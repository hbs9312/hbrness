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
spec = importlib.util.spec_from_file_location('chronicle', ROOT / 'plugins/ghflow/hooks/commit-chronicle.py')
chronicle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(chronicle)


class HookTests(unittest.TestCase):
    def run_hook(self, payload, exists=False):
        output = io.StringIO()
        with patch.object(chronicle, '_read_stdin_json', return_value=payload), \
             patch.object(chronicle, '_run', return_value=(0, 'abcdef123456')), \
             patch.object(chronicle, '_repo_slug_from_remote', return_value='test/repo'), \
             patch.object(chronicle, '_chronicle_exists', return_value=exists), \
             contextlib.redirect_stdout(output):
            self.assertEqual(chronicle.main(), 0)
        return output.getvalue()

    def test_devin_success_and_failures(self):
        event = {'tool_name': 'exec', 'tool_input': {'command': 'git commit -m test'},
                 'tool_response': {'success': True, 'output': 'committed\n\nExit code: 0', 'error': None}}
        out = json.loads(self.run_hook(event))
        self.assertIn('chronicle', out['hookSpecificOutput']['additionalContext'])
        self.assertEqual(self.run_hook(event, exists=True), '')
        for response in ({'success': False}, {'error': 'failed'}, {'exit_code': 1}, {'interrupted': True},
                         {'success': True, 'output': 'commit failed\nExit code: 1'},
                         {'success': True, 'output': 'still running'}):
            self.assertEqual(self.run_hook(dict(event, tool_response=response)), '')

    def test_claude_unchanged_and_non_commits_silent(self):
        event = {'tool_name': 'Bash', 'tool_input': {'command': 'git commit -m test'}, 'tool_response': {'exit_code': 0}}
        self.assertTrue(self.run_hook(event))
        for command in ('git status', 'git commit --dry-run', 'echo git commit', 'git commit --help'):
            self.assertEqual(self.run_hook(dict(event, tool_input={'command': command})), '')
        self.assertEqual(self.run_hook(dict(event, tool_name='read')), '')


class RuntimeTests(unittest.TestCase):
    def test_agentbus_recipient_wins_over_inherited_codex_environment(self):
        lib = ROOT / 'plugins/agentbus/skills/agent-send/scripts/lib.sh'
        script = 'source "$1"; tmux() { printf "%s\\n" "$@"; }; ab_tmux_submit "%99" "$2"'
        for tool in ('grok', 'devin'):
            result = subprocess.check_output(['bash', '-c', script, 'test', str(lib), tool],
                env=dict(os.environ, CODEX_CI='1'), text=True)
            self.assertEqual(result.splitlines()[-1], 'Enter')

    def test_phaseflow_records_native_clear_and_qualified_resume_without_sending_keys(self):
        engine = ROOT / 'plugins/sessionflow/skills/phase-run/scripts/phaseflow.sh'
        for tool in ('grok', 'devin'):
            with tempfile.TemporaryDirectory() as temp:
                env = dict(os.environ, HBRNESS_HOME=temp, PHASEFLOW_DRY_RUN='1')
                result = subprocess.run(['bash', str(engine), 'init', '--pane', '%fixture', '--tool', tool],
                    input='one\ntwo\n', text=True, capture_output=True, env=env, cwd=temp)
                self.assertEqual(result.returncode, 0, result.stderr)
                state = next(Path(temp).rglob('state.env')).read_text()
                values = dict(line.split('=', 1) for line in state.splitlines() if '=' in line)
                self.assertEqual(base64.b64decode(values['CLEAR_B64'].strip("'\"")).decode(), '/new')
                self.assertEqual(base64.b64decode(values['CONTINUE_B64'].strip("'\"")).decode(), '/sessionflow:phase-run continue')

    def test_xreview_native_callers_keep_codex_as_default_reviewer(self):
        lib = ROOT / 'plugins/xreview/scripts/lib.sh'
        for tool in ('grok', 'devin'):
            result = subprocess.check_output(['bash', '-c', 'source "$1"; xr_opposite_tool "$2"',
                                              'test', str(lib), tool], text=True)
            self.assertEqual(result, 'codex')

    def run_xreview_done_ping(self, on_done):
        notify = ROOT / 'plugins/xreview/scripts/notify.sh'
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            home, work, fakebin = temp / 'home', temp / 'work', temp / 'bin'
            (home / '.sessions').mkdir(parents=True)
            work.mkdir()
            fakebin.mkdir()
            (work / 'REVIEW_RESULT.md').write_text('VERDICT: request-changes\n')
            entry = {'slug': 's1', 'backend': 'tmux', 'launcher_backend': 'tmux', 'session_ref': 'xrev-s1'}
            if on_done is not None:
                entry['on_done'] = on_done
            (home / '.sessions/s1.json').write_text(json.dumps(entry))
            log = temp / 'tmux.log'
            tmux = fakebin / 'tmux'
            tmux.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$FAKE_TMUX_LOG"\n')
            tmux.chmod(0o755)
            env = dict(os.environ, XRLIVE_HOME=str(home), FAKE_TMUX_LOG=str(log),
                       PATH=f'{fakebin}{os.pathsep}{os.environ["PATH"]}')
            subprocess.run(['bash', str(notify), '%1', str(work), 'claude', 's1'],
                           check=True, env=env, timeout=30)
            return log.read_text(), work / 'REVIEW_RESULT.md'

    def test_xreview_done_ping_keeps_summary_request_by_default(self):
        log, result = self.run_xreview_done_ping(None)
        self.assertIn(f'send-keys -t %1 -l [xreview:live] 리뷰 완료 (s1) — Read {result} 로 결과 열어서 요약해줘.', log)

    def test_xreview_done_ping_carries_on_done_instruction(self):
        log, result = self.run_xreview_done_ping('반영하고 재리뷰를 start 해.')
        self.assertIn(f'send-keys -t %1 -l [xreview:live] 리뷰 완료 (s1) — 결과 {result}. 반영하고 재리뷰를 start 해.', log)
        self.assertNotIn('요약해줘', log)


if __name__ == '__main__':
    unittest.main()
