"""Opt-in real Codex 0.157.1 TUI test; local fake Responses server, no credentials.
PHASEFLOW_TUI_TEST=1 python3 -m unittest discover -s tests -p test_phaseflow_tui.py -v
"""
import http.server
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import threading
import time
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/sessionflow/skills/phase-run/scripts'
spec = importlib.util.spec_from_file_location('inject_tui', SCRIPTS / 'inject.py')
inject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inject)


class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        def event(value):
            self.wfile.write(('data: ' + json.dumps(value) + '\n\n').encode())
            self.wfile.flush()
        try:
            event(dict(type='response.created', response=dict(id='fixture', status='in_progress', output=[])))
            time.sleep(7)
            item = dict(type='message', role='assistant', id='fixture-msg',
                        content=[dict(type='output_text', text='Fixture complete.')])
            event(dict(type='response.output_item.added', output_index=0, item=dict(item, content=[])))
            event(dict(type='response.output_text.delta', output_index=0, content_index=0, delta='Fixture complete.'))
            event(dict(type='response.output_item.done', output_index=0, item=item))
            event(dict(type='response.completed', response=dict(id='fixture', status='completed', output=[item],
                       usage=dict(input_tokens=1, output_tokens=1, total_tokens=2))))
        except (BrokenPipeError, ConnectionResetError): pass


@unittest.skipUnless(os.environ.get('PHASEFLOW_TUI_TEST') == '1', 'opt-in real TUI integration')
class TuiTests(unittest.TestCase):
    def test_keys_busy_transition_skill_acceptance_and_input_cancellation(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        with tempfile.TemporaryDirectory(prefix='pf-tui-', dir='/tmp') as tmp:
            temp = Path(tmp).resolve()
            work, home = temp / 'work', temp / 'home'
            work.mkdir(); home.mkdir()
            skill = home / 'skills/phase-loop'
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text('---\nname: phase-loop\ndescription: Isolated fixture.\n---\nReply fixture complete. Do not run tools.\n')
            (home / 'config.toml').write_text(
                f'model="fixture"\nmodel_provider="fixture"\n[model_providers.fixture]\n'
                f'name="fixture"\nbase_url="http://127.0.0.1:{server.server_port}/v1"\n'
                f'wire_api="responses"\nrequires_openai_auth=false\n[projects."{work}"]\ntrust_level="trusted"\n')
            name = 'pf-test-' + uuid.uuid4().hex[:12]
            def tm(*args):
                return subprocess.check_output(['tmux', '-L', name, *args], text=True, timeout=3)
            command = shlex.join(['env', 'HOME=' + str(home), 'CODEX_HOME=' + str(home),
                                 'python3', str(SCRIPTS / 'codex-guard.py'), '--', '--no-alt-screen', '-a', 'never', '-s', 'read-only'])
            tm('-f', '/dev/null', 'new-session', '-d', '-s', 'fixture', '-x', '120', '-y', '40', '-c', str(work), command)
            try:
                pane = tm('list-panes', '-F', '#{pane_id}').strip()
                socket_path = tm('display-message', '-p', '-t', pane, '#{socket_path}').strip()
                def capture(): return tm('capture-pane', '-p', '-e', '-t', pane)
                def until(predicate, seconds=20):
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        if predicate(): return
                        time.sleep(.1)
                    self.fail('TUI timeout: ' + capture())
                until(lambda: inject.screen(capture())['kind'] == 'ready')
                # Find ONLY the guard process belonging to this isolated pane/server by cwd + PID.
                guard = None
                for candidate in Path('/tmp').glob('pf-*/guard.sock'):
                    try:
                        data = inject.rpc(str(candidate), op='status')
                        cwd = subprocess.check_output(['lsof', '-a', '-p', str(data['pid']), '-d', 'cwd', '-Fn'], text=True)
                        if data['pane'] == pane and '\nn' + str(work) + '\n' in cwd:
                            guard = str(candidate); break
                    except (OSError, RuntimeError, subprocess.SubprocessError): pass
                self.assertIsNotNone(guard)
                env = dict(os.environ, TMUX=socket_path + ',0,0', TMUX_PANE=pane,
                           PHASEFLOW_GUARD=guard, HBRNESS_HOME=str(temp / 'state'))
                def pf(*args, input=None):
                    return subprocess.run(['bash', str(SCRIPTS / 'phaseflow.sh'), *args], cwd=work, env=env,
                                          text=True, input=input, capture_output=True, timeout=5)
                # Immediate CSI-u: reproduce paste newline, never a model turn.
                tm('send-keys', '-t', pane, '-l', '--', 'burst fixture\x1b[13;1u')
                time.sleep(.5)
                self.assertEqual(inject.screen(capture())['kind'], 'draft')
                # Delayed plain Enter is also accepted by this version.
                tm('send-keys', '-t', pane, 'Enter')
                until(lambda: 'esc to interrupt' in inject.screen(capture())['text'])
                tm('send-keys', '-t', pane, '-l', '--', '/new')
                time.sleep(.4)
                tm('send-keys', '-t', pane, '-l', '--', '\x1b[13;1u')
                until(lambda: 'disabled while a task is in progress' in capture())
                until(lambda: 'esc to interrupt' not in inject.screen(capture())['text'])
                # Manual test cleanup only; production injector never sends editing shortcuts.
                tm('send-keys', '-t', pane, 'C-u')
                tm('send-keys', '-t', pane, '-l', '--', '/new')
                time.sleep(.4)
                tm('send-keys', '-t', pane, '-l', '--', '\x1b[13;1u')
                until(lambda: inject.screen(capture())['fresh'])
                self.assertEqual(pf('init', '--tool', 'codex', '--pane', pane,
                                    '--continue-prompt', '/phase-loop continue', input='one\ntwo\nthree\n').returncode, 0)
                tm('send-keys', '-t', pane, '-l', '--', 'slow fixture')
                time.sleep(.4)
                tm('send-keys', '-t', pane, '-l', '--', '\x1b[13;1u')
                until(lambda: 'esc to interrupt' in inject.screen(capture())['text'])
                self.assertEqual(pf('advance').returncode, 0)
                state = next((temp / 'state').rglob('state.env')).parent
                self.assertIn('duplicate reservation', pf('resume').stderr)
                time.sleep(4)
                self.assertNotIn('keys_sent', (state / 'inject.log').read_text())
                until(lambda: 'continuation_accepted' in (state / 'inject.log').read_text(), 25)
                records = [json.loads(line) for line in (state / 'inject.log').read_text().splitlines()]
                self.assertEqual([r['stage'] for r in records if r['event'] == 'keys_sent'],
                                 ['new_text', 'new_enter', 'continuation_text', 'continuation_enter'])
                self.assertIn('$phase-loop continue', capture())
                self.assertIn('CURSOR=2', pf('current').stdout)
                # Schedule while busy, then type a draft: guard cancels before /new.
                self.assertEqual(pf('advance').returncode, 0)
                tm('send-keys', '-t', pane, '-l', '--', 'user draft retained')
                until(lambda: 'user input' in (state / 'inject.log').read_text())
                self.assertIn('user draft retained', capture())
                self.assertEqual(sum(json.loads(line)['event'] == 'keys_sent'
                                     for line in (state / 'inject.log').read_text().splitlines()), 4)
            finally:
                tm('kill-server')


if __name__ == '__main__': unittest.main()
