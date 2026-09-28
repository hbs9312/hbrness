import base64
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/sessionflow/skills/phase-run/scripts'
spec = importlib.util.spec_from_file_location('inject', SCRIPTS / 'inject.py')
inject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inject)


def display(draft='', busy=False, history='', fresh=False):
    head = 'OpenAI Codex (v0.157.1)\n' if fresh else ''
    if history:
        head += '\x1b[1;2m› \x1b[0m' + history + '\n\n'
    if busy:
        head += '◦ Working (5s • esc to interrupt)\n\n'
    text = draft or '\x1b[2mAsk Codex to do anything\x1b[0m'
    return head + '\x1b[1m›\x1b[0m ' + text + '\n\n  fixture default · /tmp/work\n'


class Simulation:
    def __init__(self, directory, busy_until=0, transition=1, fault=''):
        self.directory = directory
        self.now = 1000.
        self.busy_until = self.now + busy_until
        self.transition = transition
        self.fault = fault
        self.sent = []
        self.phase = 'old'
        self.draft = ''
        self.new_at = None
        self.history = ''
        self.epoch = 1
        self.nonce = 'guard1'
        self.clear_count = 0
        self.identity = 'pane-generation-1'
        self.live = True
        self.cancel = None
        self.values = dict(RUN_ID='run1', CURSOR='4', TOTAL='8', STATUS='active', PANE='%fixture',
                           CLEAR_B64=base64.b64encode(b'/new').decode(),
                           CONTINUE_B64=base64.b64encode(b'continuation').decode())
        self.write_state()
        self.ticket = dict(id='ticket1', run='run1', phase='4', pane='%fixture', identity=self.identity,
                           state_hash=inject.state(directory)[1], guard='/fixture', nonce=self.nonce,
                           epoch=1, prompt='continuation', created=self.now, timeout=120, stage='reserved')
        inject.atomic(directory / 'inject-ticket.json', self.ticket)

    def write_state(self):
        (self.directory / 'state.env').write_text(''.join(f'{k}={v}\n' for k, v in self.values.items()))

    def sleep(self, seconds):
        self.now += seconds
        if self.cancel:
            self.cancel(self)
        if self.new_at and self.now >= self.new_at:
            self.phase = 'fresh'
            self.draft = ''
            self.clear_count += 1
            self.new_at = None

    def rpc(self, path, **request):
        if not self.live:
            raise ConnectionError('session ended')
        if request['op'] == 'send':
            self.sent.append((self.now, base64.b64decode(request['data'])))
            payload = self.sent[-1][1]
            if payload == b'/new':
                self.draft = '/new'
            elif payload == b'continuation':
                self.draft = 'continuation'
            elif self.draft == '/new':
                if self.fault != 'newline':
                    self.new_at = self.now + self.transition
            elif self.draft == 'continuation':
                if self.fault != 'unknown_acceptance':
                    self.history = self.draft
                    self.draft = ''
        return dict(ok=True, nonce=self.nonce, epoch=self.epoch, clears=self.clear_count, pane='%fixture')

    def tmux(self, *args):
        return display(self.draft, self.now < self.busy_until, self.history, self.phase == 'fresh')

    @contextlib.contextmanager
    def mocks(self):
        with patch.object(inject.time, 'time', lambda: self.now), \
             patch.object(inject.time, 'monotonic', lambda: self.now), \
             patch.object(inject.time, 'sleep', self.sleep), \
             patch.object(inject, 'identity', lambda pane: self.identity), \
             patch.object(inject, 'tmux', self.tmux), patch.object(inject, 'rpc', self.rpc):
            yield

    def run(self):
        with self.mocks():
            worker = inject.Worker(self.directory, 'ticket1')
            try:
                worker.run()
            except Exception as error:
                worker.finish(error)
                return error
            worker.finish()
        return None


class InjectionTests(unittest.TestCase):
    def scenario(self, **kwargs):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        return Simulation(Path(temp.name), **kwargs)

    def test_busy_over_four_seconds_and_delayed_transition(self):
        sim = self.scenario(busy_until=8, transition=3)
        self.assertIsNone(sim.run())
        self.assertGreaterEqual(sim.sent[0][0], 1008)
        self.assertGreaterEqual(sim.sent[2][0] - sim.sent[1][0], 3)
        self.assertEqual([p for _, p in sim.sent], [b'/new', b'\x1b[13;1u', b'continuation', b'\x1b[13;1u'])
        self.assertIn('continuation_accepted', (sim.directory / 'inject.log').read_text())
        self.assertEqual(inject.state(sim.directory)[0]['CURSOR'], '4')

    def test_enter_newline_never_sends_continuation(self):
        sim = self.scenario(fault='newline')
        self.assertIsInstance(sim.run(), TimeoutError)
        self.assertEqual(len(sim.sent), 2)
        self.assertNotIn('new_session_confirmed', (sim.directory / 'inject.log').read_text())

    def test_unknown_acceptance_never_retries_and_blocks_new_reservation(self):
        sim = self.scenario(fault='unknown_acceptance')
        self.assertIsInstance(sim.run(), TimeoutError)
        self.assertEqual(len(sim.sent), 4)
        with sim.mocks(), self.assertRaisesRegex(RuntimeError, 'already had a key attempt'):
            inject.prepare(sim.directory)
        self.assertIn('do not send it again', (sim.directory / 'RECOVERY.md').read_text())

    def test_draft_untouched(self):
        sim = self.scenario()
        sim.draft = 'user draft'
        self.assertIn('draft', str(sim.run()))
        self.assertEqual(sim.sent, [])

    def test_user_input_pause_stop_reuse_and_exit_at_each_boundary(self):
        for boundary in range(4):
            for event in ('input', 'pause', 'stop', 'pane', 'session', 'run', 'phase', 'ticket'):
                with self.subTest(boundary=boundary, event=event):
                    sim = self.scenario(busy_until=1)
                    def cancel(s):
                        if len(s.sent) != boundary:
                            return
                        if event == 'input': s.epoch += 1
                        elif event == 'pane': s.identity = 'pane-generation-2'
                        elif event == 'session': s.live = False
                        elif event == 'ticket': (s.directory / 'inject-ticket.json').unlink(missing_ok=True)
                        else:
                            if event in ('pause', 'stop'): s.values['STATUS'] = 'paused' if event == 'pause' else 'aborted'
                            elif event == 'run': s.values['RUN_ID'] = 'run2'
                            elif event == 'phase': s.values['CURSOR'] = '5'
                            s.write_state()
                    sim.cancel = cancel
                    self.assertIsNotNone(sim.run())
                    self.assertEqual(len(sim.sent), boundary)

    def test_timeout_before_input_is_bounded(self):
        sim = self.scenario(busy_until=1000)
        self.assertIsInstance(sim.run(), TimeoutError)
        self.assertEqual(sim.sent, [])
        self.assertLess(sim.now, 1121)

    def test_duplicate_worker_and_schedule(self):
        sim = self.scenario()
        with sim.mocks():
            inject.Worker(sim.directory, 'ticket1')
            with self.assertRaisesRegex(RuntimeError, 'duplicate worker'):
                inject.Worker(sim.directory, 'ticket1')
            with self.assertRaisesRegex(RuntimeError, 'duplicate reservation'):
                inject.prepare(sim.directory)
        self.assertEqual(sim.sent, [])

    def test_stale_ticket_and_absent_guard(self):
        sim = self.scenario()
        with self.assertRaisesRegex(RuntimeError, 'stale'):
            inject.Worker(sim.directory, 'old')
        (sim.directory / 'inject-ticket.json').unlink()
        with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(RuntimeError, 'no codex-guard'):
            inject.prepare(sim.directory)
        self.assertEqual(sim.sent, [])

    def test_same_pane_id_on_other_server_is_rejected_and_codex_skill_is_normalized(self):
        sim = self.scenario()
        (sim.directory / 'inject-ticket.json').unlink()
        sim.values['CONTINUE_B64'] = base64.b64encode(b'/phase-loop continue').decode()
        sim.write_state()
        def status(*args, **kwargs):
            return dict(sim.rpc(*args, **kwargs), server_socket='/tmux/guard-server')
        with sim.mocks(), patch.dict(os.environ, PHASEFLOW_GUARD='/fixture'), \
             patch.object(inject, 'rpc', status), contextlib.redirect_stdout(io.StringIO()):
            with patch.object(inject, 'identity', return_value='pid|/tmux/other-server|%fixture|1|0|cwd|start'):
                with self.assertRaisesRegex(RuntimeError, 'different tmux server'):
                    inject.prepare(sim.directory)
            with patch.object(inject, 'identity', return_value='pid|/tmux/guard-server|%fixture|1|0|cwd|start'):
                inject.prepare(sim.directory)
        ticket = json.loads((sim.directory / 'inject-ticket.json').read_text())
        self.assertEqual(ticket['prompt'], '$phase-loop continue')
        self.assertEqual(sim.sent, [])

    def test_slash_menu_and_multiline_draft(self):
        menu = '\x1b[1;7m› /new  start a new chat\x1b[0m\n\n'
        self.assertEqual(inject.screen(menu + display('/new'))['draft'], '/new')
        self.assertEqual(inject.screen(display('user\n  draft'))['kind'], 'draft')
        self.assertEqual(inject.screen('Trust this folder?')['kind'], 'unknown')


class ShellStateTests(unittest.TestCase):
    def test_resume_does_not_advance_and_stop_is_terminal(self):
        with tempfile.TemporaryDirectory() as temp:
            env = dict(os.environ, HBRNESS_HOME=temp, PHASEFLOW_DRY_RUN='1')
            env.pop('TMUX', None)
            def run(*args, input=None):
                return subprocess.run(['bash', str(SCRIPTS / 'phaseflow.sh'), *args], cwd=temp,
                                      env=env, input=input, text=True, capture_output=True)
            self.assertEqual(run('init', '--tool', 'codex', input='one\ntwo\n').returncode, 0)
            run('advance')
            out = run('resume', '--manual')
            self.assertIn('커서는 이동하지 않습니다', out.stdout)
            self.assertIn('CURSOR=2', run('current').stdout)
            run('stop')
            self.assertNotEqual(run('resume').returncode, 0)
            self.assertIn('CURSOR=2', run('current').stdout)

    def test_non_codex_native_keys_and_dry_run_never_spawns(self):
        for tool, clear in [('claude', '/clear'), ('grok', '/new'), ('devin', '/new')]:
            with self.subTest(tool=tool), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                stub = base / 'tmux'
                stub.write_text("#!/usr/bin/env python3\nimport os,sys,subprocess,json\n"
                    "args=sys.argv[1:]\n"
                    "if args[0]=='display-message': print('server|%fixture|123|runtime')\n"
                    "elif args[0]=='run-shell': subprocess.run(['bash','-c',args[2]],check=True)\n"
                    "elif args[0]=='send-keys':\n"
                    " with open(os.environ['KEY_LOG'],'a') as f: f.write(json.dumps(args)+'\\n')\n")
                stub.chmod(0o755)
                env = dict(os.environ, HBRNESS_HOME=temp, TMUX='fixture', PHASEFLOW_GAP='0',
                           PATH=temp + os.pathsep + os.environ['PATH'], KEY_LOG=str(base/'keys'))
                def run(*args, input=None):
                    return subprocess.run(['bash', str(SCRIPTS / 'phaseflow.sh'), *args], cwd=temp,
                                          env=env, input=input, text=True, capture_output=True)
                run('init', '--tool', tool, '--pane', '%fixture', '--delay', '0', input='one\ntwo\n')
                self.assertEqual(run('advance').returncode, 0)
                keys = [json.loads(line) for line in (base/'keys').read_text().splitlines()]
                self.assertEqual(keys[0][-1], clear)
                self.assertEqual(keys[1][-1], 'Enter')
                self.assertEqual(keys[3][-1], 'Enter')
                before = (base/'keys').read_text()
                env['PHASEFLOW_DRY_RUN'] = '1'
                self.assertIn('[dry-run]', run('resume').stdout)
                self.assertEqual((base/'keys').read_text(), before)

    def test_old_inject_invocation_is_inert(self):
        result = subprocess.run(['bash', str(SCRIPTS / 'phaseflow.sh'), '__inject'],
                                text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('no keys sent', result.stdout)


if __name__ == '__main__':
    unittest.main()
