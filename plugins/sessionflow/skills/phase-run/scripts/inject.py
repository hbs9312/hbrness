#!/usr/bin/env python3
"""Bounded Codex 0.157.1 TUI adapter. Fail closed; never infer success from send()."""
import base64
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time
import uuid


@contextlib.contextmanager
def locked(directory):
    path = Path(directory)
    path.parent.mkdir(parents=True, exist_ok=True)
    with (path.parent / ('.' + path.name + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def atomic(path, value):
    temp = path.with_suffix('.tmp-' + uuid.uuid4().hex)
    with temp.open('w') as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def state(directory):
    raw = (directory / 'state.env').read_text()
    result = {}
    for line in raw.splitlines():
        key, value = line.split('=', 1)
        words = shlex.split(value)
        result[key] = words[0] if words else ''
    return result, hashlib.sha256(raw.encode()).hexdigest()


def rpc(path, **request):
    with socket.socket(socket.AF_UNIX) as client:
        client.settimeout(2)
        client.connect(path)
        client.sendall(json.dumps(request).encode() + b'\n')
        data = b''
        while not data.endswith(b'\n'):
            part = client.recv(16384)
            if not part or len(data) > 16384:
                raise RuntimeError('guard disconnected')
            data += part
    result = json.loads(data)
    if not result.get('ok'):
        raise RuntimeError(result.get('error', 'guard refused'))
    return result


def tmux(*args):
    return subprocess.check_output(['tmux', *args], text=True, timeout=2)


def identity(pane):
    # Server lifetime + pane shell lifetime; guard nonce separately binds the Codex process.
    value = tmux('display-message', '-p', '-t', pane,
                 '#{pid}|#{socket_path}|#{pane_id}|#{pane_pid}|#{pane_dead}|#{pane_current_path}').strip()
    parts = value.split('|')
    if len(parts) != 6 or parts[2] != pane or parts[4] != '0':
        raise RuntimeError('pane missing/dead')
    started = subprocess.check_output(['ps', '-p', parts[3], '-o', 'lstart='], text=True, timeout=2).strip()
    if not started:
        raise RuntimeError('pane process ended')
    return value + '|' + started


OSC = re.compile(r'\x1b\][^\x1b\x07]*(?:\x07|\x1b\\)')
SGR = re.compile(r'\x1b\[([0-9;]*)m')


def cells(raw):
    """Only capture-pane SGR/OSC; retain dim/bold to distinguish history and placeholder."""
    bold = dim = False
    out = []
    offset = 0
    raw = OSC.sub('', raw)
    for match in SGR.finditer(raw):
        out.extend((ch, bold, dim) for ch in raw[offset:match.start()])
        for number in (int(n or '0') for n in match[1].split(';')):
            if number == 0:
                bold = dim = False
            elif number == 1:
                bold = True
            elif number == 2:
                dim = True
            elif number == 22:
                bold = dim = False
        offset = match.end()
    out.extend((ch, bold, dim) for ch in raw[offset:])
    return out


def screen(raw):
    rows = []
    row = []
    for ch, bold, dim in cells(raw):
        if ch == '\n':
            rows.append(row)
            row = []
        else:
            row.append((ch, bold, dim))
    rows.append(row)
    lines = [''.join(c[0] for c in row).rstrip() for row in rows]
    text = '\n'.join(lines)
    prompts = [i for i, row in enumerate(rows)
               if row and row[0] == ('›', True, False)]
    result = dict(kind='unknown', draft='', fresh=False, text=text)
    if not prompts:
        return result
    i = prompts[-1]  # slash completion menu can also contain a bold › above the composer
    # Actual input is not dim; placeholder is. A wrapped/multiline draft is unsafe.
    draft = ''.join(ch for ch, _, dim in rows[i][1:] if not dim).strip()
    if i + 1 < len(lines) and lines[i + 1].strip():
        draft += '\n' + lines[i + 1].strip()
    result['draft'] = draft
    if draft:
        result['kind'] = 'draft'
        return result
    if any(word in text for word in ('esc to interrupt', 'esc to cancel', 'task is in progress',
                                     'Reconnecting', 'Press enter', 'Trust this folder')):
        result['kind'] = 'busy'
        return result
    # Known 0.157.1 footer; unsupported layouts/dialogs fail closed.
    if not any(' · ' in line and ('/' in line or '~' in line) for line in lines[i + 1:]):
        return result
    result['kind'] = 'ready'
    result['fresh'] = ('OpenAI Codex' in text and '(v0.157.1)' in text
                       and sum(line.startswith('›') for line in lines) == 1
                       and not any(line.startswith(('•', '■')) for line in lines))
    return result


def log(directory, ticket, event, **fields):
    record = dict(time=time.time(), ticket=ticket['id'], run=ticket['run'],
                  phase=ticket['phase'], pane=ticket['pane'], event=event, **fields)
    with (directory / 'inject.log').open('a') as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + '\n')
        stream.flush()


def prepare(directory):
    values, digest = state(directory)
    phase = values['CURSOR']
    receipt = directory / ('attempt-' + values['RUN_ID'] + '-' + phase + '.json')
    if receipt.exists():
        raise RuntimeError('this phase already had a key attempt; inspect inject.log and resume manually')
    pending = directory / 'inject-ticket.json'
    if pending.exists():
        old = json.loads(pending.read_text())
        if old['state_hash'] == digest:
            raise RuntimeError('duplicate reservation refused; existing ticket retained')
    path = os.environ.get('PHASEFLOW_GUARD', '')
    if not path:
        raise RuntimeError('no codex-guard; no keys sent. Use manual continuation or launch codex-guard.py next session')
    guard = rpc(path, op='status')
    target_identity = identity(values['PANE'])
    if (guard['pane'] != values['PANE']
            or guard.get('server_socket') != os.path.realpath(target_identity.split('|')[1])):
        raise RuntimeError('guard belongs to a different tmux server/pane')
    if base64.b64decode(values['CLEAR_B64']).decode() != '/new':
        raise RuntimeError('Codex adapter only supports /new')
    prompt = base64.b64decode(values['CONTINUE_B64']).decode()
    prompt = re.sub(r'^/(?:sessionflow:)?(phase-loop|phase-run)(?= |$)', r'$\1', prompt)
    if not prompt or any(ord(c) < 32 or ord(c) == 127 for c in prompt) or len(prompt) > 512:
        raise RuntimeError('continuation must be one short line')
    ticket = dict(id=uuid.uuid4().hex, run=values['RUN_ID'], phase=phase,
                  pane=values['PANE'], identity=target_identity, state_hash=digest,
                  guard=path, nonce=guard['nonce'], epoch=guard['epoch'], prompt=prompt,
                  created=time.time(), timeout=120, stage='reserved')
    rpc(path, op='reserve', nonce=guard['nonce'], epoch=guard['epoch'], ticket=ticket['id'])
    atomic(pending, ticket)
    log(directory, ticket, 'reserved')
    print(ticket['id'])


class Worker:
    def __init__(self, directory, ticket_id):
        self.directory = directory
        with locked(directory):
            self.ticket = json.loads((directory / 'inject-ticket.json').read_text())
            if self.ticket['id'] != ticket_id or self.ticket.get('worker_started'):
                raise RuntimeError('stale or duplicate worker')
            self.ticket['worker_started'] = True
            atomic(directory / 'inject-ticket.json', self.ticket)
        remaining = max(0, min(self.ticket['timeout'], self.ticket['created'] + self.ticket['timeout'] - time.time()))
        self.deadline = time.monotonic() + remaining

    def validate(self):
        t = self.ticket
        if time.monotonic() > self.deadline:
            raise TimeoutError('reservation timeout')
        current = json.loads((self.directory / 'inject-ticket.json').read_text())
        values, digest = state(self.directory)
        if (current['id'] != t['id'] or values['STATUS'] != 'active'
                or (self.directory / 'PAUSED').exists() or digest != t['state_hash']):
            raise RuntimeError('cancelled: run/phase/state/reservation changed')
        if identity(t['pane']) != t['identity']:
            raise RuntimeError('pane replaced or cwd changed')
        guard = rpc(t['guard'], op='status')
        if guard['nonce'] != t['nonce'] or guard['epoch'] != t['epoch']:
            raise RuntimeError('cancelled: user input, resize, or session replacement')
        return guard

    def observe(self):
        with locked(self.directory):
            guard = self.validate()
            view = screen(tmux('capture-pane', '-p', '-e', '-t', self.ticket['pane']))
            self.validate()
            return guard, view

    def wait_for(self, predicate, label, seconds=None):
        end = min(self.deadline, time.monotonic() + seconds) if seconds else self.deadline
        stable_since = None
        while time.monotonic() < end:
            guard, view = self.observe()
            if predicate(guard, view):
                stable_since = stable_since or time.monotonic()
                if time.monotonic() - stable_since >= .3:
                    return guard, view
            else:
                stable_since = None
            time.sleep(.05)
        raise TimeoutError(label + ' timeout; no retry')

    def send(self, payload, stage):
        with locked(self.directory):
            self.validate()
            t = self.ticket
            view = screen(tmux('capture-pane', '-p', '-e', '-t', t['pane']))
            if stage.endswith('_text'):
                if view['kind'] != 'ready' or (stage == 'continuation_text' and not view['fresh']):
                    raise RuntimeError('input no longer empty/ready')
            else:
                expected = '/new' if stage == 'new_enter' else t['prompt']
                if view['kind'] != 'draft' or view['draft'] != expected:
                    raise RuntimeError('composer changed before Enter')
            self.validate()
            t['stage'] = stage
            # Durable before write: a crash or uncertain response is never replayed.
            atomic(self.directory / ('attempt-' + t['run'] + '-' + t['phase'] + '.json'), t)
            rpc(t['guard'], op='send', nonce=t['nonce'], epoch=t['epoch'], ticket=t['id'],
                data=base64.b64encode(payload).decode())
            log(self.directory, t, 'keys_sent', stage=stage)

    def run(self):
        def idle(_, view):
            if view['kind'] == 'draft':
                raise RuntimeError('user draft present; untouched')
            return view['kind'] == 'ready'
        guard, _ = self.wait_for(idle, 'idle')
        baseline = guard['clears']
        log(self.directory, self.ticket, 'input_ready')
        self.send(b'/new', 'new_text')
        self.wait_for(lambda _, v: v['kind'] == 'draft' and v['draft'] == '/new', 'new input render', 5)
        # Render stable >=300ms, beyond 0.157.1 paste Enter suppression (120ms).
        self.send(b'\x1b[13;1u', 'new_enter')
        self.wait_for(lambda g, v: g['clears'] > baseline and v['kind'] == 'ready' and v['fresh'],
                      'new session confirmation', 15)
        log(self.directory, self.ticket, 'new_session_confirmed', evidence='screen_clear+fresh_0.157.1_layout')
        self.send(self.ticket['prompt'].encode(), 'continuation_text')
        self.wait_for(lambda _, v: v['kind'] == 'draft' and v['draft'] == self.ticket['prompt'],
                      'continuation render', 5)
        self.send(b'\x1b[13;1u', 'continuation_enter')
        # Exact history cell + empty composer establishes TUI acceptance, not task completion.
        expected = '› ' + self.ticket['prompt']
        self.wait_for(lambda _, v: v['kind'] in ('ready', 'busy') and expected in v['text'].splitlines(),
                      'continuation acceptance', 15)
        log(self.directory, self.ticket, 'continuation_accepted', evidence='exact_user_history_cell')

    def finish(self, error=None):
        t = self.ticket
        with locked(self.directory):
            if self.directory.exists():
                log(self.directory, t, 'timeout' if isinstance(error, TimeoutError) else 'failed' if error else 'finished',
                    reason=str(error) if error else '', stage=t['stage'])
                values, _ = state(self.directory)
                if error and values['RUN_ID'] == t['run'] and values['CURSOR'] == t['phase']:
                    (self.directory / 'RECOVERY.md').write_text(
                        f'# Automatic continuation stopped\n\nPhase {t["phase"]}; stage `{t["stage"]}`.\n\n'
                        f'Reason: {error}\n\nNo automatic retry. Inspect the target Codex conversation and draft first. '
                        'If the continuation already appears as a user message, do not send it again. '
                        'Wait for any active task. Preserve any draft manually. '
                        'Use `resume --manual` only if paused, then manually enter `/new`, wait for a fresh chat, '
                        f'and enter `{t["prompt"]}` once if it was not accepted. Never use advance to recover.\n')
        try:
            rpc(t['guard'], op='release', nonce=t['nonce'], epoch=t['epoch'], ticket=t['id'])
        except (OSError, RuntimeError):
            pass


def main():
    action, directory, *args = sys.argv[1:]
    directory = Path(directory)
    if action == 'locked':
        with locked(directory):
            env = dict(os.environ, PHASEFLOW_LOCK_HELD='1')
            return subprocess.call(args, env=env)
    if action == 'prepare':
        try:
            prepare(directory)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            values, _ = state(directory)
            refused = dict(id=uuid.uuid4().hex, run=values['RUN_ID'], phase=values['CURSOR'], pane=values['PANE'])
            log(directory, refused, 'reservation_refused', reason=str(error))
            print('phaseflow: ' + str(error), file=sys.stderr)
            return 1
    elif action == 'worker':
        worker = None
        try:
            worker = Worker(directory, args[0])
            worker.run()
        except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
            if worker:
                worker.finish(error)
            else:
                print('phaseflow: stale/missing reservation; no keys sent', file=sys.stderr)
            return 1
        worker.finish()
    return 0


if __name__ == '__main__':
    sys.exit(main())
