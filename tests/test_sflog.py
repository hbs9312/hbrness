import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'plugins/sessionflow/scripts'
SFLOG = SCRIPTS / 'sflog.py'
SFHOOK = SCRIPTS / 'sfhook.py'
SFSTATE = SCRIPTS / 'sfstate.py'
spec = importlib.util.spec_from_file_location('sflog', SFLOG)
sflog = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sflog)

GIT_ENV = {
    'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
    'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com',
    'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
}


def sh(*args, cwd=None, env=None, input=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True, input=input).stdout


class RedactTests(unittest.TestCase):
    def test_known_secrets_are_masked(self):
        cases = {
            'AKIAABCDEFGHIJKLMNOP': 'aws-access-key',
            'ghp_' + 'a' * 36: 'github-token',
            'sk-ant-api03-' + 'b' * 30: 'anthropic-key',
            'xoxb-1234567890-abcdef': 'slack-token',
            'ATATT3xFfGF0' + 'c' * 30: 'atlassian-token',
            'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYifQ.abcdefghijklmnop': 'jwt',
        }
        for secret, name in cases.items():
            out = sflog.redact(f'token is {secret} ok')
            self.assertNotIn(secret, out)
            self.assertIn(f'[REDACTED:{name}]', out)

    def test_private_key_and_assignments_inside_jsonl(self):
        line = json.dumps({'text': 'key:\n-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----\n'
                                   'password = hunter2hunter2 and "api_key": "abcd1234efgh"'})
        out = sflog.redact(line)
        self.assertNotIn('MIIEow', out)
        self.assertNotIn('hunter2hunter2', out)
        self.assertNotIn('abcd1234efgh', out)
        json.loads(out)  # 가린 뒤에도 JSON 줄이 깨지지 않는다

    def test_tokens_right_after_a_serialised_newline(self):
        secrets = ['AKIAABCDEFGHIJKLMNOP', 'ghp_' + 'a' * 36, 'sk-ant-api03-' + 'b' * 30]
        for secret in secrets:
            line = json.dumps({'text': 'credentials:\n' + secret + '\n'})
            out = sflog.redact(line)
            self.assertNotIn(secret, out)
            json.loads(out)
            # 문자열 안에 JSON 이 한 번 더 들어 있어도 (escape 가 두 겹)
            nested = json.dumps({'tool_result': json.dumps({'out': 'x\n' + secret})})
            self.assertNotIn(secret, sflog.redact(nested))

    def test_sensitive_keys_stay_valid_json(self):
        for raw in ('{"password":123456789}', '{"db_password":"pw"}', '{"api_key":12.5}',
                    '{"nested":{"client_secret":"abcdefgh"}}'):
            out = sflog.redact(raw)
            data = json.loads(out)
            self.assertIn('[REDACTED:assignment]', out, raw)
            self.assertNotIn('123456789', out)
        self.assertEqual(sflog.redact('{"input_tokens":123,"is_secret":true}'), '{"input_tokens":123,"is_secret":true}')

    def test_unchanged_lines_keep_their_bytes(self):
        line = b'{ "a" : 1 ,  "b":"\\u00e9" }'
        self.assertEqual(sflog.redact_jsonl(line + b'\n'), line + b'\n')

    def test_quoted_values_in_transcript_text_are_masked_whole(self):
        for text, secret in (('password="shortpw"', 'shortpw'), ('password="two words long"', 'two words'),
                             ("DB_PASSWORD='x y z'", 'x y z'), ('export AWS_SECRET_ACCESS_KEY=abc/def', 'abc/def'),
                             ('curl -H "Authorization: Bearer abcdefghijklmnopqrstuv"', 'abcdefghijklmnopqrstuv')):
            out = sflog.redact(json.dumps({'type': 'tool_result', 'content': f'$ {text} rest'}))
            self.assertNotIn(secret, out, text)
            self.assertIn('rest', out)
            json.loads(out)

    def test_long_base64_runs_stay_fast(self):
        import random
        import string
        blob = ''.join(random.choice(string.ascii_letters + string.digits + '-_') for _ in range(2_000_000))
        started = time.monotonic()
        sflog.redact_text(blob)
        self.assertLess(time.monotonic() - started, 5)

    def test_plain_text_is_left_alone(self):
        text = 'the password field must be at least 8 chars; skip-ant is a word'
        self.assertEqual(sflog.redact(text), text)


class CollectEnv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.home = self.base / 'home'
        self.store = self.base / 'store'
        self.project = self.base / 'work' / 'app'
        self.project.mkdir(parents=True)
        e = self.env()
        sh('git', 'init', '-q', '-b', 'main', cwd=self.project, env=e)
        sh('git', 'remote', 'add', 'origin', 'git@github.com:acme/app.git', cwd=self.project, env=e)
        sh(sys.executable, str(SFSTATE), 'init', '--backend', 'local', '--path', str(self.store),
           cwd=self.project, env=e)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, **extra):
        return dict(os.environ, **GIT_ENV, HBRNESS_HOME=str(self.home), HBRNESS_STATE_DIR=str(self.home / 'state'),
                    GROK_HOME=str(self.base / 'grok'), **extra)

    def collect(self, tool, session, transcript='', final=False):
        args = [sys.executable, str(SFLOG), 'collect', '--tool', tool, '--session', session,
                '--transcript', str(transcript), '--cwd', str(self.project)]
        return sh(*args + (['--final'] if final else []), cwd=self.project, env=self.env())

    def remote(self, tool, session):
        return self.store / 'logs' / 'github.com/acme/app' / tool / session

    def segments(self, tool, session):
        d = self.remote(tool, session)
        return b''.join(gzip.decompress(f.read_bytes()) for f in sorted(d.glob('*.jsonl.gz')))


class CollectTests(CollectEnv):
    def test_jsonl_is_uploaded_in_growing_segments_and_redacted(self):
        t = self.base / 'claude.jsonl'
        t.write_text('{"n":1}\n{"n":2, "k":"AKIAABCDEFGHIJKLMNOP"}\n{"n":3')  # 마지막 줄은 아직 쓰는 중
        self.assertIn('COLLECT=uploaded 1', self.collect('claude', 's1', t))
        self.assertEqual(self.segments('claude', 's1'),
                         b'{"n":1}\n{"n":2,"k":"[REDACTED:aws-access-key]"}\n')  # 가린 줄만 다시 직렬화
        self.assertIn('COLLECT=nochange', self.collect('claude', 's1', t))
        with open(t, 'a') as fh:
            fh.write('}\n{"n":4}\n')
        self.assertIn('COLLECT=uploaded 1', self.collect('claude', 's1', t))
        self.assertTrue(self.segments('claude', 's1').endswith(b'{"n":3}\n{"n":4}\n'))
        meta = json.loads((self.remote('claude', 's1') / 'meta.json').read_text())
        self.assertEqual((meta['tool'], meta['repo_key'], meta['branch'], meta['segments'], meta['ended']),
                         ('claude', 'github.com/acme/app', 'main', 2, None))
        self.collect('claude', 's1', t, final=True)
        self.assertIsNotNone(json.loads((self.remote('claude', 's1') / 'meta.json').read_text())['ended'])

    def test_final_uploads_an_unterminated_last_line(self):
        t = self.base / 'codex.jsonl'
        t.write_text('{"a":1}\n{"b":2}')
        self.collect('codex', 's2', t)
        self.collect('codex', 's2', t, final=True)
        self.assertEqual(self.segments('codex', 's2'), b'{"a":1}\n{"b":2}')

    def test_rewritten_transcript_starts_over(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"old":1}\n{"old":2}\n')
        self.collect('claude', 's3', t)
        t.write_text('{"new":1}\n{"new":2}\n{"new":3}\n')  # 더 길어졌지만 앞부분이 다르다
        self.collect('claude', 's3', t)
        self.assertTrue(self.segments('claude', 's3').endswith(b'{"new":1}\n{"new":2}\n{"new":3}\n'))
        self.assertEqual(json.loads((self.remote('claude', 's3') / 'meta.json').read_text())['rewrites'], 1)

    def test_grok_transcript_is_found_from_session_and_cwd(self):
        import urllib.parse
        d = self.base / 'grok' / 'sessions' / urllib.parse.quote(str(self.project), safe='') / 'g-1'
        d.mkdir(parents=True)
        (d / 'chat_history.jsonl').write_text('{"role":"user"}\n')
        self.assertIn('COLLECT=uploaded 1', self.collect('grok', 'g-1'))
        self.assertEqual(self.segments('grok', 'g-1'), b'{"role":"user"}\n')

    def test_devin_json_snapshot_is_replaced_only_when_it_changes(self):
        t = self.base / 'north-mandible.json'
        t.write_text('{"schema_version": 1, "steps": []}')
        self.assertIn('uploaded 1', self.collect('devin', 'd-1', t))
        self.assertIn('nochange', self.collect('devin', 'd-1', t))
        t.write_text('{"schema_version": 1, "steps": [{"text": "ghp_' + 'x' * 36 + '"}]}')
        self.assertIn('uploaded 1', self.collect('devin', 'd-1', t))
        snap = gzip.decompress((self.remote('devin', 'd-1') / 'transcript.json.gz').read_bytes())
        self.assertIn(b'[REDACTED:github-token]', snap)

    def test_custom_patterns_from_redact_txt(self):
        self.home.mkdir(exist_ok=True)
        (self.home / 'redact.txt').write_text('# 사내 키\ncorp-[0-9]{6}\n')
        t = self.base / 'c.jsonl'
        t.write_text('{"k":"corp-123456"}\n')
        self.collect('claude', 's4', t)
        self.assertEqual(self.segments('claude', 's4'), b'{"k":"[REDACTED:custom]"}\n')

    def test_without_backend_nothing_happens(self):
        (self.home / 'backend.json').unlink()
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n')
        self.assertIn('COLLECT=off', self.collect('claude', 's5', t))


class InProcessCollectTests(CollectEnv):
    """모듈 상수·backend 를 바꿔 끼워야 하는 경우 — 같은 프로세스에서 collect 를 부른다."""

    def setUp(self):
        super().setUp()
        self.saved = {k: os.environ.get(k) for k in ('HBRNESS_HOME', 'HBRNESS_STATE_DIR')}
        os.environ.update(HBRNESS_HOME=str(self.home), HBRNESS_STATE_DIR=str(self.home / 'state'))

    def tearDown(self):
        for k, v in self.saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        super().tearDown()

    def test_long_records_are_never_split_across_segments(self):
        secret = 'AKIAABCDEFGHIJKLMNOP'
        t = self.base / 'big.jsonl'
        t.write_text(json.dumps({'pad': 'x' * 30, 'k': secret}) + '\n' + json.dumps({'n': 2}) + '\n')
        old = sflog.SEGMENT_MAX
        sflog.SEGMENT_MAX = 40  # 첫 줄보다 짧다 — 비밀값이 경계에 걸린다
        try:
            sflog.collect('claude', 'big', str(t), str(self.project))
        finally:
            sflog.SEGMENT_MAX = old
        segs = [gzip.decompress(f.read_bytes()) for f in sorted(self.remote('claude', 'big').glob('*.jsonl.gz'))]
        self.assertNotIn(secret.encode(), b''.join(segs))
        for seg in segs:
            for line in seg.splitlines():
                json.loads(line)  # segment 마다 완성된 줄만

    def test_meta_is_retried_after_a_failed_write(self):
        sfstate_mod = sflog.sfstate
        real = sfstate_mod.load_backend
        fail = {'meta': True}

        def flaky():
            be = real()
            put = be.put

            def put_(key, data, **kw):
                if key.endswith('meta.json') and fail['meta']:
                    raise sflog.sfbackend.BackendError('meta down')
                return put(key, data, **kw)
            be.put = put_
            return be

        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n')
        sflog.collect('claude', 'm', str(t), str(self.project))  # meta 성공
        with open(t, 'a') as fh:
            fh.write('{"a":2}\n')
        sfstate_mod.load_backend = flaky
        try:
            with self.assertRaises(sflog.sfbackend.BackendError):
                sflog.collect('claude', 'm', str(t), str(self.project))
            fail['meta'] = False
            sflog.collect('claude', 'm', str(t), str(self.project))  # 새 줄이 없어도 meta 를 다시 쓴다
        finally:
            sfstate_mod.load_backend = real
        meta = json.loads((self.remote('claude', 'm') / 'meta.json').read_text())
        self.assertEqual(meta['segments'], 2)


class StoreSwitchTests(CollectEnv):
    def test_switching_backend_uploads_from_the_start(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n')
        self.collect('claude', 'sw', t)
        other = self.base / 'store-b'
        sh(sys.executable, str(SFSTATE), 'init', '--backend', 'local', '--path', str(other),
           cwd=self.project, env=self.env())
        self.assertIn('uploaded 1', self.collect('claude', 'sw', t))
        d = other / 'logs' / 'github.com/acme/app' / 'claude' / 'sw'
        self.assertEqual(sorted(f.name for f in d.iterdir()), ['000001.jsonl.gz', 'meta.json'])
        self.assertEqual(json.loads((d / 'meta.json').read_text())['segments'], 1)

    def test_session_end_is_published_even_without_the_transcript(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n')
        self.collect('claude', 'gone', t)
        t.unlink()
        self.assertIn('no-transcript', self.collect('claude', 'gone', t, final=True))
        self.assertIsNotNone(json.loads((self.remote('claude', 'gone') / 'meta.json').read_text())['ended'])


class LifecycleTests(unittest.TestCase):
    def test_only_full_unfiltered_expiration_counts(self):
        f = sflog.sfstate.logs_lifecycle
        rule = lambda prefix, expires=True, filtered=False, enabled=True: dict(
            prefix=prefix, expires=expires, filtered=filtered, enabled=enabled)
        self.assertTrue(f('p/logs/', [rule('p/logs/')]).startswith('ok'))
        self.assertTrue(f('p/logs/', [rule('')]).startswith('ok'))
        self.assertTrue(f('p/logs/', [rule('p/logs/one-repo/')]).startswith('partial'))
        self.assertTrue(f('p/logs/', [rule('p/logs/', filtered=True)]).startswith('partial'))
        self.assertTrue(f('p/logs/', [rule('p/logs/', expires=False)]).startswith('none'))
        self.assertTrue(f('p/logs/', [rule('p/logs/', enabled=False)]).startswith('none'))
        self.assertTrue(f('p/logs/', [rule('other/')]).startswith('none'))

    def test_rules_are_parsed_from_xml(self):
        be_cls = sflog.sfbackend.S3Backend
        body = (b'<LifecycleConfiguration xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                b'<Rule><ID>a</ID><Status>Enabled</Status><Filter><Prefix>p/logs/</Prefix></Filter>'
                b'<Expiration><Days>180</Days></Expiration></Rule>'
                b'<Rule><ID>b</ID><Status>Enabled</Status><Filter><And><Prefix>p/</Prefix><Tag><Key>k</Key>'
                b'<Value>v</Value></Tag></And></Filter><Transition><Days>30</Days></Transition></Rule>'
                b'</LifecycleConfiguration>')

        class Fake(be_cls):
            def _request(self, *a, **k):
                return 200, {}, body

        be = Fake({'bucket': 'b', 'endpoint': 'http://x'}, {'access_key_id': 'k', 'secret_access_key': 's'})
        self.assertEqual(be.lifecycle_rules(), [
            {'prefix': 'p/logs/', 'enabled': True, 'expires': True, 'filtered': False},
            {'prefix': 'p/', 'enabled': True, 'expires': False, 'filtered': True}])


class HookTests(CollectEnv):
    def test_hook_returns_at_once_silently_and_collects_in_background(self):
        t = self.base / 'claude.jsonl'
        t.write_text('{"hello":1}\n')
        payload = json.dumps({'session_id': 'h-1', 'transcript_path': str(t), 'cwd': str(self.project),
                              'hook_event_name': 'Stop'})
        started = time.monotonic()
        out = sh(sys.executable, str(SFHOOK), 'stop', '--tool', 'claude', cwd=self.project, env=self.env(),
                 input=payload)
        self.assertEqual(out, '')
        self.assertLess(time.monotonic() - started, 2)
        meta = self.remote('claude', 'h-1') / 'meta.json'
        for _ in range(100):
            if meta.exists():
                break
            time.sleep(0.1)
        self.assertEqual(self.segments('claude', 'h-1'), b'{"hello":1}\n')

    def test_grok_payload_keys(self):
        import urllib.parse
        d = self.base / 'grok' / 'sessions' / urllib.parse.quote(str(self.project), safe='') / 'g-2'
        d.mkdir(parents=True)
        (d / 'chat_history.jsonl').write_text('{"g":1}\n')
        payload = json.dumps({'hookEventName': 'session_end', 'sessionId': 'g-2', 'cwd': str(self.project)})
        sh(sys.executable, str(SFHOOK), 'session-end', '--tool', 'grok', cwd=self.project, env=self.env(),
           input=payload)
        meta = self.remote('grok', 'g-2') / 'meta.json'
        for _ in range(100):
            if meta.exists() and json.loads(meta.read_text()).get('ended'):
                break
            time.sleep(0.1)
        self.assertIsNotNone(json.loads(meta.read_text())['ended'])

    def test_bad_input_never_breaks_the_turn(self):
        out = sh(sys.executable, str(SFHOOK), 'stop', '--tool', 'codex', cwd=self.project, env=self.env(),
                 input='not json')
        self.assertEqual(out, '')


class BuildHookTests(unittest.TestCase):
    def test_sessionflow_hooks_per_harness(self):
        spec = importlib.util.spec_from_file_location('build_plugin', ROOT / 'scripts/build-plugin.py')
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        with tempfile.TemporaryDirectory() as d:
            out = {}
            for h in ('claude', 'codex', 'grok', 'devin'):
                o = Path(d) / h
                build.build_plugin(h, str(ROOT / 'plugins/sessionflow'), str(ROOT / f'adapters/{h}.adapter.json'), str(o))
                out[h] = o
            self.assertIn('${CLAUDE_PLUGIN_ROOT}/scripts/sfhook.py',
                          (out['claude'] / 'hooks/hooks.json').read_text())
            self.assertIn('--tool grok', (out['grok'] / 'hooks/hooks.json').read_text())
            devin = json.loads((out['devin'] / 'hooks.json').read_text())
            self.assertEqual(sorted(devin), ['SessionEnd', 'Stop'])
            self.assertFalse((out['codex'] / 'hooks/hooks.json').exists())  # ghflow 훅이 섞여 들어가지 않는다
            for o in out.values():
                self.assertEqual(list(o.glob('hooks/*.hooks.json')), [])


if __name__ == '__main__':
    unittest.main()
