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

    def test_lone_surrogates_survive_redaction(self):
        line = b'{"t":"\\ud800 password=hunter2hunter2"}'
        out = sflog.redact_jsonl(line + b'\n')
        self.assertNotIn(b'hunter2', out)
        self.assertEqual(json.loads(out)['t'], '\ud800 password=[REDACTED:assignment]')

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

    def test_more_token_prefixes(self):
        cases = {
            'sk_live_' + 'a1B2' * 6: 'stripe-key', 'rk_test_' + 'a1B2' * 6: 'stripe-key',
            'whsec_' + 'Ab1' * 10: 'stripe-key', 'npm_' + 'a1' * 18: 'npm-token',
            'glpat-' + 'Ab1_' * 6: 'gitlab-token', 'pypi-AgEIcHlwaS5vcmc' + 'x1' * 30: 'pypi-token',
            'hf_' + 'Ab1' * 12: 'huggingface-token', 'xapp-1-A0' + 'b1' * 10: 'slack-token',
            'shpat_' + '0a' * 16: 'shopify-token', 'dop_v1_' + '0a' * 32: 'digitalocean-token',
            'SG.' + 'Ab1' * 8 + '.' + 'Cd2' * 15: 'sendgrid-key', 'gsk_' + 'Ab1' * 18: 'groq-key',
            'xai-' + 'Ab1' * 20: 'xai-key', 'ya29.' + 'Ab1_' * 8: 'google-oauth', 'GOCSPX-' + 'Ab1' * 9: 'google-oauth',
            'AGE-SECRET-KEY-1' + 'QYQSZQGP' * 7 + 'QY': 'age-secret-key', 'dapi' + '0a' * 16: 'databricks-token',
            'lin_api_' + 'Ab1' * 14: 'linear-key', 'ntn_' + 'Ab1' * 15: 'notion-token',
            'sntrys_' + 'Ab1=' * 8: 'sentry-token',
        }
        for secret, name in cases.items():
            out = sflog.redact(json.dumps({'text': f'value {secret} ok'}))
            self.assertNotIn(secret, out, name)
            self.assertIn(f'[REDACTED:{name}]', out, secret)

    def test_url_passwords_keep_user_and_host(self):
        for text, secret in (('DATABASE_URL=postgres://app:S3cr3tPass@db/x', 'S3cr3tPass'),
                             ('mongodb+srv://u:pw@cluster0.example.net/db', 'pw@'),
                             ('redis://:only-pass@cache:6379/0', 'only-pass')):
            out = sflog.redact(text)
            self.assertNotIn(secret, out, text)
            self.assertIn('[REDACTED:url-password]@', out)
        self.assertEqual(sflog.redact('postgres://app:pw@db/x'), 'postgres://app:[REDACTED:url-password]@db/x')
        for text in ('https://example.com:8080/a@b', 'git@github.com:acme/app.git', 'ssh://git@github.com:22/a/b'):
            self.assertEqual(sflog.redact(text), text)

    def test_env_lines_with_random_looking_values(self):
        env = ('     1\tAPP=web\n     2\tSESSION_SALT=9fK2xLq8Zp3Mabc\n  3→export TENANT="1b4e28ba2fa111d2883f"\n'
               'NODE_ENV=production\nPORT=3000\nPATH=/usr/local/bin:/bin\nPYTHONPATH=/opt/lib/python3.12/site\n'
               'MY_PRIVATE=hunter2hunter2\nLOG_LEVEL=debug')
        out = json.loads(sflog.redact(json.dumps({'content': env})))['content']
        for secret in ('9fK2xLq8Zp3Mabc', '1b4e28ba2fa111d2883f', 'hunter2hunter2'):
            self.assertNotIn(secret, out)
        self.assertIn('SESSION_SALT=[REDACTED:env]', out)
        self.assertIn('export TENANT="[REDACTED:env]"', out)
        for kept in ('APP=web', 'NODE_ENV=production', 'PORT=3000', 'PATH=/usr/local/bin:/bin',
                     'PYTHONPATH=/opt/lib/python3.12/site', 'LOG_LEVEL=debug'):
            self.assertIn(kept, out)
        nested = json.dumps({'r': json.dumps({'out': 'A=1\nTOKEN_Q=9fK2xLq8Zp3Mabc\n'})})
        self.assertNotIn('9fK2xLq8Zp3Mabc', sflog.redact(nested))

    def test_more_sensitive_names(self):
        for text, secret in (('SECRET_KEY=abc', 'abc'), ('PRIVATE_KEY: zzz', 'zzz'), ('db_dsn = mysql-host-x', 'mysql-host-x'),
                             ('passphrase="open sesame"', 'open sesame')):
            self.assertNotIn(secret, sflog.redact(text), text)
        for text in ('"private": true', '{"private": true}', 'password = "[REDACTED:openai-key]"', 'token: null'):
            self.assertEqual(sflog.redact(text), text)

    def test_handoff_leak_examples(self):
        text = ('STRIPE_KEY=sk_live_51HxYzAbCdEfGhIjKlMn\nDATABASE_URL=postgres://app:S3cr3tPass@db/x\n'
                'mongodb+srv://u:pw@c.example.net/d\nnpm_abcdefghijklmnopqrstuvwxyz0123456789\nMY_PRIVATE=hunter2hunter2\n')
        out = sflog.redact(json.dumps({'t': text}))
        for secret in ('sk_live_51Hx', 'S3cr3tPass', 'u:pw@', 'npm_abcdef', 'hunter2hunter2'):
            self.assertNotIn(secret, out)


class GitleaksTests(unittest.TestCase):
    """gitleaks 가 있으면 가린 결과를 한 번 더 훑는다. 가짜 gitleaks 로 출력 형식에 맞춰 본다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.saved = (sflog.sfbackend.which, os.environ.get('HBRNESS_HOME'))
        os.environ['HBRNESS_HOME'] = self.tmp.name

    def tearDown(self):
        sflog.sfbackend.which = self.saved[0]
        os.environ.pop('HBRNESS_HOME', None)
        if self.saved[1] is not None:
            os.environ['HBRNESS_HOME'] = self.saved[1]
        self.tmp.cleanup()

    def fake(self, findings, exit_code=0):
        exe = Path(self.tmp.name) / 'gitleaks'
        exe.write_text(f'#!/bin/sh\ncat > /dev/null\nprintf %s {json.dumps(json.dumps(findings))}\nexit {exit_code}\n')
        exe.chmod(0o755)
        sflog.sfbackend.which = lambda name: str(exe) if name == 'gitleaks' else None

    def test_findings_are_masked_and_json_stays_valid(self):
        self.fake([{'RuleID': 'x', 'Secret': 'Zx9vB2nM4kL6jH8g'}, {'RuleID': 'y', 'Secret': 'a\\/b-Qw7Er5Ty3Ui'},
                   {'RuleID': 'short', 'Secret': 'abc'}])
        chunk = (json.dumps({'t': 'cf Zx9vB2nM4kL6jH8g'}) + '\n' + json.dumps({'t': 'u a/b-Qw7Er5Ty3Ui abc'}) + '\n').encode()
        out = sflog.scrub(chunk, [], sflog.redact_jsonl)
        self.assertNotIn(b'Zx9vB2nM4kL6jH8g', out)
        self.assertNotIn(b'Qw7Er5Ty3Ui', out)
        self.assertEqual([json.loads(l)['t'] for l in out.splitlines()],
                         ['cf [REDACTED:gitleaks]', 'u [REDACTED:gitleaks] abc'])

    def test_missing_or_broken_gitleaks_changes_nothing(self):
        chunk = json.dumps({'t': 'plain'}).encode() + b'\n'
        sflog.sfbackend.which = lambda name: None
        self.assertEqual(sflog.scrub(chunk, [], sflog.redact_jsonl), chunk)
        self.fake('not a list', exit_code=2)
        self.assertEqual(sflog.scrub(chunk, [], sflog.redact_jsonl), chunk)

    @unittest.skipUnless(__import__('shutil').which('gitleaks'), 'gitleaks 가 있을 때만')
    def test_real_gitleaks_catches_what_patterns_miss(self):
        secret = 'SK0123456789abcdef0123456789abcdef'  # twilio — SECRET_PATTERNS 에 없다
        chunk = json.dumps({'t': f'twilio {secret}'}).encode() + b'\n'
        self.assertIn(secret.encode(), sflog.redact_jsonl(chunk))
        self.assertNotIn(secret.encode(), sflog.scrub(chunk, [], sflog.redact_jsonl))


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
        sh(sys.executable, str(SFSTATE), 'init', '--backend', 'local', '--path', str(self.store), '--no-encrypt',
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

    def test_lone_surrogate_in_the_first_message_does_not_break_collect(self):
        t = self.base / 'surrogate.jsonl'
        t.write_text('{"type":"user","message":{"content":"hello \\ud800 world"}}\n')
        self.assertIn('uploaded 1', self.collect('claude', 'sur', t))
        self.assertIn('hello', json.loads((self.remote('claude', 'sur') / 'meta.json').read_text())['title'])

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
        sh(sys.executable, str(SFSTATE), 'init', '--backend', 'local', '--path', str(other), '--no-encrypt',
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


CLAUDE_LINES = [
    {'type': 'mode', 'mode': 'x'},
    {'type': 'user', 'isMeta': True, 'message': {'role': 'user', 'content': '<local-command-caveat>x</local-command-caveat>'}},
    {'type': 'user', 'timestamp': 't1', 'message': {'role': 'user', 'content':
        '<command-name>/clear</command-name><command-message>clear</command-message><command-args></command-args>'}},
    {'type': 'user', 'timestamp': 't2', 'message': {'role': 'user', 'content': '로그인 버그 고쳐줘'}},
    {'type': 'assistant', 'timestamp': 't3', 'message': {'role': 'assistant', 'content': [
        {'type': 'thinking', 'thinking': 'secret thoughts'}, {'type': 'text', 'text': '보겠습니다.'},
        {'type': 'tool_use', 'name': 'Bash', 'input': {'command': 'pytest -q'}}]}},
    {'type': 'user', 'timestamp': 't4', 'message': {'role': 'user', 'content': [
        {'type': 'tool_result', 'content': [{'type': 'text', 'text': '1 failed'}]}]}},
]
CODEX_LINES = [
    {'type': 'session_meta', 'payload': {'cwd': '/x'}},
    {'type': 'response_item', 'timestamp': 't1', 'payload': {'type': 'message', 'role': 'developer', 'content': [{'type': 'input_text', 'text': 'rules'}]}},
    {'type': 'response_item', 'timestamp': 't1', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': '<environment_context>cwd</environment_context>'}]}},
    {'type': 'response_item', 'timestamp': 't2', 'payload': {'type': 'message', 'role': 'user', 'content': [{'type': 'input_text', 'text': '리뷰해줘'}]}},
    {'type': 'response_item', 'timestamp': 't3', 'payload': {'type': 'custom_tool_call', 'name': 'apply_patch', 'input': '*** Begin Patch'}},
    {'type': 'response_item', 'timestamp': 't4', 'payload': {'type': 'custom_tool_call_output', 'output': [{'type': 'text', 'text': 'Done'}]}},
    {'type': 'response_item', 'timestamp': 't5', 'payload': {'type': 'function_call', 'name': 'shell', 'arguments': '{"cmd":"ls"}'}},
    {'type': 'response_item', 'timestamp': 't6', 'payload': {'type': 'function_call_output', 'output': 'a b'}},
    {'type': 'response_item', 'timestamp': 't7', 'payload': {'type': 'message', 'role': 'assistant', 'content': [{'type': 'output_text', 'text': '끝났습니다'}]}},
]
GROK_LINES = [
    {'type': 'system', 'content': 'sys'},
    {'type': 'user', 'content': [{'type': 'text', 'text': '<user_info>\nOS Version: macos\n</user_info>'}]},
    {'type': 'user', 'synthetic_reason': 'system_reminder', 'content': [{'type': 'text', 'text': 'skills'}]},
    {'type': 'user', 'prompt_index': 0, 'content': [{'type': 'text', 'text': '<user_query>\n배포 스크립트 점검\n</user_query>'}]},
    {'type': 'reasoning', 'summary': []},
    {'type': 'assistant', 'content': '확인합니다', 'tool_calls': [{'id': '1', 'name': 'run_terminal_command', 'arguments': '{"command":"ls"}'}]},
    {'type': 'tool_result', 'tool_call_id': '1', 'content': 'deploy.sh'},
]
DEVIN_DOC = {'schema_version': '1', 'session_id': 'd', 'steps': [
    {'source': 'system', 'message': 'sys'},
    {'source': 'user', 'timestamp': 't1', 'message': '테스트 돌려줘'},
    {'source': 'agent', 'timestamp': 't2', 'message': '돌립니다', 'tool_calls': [{'function_name': 'exec', 'arguments': {'command': 'npm test'}}],
     'observation': {'results': [{'source_call_id': 'x', 'content': 'ok'}]}},
]}


def jl(lines):
    return ''.join(json.dumps(l, ensure_ascii=False) + '\n' for l in lines).encode()


class NormaliseTests(unittest.TestCase):
    def roles(self, events):
        return [(e['role'], e['name'] or '', e['text']) for e in events]

    def test_claude(self):
        self.assertEqual(self.roles(sflog.events_from('claude', 'jsonl-segments', jl(CLAUDE_LINES)))[1:], [
            ('user', '', '로그인 버그 고쳐줘'), ('assistant', '', '보겠습니다.'),
            ('tool', 'Bash', '{"command": "pytest -q"}'), ('result', '', '1 failed')])

    def test_codex_skips_developer_and_injected_context(self):
        self.assertEqual(self.roles(sflog.events_from('codex', 'jsonl-segments', jl(CODEX_LINES))), [
            ('user', '', '리뷰해줘'), ('tool', 'apply_patch', '*** Begin Patch'), ('result', '', 'Done'),
            ('tool', 'shell', '{"cmd":"ls"}'), ('result', '', 'a b'), ('assistant', '', '끝났습니다')])

    def test_grok_skips_injected_and_synthetic(self):
        self.assertEqual(self.roles(sflog.events_from('grok', 'jsonl-segments', jl(GROK_LINES))), [
            ('user', '', '<user_query>\n배포 스크립트 점검\n</user_query>'), ('assistant', '', '확인합니다'),
            ('tool', 'run_terminal_command', '{"command":"ls"}'), ('result', '', 'deploy.sh')])

    def test_devin(self):
        self.assertEqual(self.roles(sflog.events_from('devin', 'json-snapshot', json.dumps(DEVIN_DOC).encode())), [
            ('user', '', '테스트 돌려줘'), ('assistant', '', '돌립니다'),
            ('tool', 'exec', '{"command": "npm test"}'), ('result', '', 'ok')])

    def test_injected_blocks_are_dropped_one_by_one(self):
        codex = [{'type': 'response_item', 'payload': {'type': 'message', 'role': 'user', 'content': [
            {'type': 'input_text', 'text': '<environment_context>cwd</environment_context>'},
            {'type': 'input_text', 'text': 'Fix the login bug'}]}}]
        self.assertEqual(self.roles(sflog.events_from('codex', 'jsonl-segments', jl(codex))),
                         [('user', '', 'Fix the login bug')])
        grok = [{'type': 'user', 'content': [{'type': 'text', 'text': '<user_info>OS</user_info>\n배포 점검'}]}]
        self.assertEqual(self.roles(sflog.events_from('grok', 'jsonl-segments', jl(grok))), [('user', '', '배포 점검')])
        only = [{'type': 'user', 'content': [{'type': 'text', 'text': '<system-reminder>never closed'}]}]
        self.assertEqual(sflog.events_from('grok', 'jsonl-segments', jl(only)), [])

    def test_title_applies_line_patterns_before_flattening(self):
        import re
        extra = [('custom', re.compile(r'(?m)^internal-credential-.*$'))]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'c.jsonl'
            f.write_bytes(jl([{'type': 'user', 'message': {'role': 'user', 'content':
                'Here is the credential:\ninternal-credential-demo\nPlease use it.'}}]))
            title = sflog.derive_title('claude', f, extra)
        self.assertNotIn('internal-credential-demo', title)
        self.assertIn('[REDACTED:custom]', title)

    def test_title_respects_whitespace_sensitive_patterns(self):
        import re
        extra = [('custom', re.compile(r'(?m)^    internal-credential-.*$'))]
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'c.jsonl'
            f.write_bytes(jl([{'type': 'user', 'message': {'role': 'user', 'content':
                '    internal-credential-demo\nPlease use it.'}}]))
            title = sflog.derive_title('claude', f, extra)
        self.assertNotIn('internal-credential-demo', title)

    def test_titles(self):
        with tempfile.TemporaryDirectory() as d:
            for tool, name, data, want in (
                    ('claude', 'c.jsonl', jl(CLAUDE_LINES), '로그인 버그 고쳐줘'),
                    ('grok', 'g.jsonl', jl(GROK_LINES), '배포 스크립트 점검'),
                    ('devin', 'd.json', json.dumps(DEVIN_DOC).encode(), '테스트 돌려줘')):
                f = Path(d) / name
                f.write_bytes(data)
                self.assertEqual(sflog.derive_title(tool, f), want)
            f = Path(d) / 'cmd.jsonl'
            f.write_bytes(jl([{'type': 'user', 'message': {'role': 'user', 'content':
                '<command-name>/sessionflow:phase-loop</command-name><command-args>continue</command-args>'}}]))
            self.assertEqual(sflog.derive_title('claude', f), '/sessionflow:phase-loop continue')

    def test_render(self):
        out = sflog.render(sflog.events_from('claude', 'jsonl-segments', jl(CLAUDE_LINES)))
        self.assertIn('### user · t2\n\n로그인 버그 고쳐줘', out)
        self.assertIn('→ Bash: {"command": "pytest -q"}', out)
        self.assertIn('← 1 failed', out)
        self.assertNotIn('secret thoughts', out)
        self.assertNotIn('→ Bash', sflog.render(sflog.events_from('claude', 'jsonl-segments', jl(CLAUDE_LINES)), tools=False))


class ReadCommandTests(CollectEnv):
    def run_log(self, *args, input=None):
        return sh(sys.executable, str(SFLOG), *args, cwd=self.project, env=self.env(), input=input)

    def setUp(self):
        super().setUp()
        for tool, name, data in (('claude', 'c.jsonl', jl(CLAUDE_LINES)), ('codex', 'x.jsonl', jl(CODEX_LINES)),
                                 ('devin', 'd.json', json.dumps(DEVIN_DOC).encode())):
            f = self.base / name
            f.write_bytes(data)
            self.collect(tool, f'{tool}-session-1', f, final=True)

    def test_list_show_search(self):
        out = self.run_log('list')
        self.assertIn('LOGS=github.com/acme/app · 3개', out)
        self.assertIn('로그인 버그 고쳐줘', out)
        self.assertIn('codex   codex-session-1', out)
        self.assertIn('codex-session-1', self.run_log('list', '--tool', 'codex'))
        self.assertNotIn('claude-session-1', self.run_log('list', '--tool', 'codex'))

        shown = self.run_log('show', 'claude-sess')
        self.assertIn('# claude · claude-session-1', shown)
        self.assertIn('→ Bash:', shown)
        target = self.base / 'shown.md'
        self.assertIn('사용자 말 1개', self.run_log('show', 'devin-session-1', '--no-tools', '--out', str(target)))
        self.assertNotIn('→ exec', target.read_text())

        found = self.run_log('search', 'npm test')
        self.assertIn('devin-session-1', found)
        self.assertIn('SEARCH=1개 세션', found)
        self.assertIn('SEARCH=2개 세션', self.run_log('search', '--regex', '버그|리뷰'))

    def test_search_does_not_keep_transcripts_around(self):
        os.environ['HBRNESS_HOME'] = str(self.home)
        try:
            r = sflog.Remote(sflog.sfbackend.LocalBackend(self.store))
            metas = r.sessions('github.com/acme/app')
            for m in metas:
                r.events(m)
            self.assertFalse(any(k == '_raw' for m in metas for k in m))
        finally:
            os.environ.pop('HBRNESS_HOME', None)

    def test_show_needs_a_unique_prefix(self):
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_log('show', 'c')  # claude·codex 둘 다
        self.assertIn('SHOW=ambiguous', cm.exception.stdout)
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.run_log('show', 'nope')
        self.assertIn('SHOW=none', cm.exception.stdout)

    def test_save_redacts_and_lists_as_manual(self):
        out = self.run_log('save', '--title', '웹 채팅 요약', input='# 요약\n\npassword="hunter2 x" 로 접속했다\n')
        sid = out.split('SAVED=')[1].split()[0]
        self.assertIn('웹 채팅 요약', self.run_log('list', '--tool', 'manual'))
        shown = self.run_log('show', sid)
        self.assertIn('[REDACTED:assignment]', shown)
        self.assertNotIn('hunter2', shown)

    def test_save_title_goes_through_gitleaks_too(self):
        secret = 'Zx9vB2nM4kL6jH8gQ1w'
        fake = self.base / 'bin'
        fake.mkdir()
        (fake / 'gitleaks').write_text('#!/bin/sh\ncat > /dev/null\n'
                                       f'printf %s \'[{{"RuleID":"t","Secret":"{secret}"}}]\'\n')
        (fake / 'gitleaks').chmod(0o755)
        env = self.env(PATH=f"{fake}:{os.environ['PATH']}")
        out = sh(sys.executable, str(SFLOG), 'save', '--title', f'key {secret}', cwd=self.project, env=env,
                 input=f'body {secret}\n')
        sid = out.split('SAVED=')[1].split()[0]
        d = self.store / 'logs' / 'github.com/acme/app' / 'manual' / sid
        for f in ('meta.json', 'transcript.md'):
            self.assertNotIn(secret, (d / f).read_text(), f)
        self.assertIn('[REDACTED:gitleaks]', json.loads((d / 'meta.json').read_text())['title'])

    def test_other_repos_need_all_repos(self):
        other = self.base / 'elsewhere'
        other.mkdir()
        out = sh(sys.executable, str(SFLOG), 'list', cwd=other, env=self.env())
        self.assertIn('LOGS=_norepo · 0개', out)
        out = sh(sys.executable, str(SFLOG), 'list', '--all-repos', cwd=other, env=self.env())
        self.assertIn('github.com/acme/app', out)


@unittest.skipUnless(__import__('shutil').which('age'), 'age 가 있을 때만')
class EncryptedCollectTests(CollectEnv):
    """암호화한 저장소: 올라간 object 는 age 암호문이고, list·show 는 풀어서 읽는다."""

    def setUp(self):
        super().setUp()
        self.store = self.base / 'sealed'
        sh(sys.executable, str(SFSTATE), 'init', '--backend', 'local', '--path', str(self.store),
           cwd=self.project, env=self.env())

    def test_segments_and_meta_are_sealed_and_read_back(self):
        t = self.base / 'c.jsonl'
        t.write_bytes(jl(CLAUDE_LINES) + jl([{'type': 'user', 'message': {'content': 'key sk_live_51HxYzAbCdEfGhIjKlMn'}}]))
        self.assertIn('uploaded 1', self.collect('claude', 'enc-1', t, final=True))
        d = self.remote('claude', 'enc-1')
        for f in (d / '000001.jsonl.gz', d / 'meta.json'):
            self.assertTrue(f.read_bytes().startswith(b'age-encryption.org/'), f.name)
        run = lambda *a: sh(sys.executable, str(SFLOG), *a, cwd=self.project, env=self.env())
        self.assertIn('로그인 버그 고쳐줘', run('list'))
        shown = run('show', 'enc-1', '--raw')
        self.assertIn('[REDACTED:stripe-key]', shown)
        self.assertNotIn('sk_live_51Hx', shown)

    def test_pc_without_the_key_can_upload_but_not_read(self):
        (self.home / 'age.key').unlink()
        t = self.base / 'c.jsonl'
        t.write_bytes(jl(CLAUDE_LINES))
        self.assertIn('uploaded 1', self.collect('claude', 'enc-2', t))  # 공개키만으로 암호화한다
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            sh(sys.executable, str(SFLOG), 'show', 'enc-2', cwd=self.project, env=self.env())
        self.assertIn('age.key', cm.exception.stderr + cm.exception.stdout)


class RemoteCacheTests(CollectEnv):
    def open_remote(self):
        os.environ['HBRNESS_HOME'] = str(self.home)  # 캐시 위치 — 각 테스트가 끝에 되돌린다
        be = sflog.sfbackend.LocalBackend(self.store)
        return sflog.Remote(be), be

    def test_parallel_fetches_and_new_versions(self):
        import threading
        saved = os.environ.get('HBRNESS_HOME')
        try:
            r1, be = self.open_remote()
            r2, _ = self.open_remote()
            etag = be.put('logs/x/claude/s/meta.json', b'v1')
            errors = []

            def go(r):
                try:
                    for _ in range(20):
                        self.assertEqual(r.fetch('logs/x/claude/s/meta.json', etag), b'v1')
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
            ts = [threading.Thread(target=go, args=(r,)) for r in (r1, r2, r1, r2)]
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(errors, [])
            etag2 = be.put('logs/x/claude/s/meta.json', b'v2')
            self.assertEqual(r2.fetch('logs/x/claude/s/meta.json', etag2), b'v2')
            cached = list((r1.dir / 'objects' / 'logs/x/claude/s').glob('meta.json@*'))
            self.assertEqual(len(cached), 1)  # 예전 버전은 지운다
            self.assertFalse((r1.dir / 'index.json').exists())
        finally:
            if saved is None:
                os.environ.pop('HBRNESS_HOME', None)
            else:
                os.environ['HBRNESS_HOME'] = saved

    def test_sessions_sort_by_instant_across_offsets(self):
        saved = os.environ.get('HBRNESS_HOME')
        try:
            r, be = self.open_remote()
            for sid, updated in (('a', '2026-10-01T12:00:00+09:00'),   # 03:00Z
                                 ('b', '2026-10-01T04:00:00+00:00'),   # 04:00Z — 더 최근
                                 ('c', '2026-10-01T02:30:00Z')):
                be.put(f'logs/r/claude/{sid}/meta.json', json.dumps({'session_id': sid, 'tool': 'claude',
                                                                      'updated': updated}).encode())
            self.assertEqual([m['session_id'] for m in r.sessions('r')], ['b', 'a', 'c'])
            self.assertGreater(sflog.instant('2026-10-01T04:00:00+00:00'), sflog.instant('2026-10-01T12:00:00+09:00'))
        finally:
            if saved is None:
                os.environ.pop('HBRNESS_HOME', None)
            else:
                os.environ['HBRNESS_HOME'] = saved


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
