import datetime as dt
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
                    GROK_HOME=str(self.base / 'grok'), HBRNESS_CREDENTIALS_STORE='file',
                    **{'HBRNESS_LOG_BATCH_BYTES': '0', **extra})  # 모아 올리기는 BatchTests 에서만

    def collect(self, tool, session, transcript='', final=False):
        args = [sys.executable, str(SFLOG), 'collect', '--tool', tool, '--session', session,
                '--transcript', str(transcript), '--cwd', str(self.project)]
        return sh(*args + (['--final'] if final else []), cwd=self.project, env=self.env())

    def remote(self, tool, session):
        return self.store / 'logs' / 'github.com/acme/app' / tool / session

    def meta_file(self, tool, session, store=None):
        return (store or self.store) / 'logs' / '_meta' / 'github.com/acme/app' / tool / f'{session}.json'

    def segments(self, tool, session):
        """읽는 쪽과 같이 meta.json 의 세대만."""
        d = self.remote(tool, session)
        gen = json.loads(self.meta_file(tool, session).read_text()).get('generation')
        names = sflog.latest_segments([f.name for f in d.glob('*.jsonl.gz')], gen)
        return b''.join(gzip.decompress((d / n).read_bytes()) for n in names)


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
        meta = json.loads((self.meta_file('claude', 's1')).read_text())
        self.assertEqual((meta['tool'], meta['repo_key'], meta['branch'], meta['segments'], meta['ended']),
                         ('claude', 'github.com/acme/app', 'main', 2, None))
        self.collect('claude', 's1', t, final=True)
        self.assertIsNotNone(json.loads((self.meta_file('claude', 's1')).read_text())['ended'])

    def test_final_uploads_an_unterminated_last_line(self):
        t = self.base / 'codex.jsonl'
        t.write_text('{"a":1}\n{"b":2}')
        self.collect('codex', 's2', t)
        self.collect('codex', 's2', t, final=True)
        self.assertEqual(self.segments('codex', 's2'), b'{"a":1}\n{"b":2}')

    def test_rewritten_transcript_starts_a_new_generation(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"old":1}\n{"old":2}\n')
        self.collect('claude', 's3', t)
        t.write_text('{"new":1}\n{"new":2}\n{"new":3}\n')  # 더 길어졌지만 앞부분이 다르다
        self.collect('claude', 's3', t)
        d = self.remote('claude', 's3')
        self.assertEqual(sorted(f.name for f in d.glob('*.jsonl.gz')), ['000001.jsonl.gz', 'g2-000001.jsonl.gz'])
        self.assertEqual(self.segments('claude', 's3'), b'{"new":1}\n{"new":2}\n{"new":3}\n')  # 예전 세대는 안 읽는다
        meta = json.loads(self.meta_file('claude', 's3').read_text())
        self.assertEqual((meta['rewrites'], meta['generation'], meta['segments']), (1, 2, 1))
        shown = sh(sys.executable, str(SFLOG), 'show', 's3', '--raw', cwd=self.project, env=self.env())
        self.assertNotIn('old', shown)
        self.assertEqual(sflog.latest_segments(['000002.jsonl.gz', 'g10-000001.jsonl.gz', 'g9-000003.jsonl.gz',
                                                'g10-000002.jsonl.gz', 'meta.json', 'g0-000001.jsonl.gz'], 10),
                         ['g10-000001.jsonl.gz', 'g10-000002.jsonl.gz'])
        # generation 이 없는 1.3 meta 는 1세대 — 그 뒤에 일부만 올라간 g2 를 읽지 않는다
        self.assertEqual(sflog.latest_segments(['000001.jsonl.gz', '000002.jsonl.gz', 'g2-000001.jsonl.gz'], None),
                         ['000001.jsonl.gz', '000002.jsonl.gz'])
        self.assertEqual(sflog.latest_segments(['000001.jsonl.gz', 'g2-000001.jsonl.gz'], 3), [])  # 빈 세대
        self.assertEqual(sflog.latest_segments(['000001.jsonl.gz', 'g2-000001.jsonl.gz'], 1), ['000001.jsonl.gz'])
        t.write_text('{"x":1}\n')  # 줄었다
        self.collect('claude', 's3', t)
        self.assertEqual(self.segments('claude', 's3'), b'{"x":1}\n')
        self.assertEqual(json.loads(self.meta_file('claude', 's3').read_text())['generation'], 3)

    def test_rewritten_to_empty_reads_empty(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"old":1}\n')
        self.collect('claude', 'empty', t)
        t.write_text('')
        self.collect('claude', 'empty', t, final=True)
        shown = sh(sys.executable, str(SFLOG), 'show', 'empty', '--raw', cwd=self.project, env=self.env())
        self.assertNotIn('old', shown)
        d = self.base / 'd.json'
        d.write_text(json.dumps({'steps': [{'source': 'user', 'message': 'old step'}, {'source': 'agent', 'message': 'x'}]}))
        self.collect('devin', 'dempty', d, final=True)
        d.write_text(json.dumps({'steps': []}))
        self.collect('devin', 'dempty', d, final=True)
        self.assertNotIn('old step', sh(sys.executable, str(SFLOG), 'show', 'dempty', cwd=self.project, env=self.env()))

    def test_lost_state_starts_above_what_is_there(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n')
        self.collect('claude', 'lost', t)
        t.write_text('{"a":1}\n{"a":2}\n')
        self.collect('claude', 'lost', t)  # 1세대 segment 두 개
        for f in (self.home / 'logs' / 'sessions').glob('claude-lost.*'):
            f.unlink()
        t.write_text('{"b":1}\n')
        self.collect('claude', 'lost', t)
        self.assertEqual(self.segments('claude', 'lost'), b'{"b":1}\n')  # 남은 000002 가 섞이지 않는다
        self.assertTrue((self.remote('claude', 'lost') / 'g2-000001.jsonl.gz').exists())

    def test_rewrite_noticed_before_its_first_line_is_complete_bumps_once(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"old":1}\n{"old":2}\n')
        self.collect('claude', 'half', t)
        t.write_text('{"new":1')  # 다시 쓰는 중 — 첫 줄도 아직 덜 썼다
        self.assertIn('nochange', self.collect('claude', 'half', t))
        t.write_text('{"new":1}\n{"new":2}\n')
        self.collect('claude', 'half', t)
        meta = json.loads((self.meta_file('claude', 'half')).read_text())
        self.assertEqual((meta['rewrites'], meta['generation']), (1, 2))
        self.assertEqual(self.segments('claude', 'half'), b'{"new":1}\n{"new":2}\n')

    def test_grok_transcript_is_found_from_session_and_cwd(self):
        import urllib.parse
        d = self.base / 'grok' / 'sessions' / urllib.parse.quote(str(self.project), safe='') / 'g-1'
        d.mkdir(parents=True)
        (d / 'chat_history.jsonl').write_text('{"role":"user"}\n')
        self.assertIn('COLLECT=uploaded 1', self.collect('grok', 'g-1'))
        self.assertEqual(self.segments('grok', 'g-1'), b'{"role":"user"}\n')

    def test_devin_steps_are_uploaded_as_they_grow(self):
        t = self.base / 'north-mandible.json'
        step = lambda n, text='': {'step_id': n, 'source': 'user' if n % 2 else 'agent', 'message': text or f'm{n}'}
        write = lambda steps: t.write_text(json.dumps({'schema_version': 'ATIF-v1.7', 'steps': steps}))
        write([step(1), step(2)])
        self.assertIn('uploaded 1', self.collect('devin', 'd-1', t))  # 마지막 step 은 아직 채워지는 중일 수 있다
        self.assertIn('nochange', self.collect('devin', 'd-1', t))
        write([step(1), step(2), step(3, 'key ghp_' + 'x' * 36)])
        self.assertIn('uploaded 1', self.collect('devin', 'd-1', t))
        self.assertIn('uploaded 1', self.collect('devin', 'd-1', t, final=True))
        lines = [json.loads(l) for l in self.segments('devin', 'd-1').splitlines()]
        self.assertEqual([l['step_id'] for l in lines], [1, 2, 3])
        self.assertIn('[REDACTED:github-token]', lines[2]['message'])
        self.assertFalse((self.remote('devin', 'd-1') / 'transcript.json.gz').exists())

        write([step(1, 'edited'), step(2), step(3), step(4)])  # 이미 올린 step 이 바뀌었다 — 새 세대
        self.collect('devin', 'd-1', t, final=True)
        meta = json.loads((self.meta_file('devin', 'd-1')).read_text())
        self.assertEqual((meta['format'], meta['generation']), ('jsonl-segments', 2))
        self.assertEqual([json.loads(l)['message'] for l in self.segments('devin', 'd-1').splitlines()],
                         ['edited', 'm2', 'm3', 'm4'])

    def test_half_written_devin_json_is_skipped_not_uploaded(self):
        t = self.base / 'd.json'
        doc = json.dumps({'steps': [{'source': 'user', 'message': '세션 질문'}, {'source': 'agent', 'message': '답'}]})
        t.write_text(doc)
        self.collect('devin', 'half', t)
        t.write_text('{"steps":[')  # 제자리에서 다시 쓰는 중
        self.assertIn('partial', self.collect('devin', 'half', t))
        self.assertFalse((self.remote('devin', 'half') / 'transcript.json.gz').exists())
        t.write_text(doc)
        self.assertIn('uploaded 1', self.collect('devin', 'half', t, final=True))
        meta = json.loads((self.meta_file('devin', 'half')).read_text())
        self.assertEqual(meta['format'], 'jsonl-segments')
        self.assertIn('세션 질문', sh(sys.executable, str(SFLOG), 'show', 'half', cwd=self.project, env=self.env()))

    def test_json_without_steps_is_still_a_snapshot(self):
        t = self.base / 'other.json'
        t.write_text('{"messages": ["ghp_' + 'x' * 36 + '"]}')
        self.assertIn('uploaded 1', self.collect('devin', 'd-2', t))
        self.assertIn('nochange', self.collect('devin', 'd-2', t))
        snap = gzip.decompress((self.remote('devin', 'd-2') / 'transcript.json.gz').read_bytes())
        self.assertIn(b'[REDACTED:github-token]', snap)

    def test_lone_surrogate_in_the_first_message_does_not_break_collect(self):
        t = self.base / 'surrogate.jsonl'
        t.write_text('{"type":"user","message":{"content":"hello \\ud800 world"}}\n')
        self.assertIn('uploaded 1', self.collect('claude', 'sur', t))
        self.assertIn('hello', json.loads((self.meta_file('claude', 'sur')).read_text())['title'])

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
        self.saved = {k: os.environ.get(k) for k in ('HBRNESS_HOME', 'HBRNESS_STATE_DIR', 'HBRNESS_LOG_BATCH_BYTES')}
        os.environ.update(HBRNESS_HOME=str(self.home), HBRNESS_STATE_DIR=str(self.home / 'state'),
                          HBRNESS_LOG_BATCH_BYTES='0')

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
                if key.startswith('logs/_meta/') and fail['meta']:
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
        meta = json.loads((self.meta_file('claude', 'm')).read_text())
        self.assertEqual(meta['segments'], 2)


    def flaky_puts(self, fail_on):
        """fail_on(key, n) 이 참이면 n 번째 segment put 을 실패시키는 backend 로 바꿔 끼운다. 되돌리는 함수를 준다."""
        sfstate_mod = sflog.sfstate
        real = sfstate_mod.load_backend
        count = {'n': 0}

        def flaky():
            be = real()
            put = be.put

            def put_(key, data, **kw):
                if key.endswith('.jsonl.gz'):
                    count['n'] += 1
                    if fail_on(key, count['n']):
                        raise sflog.sfbackend.BackendError('segment down')
                return put(key, data, **kw)
            be.put = put_
            return be
        sfstate_mod.load_backend = flaky
        return lambda: setattr(sfstate_mod, 'load_backend', real)

    def meta(self, tool, session):
        return json.loads((self.meta_file(tool, session)).read_text())

    def test_half_uploaded_generation_is_never_published(self):
        t = self.base / 'd.json'
        steps = [{'source': 'user', 'message': f'v1 step {i}'} for i in range(3)]
        t.write_text(json.dumps({'steps': steps}))
        sflog.collect('devin', 'pub', str(t), str(self.project), final=True)
        new = [{'source': 'user', 'message': f'v2 step {i}'} for i in range(3)]
        t.write_text(json.dumps({'steps': new}))
        old = sflog.SEGMENT_MAX
        sflog.SEGMENT_MAX = 1  # step 하나가 segment 하나
        undo = self.flaky_puts(lambda key, n: n == 2)  # 새 세대의 두 번째 segment 에서 끊긴다
        try:
            with self.assertRaises(sflog.sfbackend.BackendError):
                sflog.collect('devin', 'pub', str(t), str(self.project), final=True)
        finally:
            undo()
            sflog.SEGMENT_MAX = old
        t.write_text('{"steps":[')  # 다음 수집 때는 반쯤 쓴 파일
        self.assertEqual(sflog.collect('devin', 'pub', str(t), str(self.project), final=True), 'partial')
        meta = self.meta('devin', 'pub')
        self.assertEqual((meta['generation'], meta['format']), (1, 'jsonl-segments'))
        self.assertIn(b'v1 step 2', self.segments('devin', 'pub'))
        t.write_text(json.dumps({'steps': new}))
        sflog.collect('devin', 'pub', str(t), str(self.project), final=True)
        self.assertEqual(self.meta('devin', 'pub')['generation'], 2)
        self.assertEqual([json.loads(l)['message'] for l in self.segments('devin', 'pub').splitlines()],
                         ['v2 step 0', 'v2 step 1', 'v2 step 2'])

    def test_partial_after_lost_state_leaves_remote_meta_alone(self):
        t = self.base / 'd.json'
        t.write_text(json.dumps({'steps': [{'source': 'user', 'message': 'kept'}, {'source': 'agent', 'message': 'x'}]}))
        sflog.collect('devin', 'lostp', str(t), str(self.project), final=True)
        before = self.meta('devin', 'lostp')
        for f in (self.home / 'logs' / 'sessions').glob('devin-lostp.*'):
            f.unlink()
        t.write_text('{"steps":[')
        self.assertEqual(sflog.collect('devin', 'lostp', str(t), str(self.project), final=True), 'partial')
        self.assertEqual(self.meta('devin', 'lostp'), before)

    def test_retry_after_a_failed_upload_is_not_batched(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n{"a":2}\n')
        sflog.collect('claude', 'retry', str(t), str(self.project))  # 1세대를 냈다
        t.write_text('{"b":1}\n{"b":2}\n')  # 다시 쓰였다
        old = sflog.SEGMENT_MAX
        sflog.SEGMENT_MAX = 8
        undo = self.flaky_puts(lambda key, n: n == 2)
        try:
            with self.assertRaises(sflog.sfbackend.BackendError):
                sflog.collect('claude', 'retry', str(t), str(self.project))
        finally:
            undo()
            sflog.SEGMENT_MAX = old
        os.environ['HBRNESS_LOG_BATCH_BYTES'] = '65536'  # 모아 올리기를 켜도
        try:
            self.assertEqual(sflog.collect('claude', 'retry', str(t), str(self.project)), 'uploaded 1')
        finally:
            os.environ['HBRNESS_LOG_BATCH_BYTES'] = '0'
        self.assertEqual(self.meta('claude', 'retry')['generation'], 2)
        self.assertEqual(self.segments('claude', 'retry'), b'{"b":1}\n{"b":2}\n')

    def test_first_rewrite_after_upgrade_keeps_old_meta_readable(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n{"a":2}\n')
        sflog.collect('claude', 'up', str(t), str(self.project))
        d = self.remote('claude', 'up')
        meta = self.meta('claude', 'up')
        del meta['generation']  # 1.3 이 쓴 meta
        self.meta_file('claude', 'up').write_text(json.dumps(meta))
        t.write_text('{"b":1}\n{"b":2}\n')
        old = sflog.SEGMENT_MAX
        sflog.SEGMENT_MAX = 8
        undo = self.flaky_puts(lambda key, n: n == 2)
        try:
            with self.assertRaises(sflog.sfbackend.BackendError):
                sflog.collect('claude', 'up', str(t), str(self.project))
        finally:
            undo()
            sflog.SEGMENT_MAX = old
        self.assertTrue((d / 'g2-000001.jsonl.gz').exists())
        shown = sh(sys.executable, str(SFLOG), 'show', 'up', '--raw', cwd=self.project, env=self.env())
        self.assertIn('"a":2', shown.replace(' ', ''))
        self.assertNotIn('"b"', shown)


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
        self.assertEqual(sorted(f.name for f in d.iterdir()), ['000001.jsonl.gz'])
        self.assertEqual(json.loads(self.meta_file('claude', 'sw', other).read_text())['segments'], 1)

    def test_session_end_is_published_even_without_the_transcript(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"a":1}\n')
        self.collect('claude', 'gone', t)
        t.unlink()
        self.assertIn('no-transcript', self.collect('claude', 'gone', t, final=True))
        self.assertIsNotNone(json.loads((self.meta_file('claude', 'gone')).read_text())['ended'])


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
        for f in (self.meta_file('manual', sid), d / 'transcript.md'):
            self.assertNotIn(secret, f.read_text(), f)
        self.assertIn('[REDACTED:gitleaks]', json.loads(self.meta_file('manual', sid).read_text())['title'])

    def test_other_repos_need_all_repos(self):
        other = self.base / 'elsewhere'
        other.mkdir()
        out = sh(sys.executable, str(SFLOG), 'list', cwd=other, env=self.env())
        self.assertIn('LOGS=_norepo · 0개', out)
        out = sh(sys.executable, str(SFLOG), 'list', '--all-repos', cwd=other, env=self.env())
        self.assertIn('github.com/acme/app', out)


class BatchTests(CollectEnv):
    """turn 마다 작은 segment 가 쌓이지 않게 모아 올린다."""

    def batched(self, tool, session, transcript, final=False, seconds='300'):
        args = [sys.executable, str(SFLOG), 'collect', '--tool', tool, '--session', session,
                '--transcript', str(transcript), '--cwd', str(self.project)] + (['--final'] if final else [])
        return sh(*args, cwd=self.project, env=self.env(HBRNESS_LOG_BATCH_BYTES='65536',
                                                        HBRNESS_LOG_BATCH_SECONDS=seconds))

    def test_small_turns_wait_until_enough_or_session_end(self):
        t = self.base / 'c.jsonl'
        t.write_bytes(jl(CLAUDE_LINES))
        self.assertIn('uploaded 1', self.batched('claude', 'b', t))  # 첫 segment 는 바로 — list 에 바로 보이게
        with open(t, 'ab') as fh:
            fh.write(jl([{'type': 'user', 'message': {'content': 'small turn'}}]))
        self.assertIn('nochange', self.batched('claude', 'b', t))  # 작고 5분 안 — 미룬다
        status = sh(sys.executable, str(SFLOG), 'status', cwd=self.project, env=self.env())
        self.assertIn('WAITING=1', status)
        with open(t, 'ab') as fh:
            fh.write(jl([{'type': 'user', 'message': {'content': 'x' * 70000}}]))
        self.assertIn('uploaded 1', self.batched('claude', 'b', t))  # 64KB 를 넘었다
        with open(t, 'ab') as fh:
            fh.write(jl([{'type': 'user', 'message': {'content': 'last words'}}]))
        self.assertIn('nochange', self.batched('claude', 'b', t))
        self.assertIn('uploaded 1', self.batched('claude', 'b', t, final=True))  # 세션 끝은 바로
        self.assertTrue(self.segments('claude', 'b').endswith(jl([{'type': 'user', 'message': {'content': 'last words'}}])))
        self.assertIn('WAITING=0', sh(sys.executable, str(SFLOG), 'status', cwd=self.project, env=self.env()))

    def test_waits_at_most_the_batch_time(self):
        t = self.base / 'c.jsonl'
        t.write_bytes(jl(CLAUDE_LINES))
        self.batched('claude', 't', t)
        with open(t, 'ab') as fh:
            fh.write(b'{"small":1}\n')
        self.assertIn('uploaded 1', self.batched('claude', 't', t, seconds='0'))  # 마지막으로 올린 지 오래됐다

    def test_devin_steps_batch_too(self):
        t = self.base / 'd.json'
        step = lambda n: {'source': 'user' if n % 2 else 'agent', 'message': f'm{n}'}
        t.write_text(json.dumps({'steps': [step(1), step(2)]}))
        self.assertIn('uploaded 1', self.batched('devin', 'dv', t))
        t.write_text(json.dumps({'steps': [step(1), step(2), step(3), step(4)]}))
        self.assertIn('nochange', self.batched('devin', 'dv', t))
        self.assertIn('uploaded 1', self.batched('devin', 'dv', t, final=True))
        self.assertEqual(len(self.segments('devin', 'dv').splitlines()), 4)


class StatusAndReadingTests(CollectEnv):
    def run_log(self, *args):
        return sh(sys.executable, str(SFLOG), *args, cwd=self.project, env=self.env())

    def test_status_reports_failures_and_tools(self):
        t = self.base / 'c.jsonl'
        t.write_bytes(jl(CLAUDE_LINES))
        self.collect('claude', 's', t)
        log = self.home / 'logs' / 'collect.log'
        old = (dt.datetime.now().astimezone() - dt.timedelta(days=3)).isoformat(timespec='seconds')
        log.write_text(f'{old} collect claude x: old failure\n{sflog.now_iso()} collect claude s: 목록 실패\n')
        out = self.run_log('status')
        for line in ('BACKEND=local:', 'SESSIONS=1 (진행 중 1)', 'FAILURES_24H=1', '목록 실패', 'AGE=', 'GITLEAKS='):
            self.assertIn(line, out)
        self.assertNotIn('old failure', out)

    def test_quiet_unended_sessions_look_dropped(self):
        now = dt.datetime.now(dt.timezone.utc)
        base = {'tool': 'claude', 'session_id': 's', 'segments': 1}
        self.assertIn('진행 중', sflog.meta_line({**base, 'updated': now.isoformat()}))
        old = (now - dt.timedelta(hours=13)).isoformat()
        self.assertIn('끊김(추정)', sflog.meta_line({**base, 'updated': old}))
        self.assertNotIn('끊김', sflog.meta_line({**base, 'updated': old, 'ended': old}))

    def test_unknown_records_are_counted_not_shown(self):
        lines = CLAUDE_LINES + [{'type': 'assistant', 'timestamp': 't9', 'message': {'role': 'assistant', 'content': [
            {'type': 'server_tool_use', 'name': 'web_search'}, {'type': 'thinking', 'thinking': 'hidden'}]}},
            {'type': 'attachment', 'x': 1}]
        t = self.base / 'c.jsonl'
        t.write_bytes(jl(lines))
        self.collect('claude', 'u', t, final=True)
        shown = self.run_log('show', 'u')
        self.assertIn('읽지 못한 레코드: assistant.server_tool_use×1', shown)
        self.assertNotIn('attachment', shown)  # 메타데이터 레코드는 세지 않는다
        self.assertNotIn('hidden', shown)
        codex = [{'type': 'response_item', 'payload': {'type': 'web_search_call'}},
                 {'type': 'response_item', 'payload': {'type': 'reasoning'}}]
        self.assertEqual(sflog.unknown_summary(sflog.events_from('codex', 'jsonl-segments', jl(codex))),
                         'response_item.web_search_call×1')
        grok = [{'type': 'backend_tool_call', 'kind': "{'tool_type': 'web_search'}"}, {'type': 'brand_new'}]
        evs = sflog.events_from('grok', 'jsonl-segments', jl(grok))
        self.assertEqual([e['role'] for e in evs], ['tool', 'unknown'])
        devin = {'steps': [{'source': 'robot', 'message': 'x'}, {'source': 'system', 'message': 'y'}]}
        self.assertEqual(sflog.unknown_summary(sflog.events_from('devin', 'json-snapshot', json.dumps(devin).encode())),
                         'step.robot×1')

    def test_cache_is_trimmed_oldest_first(self):
        saved = os.environ.get('HBRNESS_HOME')
        os.environ['HBRNESS_HOME'] = str(self.home)
        try:
            r = sflog.Remote(sflog.sfbackend.LocalBackend(self.store))
            objs = r.dir / 'objects' / 'x'
            objs.mkdir(parents=True)
            for i in range(10):
                f = objs / f'{i}@e'
                f.write_bytes(b'z' * 200_000)
                os.utime(f, (1000 + i, 1000 + i))
            self.assertEqual(r.trim(cap_mb=1), 6)  # 2MB → 0.8MB 까지
            self.assertEqual(sorted(f.name for f in objs.iterdir()), [f'{i}@e' for i in range(6, 10)])
            self.assertEqual(r.trim(cap_mb=1), 0)
            busy = objs / '.tmp-123-abcd'  # 다른 명령이 쓰는 중
            busy.write_bytes(b'z' * 300_000)
            os.utime(busy, (1, 1))
            r.trim(cap_mb=0)
            self.assertTrue(busy.exists())
            etag = r.be.put('logs/x/claude/s/000001.jsonl.gz', b'v1')
            real = sflog.os.replace
            sflog.os.replace = lambda a, b: (_ for _ in ()).throw(FileNotFoundError(a))  # 그사이 치워졌다
            try:
                self.assertEqual(r.fetch('logs/x/claude/s/000001.jsonl.gz', etag), b'v1')
            finally:
                sflog.os.replace = real
        finally:
            os.environ.pop('HBRNESS_HOME', None)
            if saved is not None:
                os.environ['HBRNESS_HOME'] = saved


class BackAndForthTests(CollectEnv):
    def test_returning_to_a_backend_reads_the_new_content(self):
        t = self.base / 'c.jsonl'
        t.write_text('{"v":1}\n')
        self.collect('claude', 'ab', t)
        t.write_text('{"v":2}\n')  # A 에 2세대
        self.collect('claude', 'ab', t)
        init = lambda store: sh(sys.executable, str(SFSTATE), 'init', '--backend', 'local', '--path', str(store),
                                '--no-encrypt', cwd=self.project, env=self.env())
        init(self.base / 'store-b')
        t.write_text('{"v":3}\n')
        self.collect('claude', 'ab', t)
        init(self.store)  # A 로 돌아온다
        t.write_text('{"v":4}\n')
        self.assertIn('uploaded 1', self.collect('claude', 'ab', t))
        self.assertEqual(self.segments('claude', 'ab'), b'{"v":4}\n')
        shown = sh(sys.executable, str(SFLOG), 'show', 'ab', '--raw', cwd=self.project, env=self.env())
        self.assertIn('"v":4', shown.replace(' ', ''))
        self.assertNotIn('"v":2', shown.replace(' ', ''))


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
        for f in (d / '000001.jsonl.gz', self.meta_file('claude', 'enc-1')):
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


class IndexedSearchTests(CollectEnv):
    """list 는 logs/_meta/ 만 LIST 하고, search 는 로컬 색인에 바뀐 세션만 넣는다."""

    def setUp(self):
        super().setUp()
        self.saved = os.environ.get('HBRNESS_HOME')
        os.environ['HBRNESS_HOME'] = str(self.home)
        for tool, name, data in (('claude', 'c.jsonl', jl(CLAUDE_LINES)), ('codex', 'x.jsonl', jl(CODEX_LINES)),
                                 ('devin', 'd.json', json.dumps(DEVIN_DOC).encode())):
            f = self.base / name
            f.write_bytes(data)
            self.collect(tool, f'{tool}-session-1', f, final=True)

    def tearDown(self):
        os.environ.pop('HBRNESS_HOME', None)
        if self.saved is not None:
            os.environ['HBRNESS_HOME'] = self.saved
        super().tearDown()

    def counting(self):
        be = sflog.sfbackend.LocalBackend(self.store)
        calls = {'list': [], 'get': []}
        real_list, real_get = be.list, be.get_raw
        be.list = lambda prefix: calls['list'].append(prefix) or real_list(prefix)
        be.get_raw = lambda key: calls['get'].append(key) or real_get(key)
        return be, calls

    def search(self, query, *extra):
        return sh(sys.executable, str(SFLOG), 'search', query, *extra, cwd=self.project, env=self.env())

    def test_list_reads_only_the_meta_prefix(self):
        be, calls = self.counting()
        sflog.Remote(be).sessions('github.com/acme/app')
        self.assertEqual(calls['list'], ['logs/', 'logs/_meta/github.com/acme/app/'])  # 처음 한 번은 예전 meta 옮기기
        be, calls = self.counting()
        metas = sflog.Remote(be).sessions('github.com/acme/app')
        self.assertEqual(len(metas), 3)
        self.assertEqual(calls['list'], ['logs/_meta/github.com/acme/app/'])
        self.assertTrue(all(k.startswith('logs/_meta/') for k in calls['get']))
        self.assertEqual(metas[0]['_dir'].count('/'), 5)  # logs/<host>/<owner>/<repo>/<tool>/<id>

    def sigs(self):
        r = sflog.Remote(sflog.sfbackend.LocalBackend(self.store))
        idx = sflog.Index(r.dir / 'index.sqlite')
        try:
            return idx.sigs()
        finally:
            idx.close()

    def search_in_process(self, query):
        """같은 프로세스에서 search 를 돌려 backend 호출을 센다."""
        import contextlib
        import io
        be, calls = self.counting()
        real = sflog.sfstate.load_backend
        sflog.sfstate.load_backend = lambda: be
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                sflog.main(['search', query, '--dir', str(self.project)])
        finally:
            sflog.sfstate.load_backend = real
        return out.getvalue(), calls

    def test_search_indexes_only_changed_sessions(self):
        self.assertIn('SEARCH=1개 세션', self.search('npm test'))
        metas = sflog.Remote(sflog.sfbackend.LocalBackend(self.store)).sessions('github.com/acme/app')
        self.assertEqual(self.sigs(), {m['_dir']: m['_etag'] for m in metas})
        out, calls = self.search_in_process('npm test')  # 그대로면 색인만 본다
        self.assertIn('SEARCH=1개 세션', out)
        self.assertEqual(calls['list'], ['logs/_meta/github.com/acme/app/'])
        self.assertEqual(calls['get'], [])  # meta 는 캐시, transcript 는 색인

        before = self.sigs()
        t = self.base / 'c.jsonl'
        with open(t, 'ab') as fh:
            fh.write(jl([{'type': 'user', 'timestamp': 't9', 'message': {'role': 'user', 'content': '새로 추가한 질문'}}]))
        self.collect('claude', 'claude-session-1', t, final=True)
        out, calls = self.search_in_process('추가한 질문')
        self.assertIn('SEARCH=1개 세션', out)
        self.assertEqual([p for p in calls['list'] if not p.startswith('logs/_meta/')],
                         ['logs/github.com/acme/app/claude/claude-session-1/'])  # 바뀐 세션만 다시 읽는다
        after = self.sigs()
        self.assertEqual({d for d in after if after[d] != before.get(d)},
                         {d for d in after if d.endswith('/claude/claude-session-1')})

    def test_short_regex_tool_filters_and_bad_regex(self):
        self.assertIn('SEARCH=2개 세션', self.search('--regex', '버그|리뷰'))
        self.assertIn('SEARCH=1개 세션', self.search('버그'))  # 2글자 — trigram 대신 훑는다
        self.assertIn('SEARCH=0개 세션', self.search('버그', '--tool', 'codex'))
        self.assertIn('SEARCH=1개 세션', self.search('NPM TEST'))  # 대소문자 무시
        with self.assertRaises(subprocess.CalledProcessError) as cm:
            self.search('--regex', '(')
        self.assertIn('SEARCH=failed', cm.exception.stdout)

    def test_same_results_without_fts(self):
        r = sflog.Remote(sflog.sfbackend.LocalBackend(self.store))
        metas = r.sessions('github.com/acme/app')
        dirs = [m['_dir'] for m in metas]
        results = []
        for fts in (True, False):
            idx = sflog.Index(self.base / f'idx-{fts}.sqlite')
            try:
                idx.fts = idx.fts and fts
                for m in metas:
                    idx.update(m['_dir'], m['_etag'], r.events(m))
                results.append({d: [h[:3] for h in v] for d, v in idx.hits('npm test', False, dirs).items()})
            finally:
                idx.close()
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(results[0]), 1)

    def fts_ok(self, idx):
        idx.db.execute("INSERT INTO ev_fts(ev_fts, rank) VALUES('integrity-check', 1)")

    def test_writers_are_serialised_and_fts_stays_consistent(self):
        import sqlite3
        import threading
        path = self.base / 'race.sqlite'
        a, b = sflog.Index(path), sflog.Index(path)
        try:
            ev = lambda t: [{'role': 'user', 'name': None, 'text': t}]
            a.update('logs/r/claude/s', 'v1', ev('first text'))
            with a.write():  # A 가 지울 행을 읽는 중
                a.db.execute("SELECT id, ftext FROM ev WHERE dir = 'logs/r/claude/s'").fetchall()
                b.db.execute('PRAGMA busy_timeout = 100')
                with self.assertRaises(sqlite3.OperationalError):  # B 는 A 가 끝날 때까지 쓰지 못한다
                    b.update('logs/r/claude/s', 'v2', ev('second text'))
            b.db.execute('PRAGMA busy_timeout = 30000')

            errors = []

            def churn(tag):  # 연결은 thread 마다 따로
                idx = sflog.Index(path)
                try:
                    for i in range(30):
                        idx.update('logs/r/claude/s', f'{tag}{i}', ev(f'{tag} text number {i}'))
                except Exception as e:  # noqa: BLE001
                    errors.append(e)
                finally:
                    idx.close()
            ts = [threading.Thread(target=churn, args=(n,)) for n in ('aa', 'bb', 'cc')]
            [t.start() for t in ts]
            [t.join() for t in ts]
            self.assertEqual(errors, [])
            self.fts_ok(a)
            self.assertEqual(a.db.execute('SELECT count(*) FROM ev').fetchone()[0], 1)
        finally:
            a.close()
            b.close()

    def test_rows_added_without_fts_are_indexed_once_fts_appears(self):
        path = self.base / 'later.sqlite'
        real = sflog.fts_available
        sflog.fts_available = lambda: False
        try:
            idx = sflog.Index(path)
            idx.update('logs/r/claude/s', 'v1', [{'role': 'user', 'name': None, 'text': 'hello world'}])
            idx.close()
        finally:
            sflog.fts_available = real
        idx = sflog.Index(path)
        try:
            self.assertTrue(idx.fts)
            self.assertIn('logs/r/claude/s', idx.hits('hello', False, ['logs/r/claude/s']))  # FTS 로 찾는다
            idx.update('logs/r/claude/s', 'v2', [{'role': 'user', 'name': None, 'text': 'bye now'}])
            self.fts_ok(idx)
            self.assertEqual(idx.hits('hello', False, ['logs/r/claude/s']), {})
        finally:
            idx.close()

    def test_legacy_meta_is_moved_once(self):
        be = sflog.sfbackend.LocalBackend(self.store)
        legacy = {'tool': 'claude', 'session_id': 'old-1', 'updated': '2026-10-01T00:00:00+09:00', 'format': 'jsonl-segments',
                  'segments': 1, 'title': '1.4 때 세션'}
        be.put('logs/github.com/acme/app/claude/old-1/meta.json', json.dumps(legacy).encode())
        be.put('logs/github.com/acme/app/claude/old-1/000001.jsonl.gz', gzip.compress(jl(CLAUDE_LINES)))
        be.put('logs/_norepo/manual/m-1/meta.json', json.dumps({**legacy, 'tool': 'manual', 'session_id': 'm-1',
                                                                 'format': 'markdown'}).encode())
        be.put('logs/_norepo/manual/m-1/transcript.md', b'# note')
        cache = self.home / 'logs' / 'cache'
        for f in cache.glob('*/legacy-meta-migrated'):
            f.unlink()
        be, calls = self.counting()
        metas = sflog.Remote(be).sessions(None)
        self.assertIn('old-1', [m['session_id'] for m in metas])
        self.assertIn('m-1', [m['session_id'] for m in metas])
        self.assertTrue(self.meta_file('claude', 'old-1').exists())
        shown = sh(sys.executable, str(SFLOG), 'show', 'old-1', cwd=self.project, env=self.env())
        self.assertIn('로그인 버그 고쳐줘', shown)
        be, calls = self.counting()
        sflog.Remote(be).sessions(None)
        self.assertEqual(calls['list'], ['logs/_meta/'])  # 두 번째부터는 옮기지 않는다

    def test_fts_marks_survive_mixed_sqlite_builds(self):
        path = self.base / 'mixed.sqlite'
        real = sflog.fts_available
        sflog.fts_available = lambda: False
        try:
            b = sflog.Index(path)  # FTS 가 안 되는 python3
        finally:
            sflog.fts_available = real
        a = sflog.Index(path)  # FTS 가 되는 python3 — 그사이 열었다
        b.update('logs/r/claude/s', 'v1', [{'role': 'user', 'name': None, 'text': 'hello world'}])
        a.close()
        b.close()
        a = sflog.Index(path)
        try:
            self.assertIn('logs/r/claude/s', a.hits('hello', False, ['logs/r/claude/s']))
            self.fts_ok(a)
        finally:
            a.close()

    def test_old_fts_definition_left_behind_is_recreated(self):
        import sqlite3
        path = self.base / 'old.sqlite'
        db = sqlite3.connect(str(path))  # FTS 없는 쪽이 user_version 만 올리고 예전 ev_fts 를 못 지운 상태
        db.executescript("""
            PRAGMA user_version = 2;
            CREATE TABLE sessions(dir TEXT PRIMARY KEY, sig TEXT NOT NULL);
            CREATE TABLE ev(id INTEGER PRIMARY KEY, dir TEXT NOT NULL, role TEXT, name TEXT, text TEXT, ftext TEXT);
            CREATE TABLE state(k TEXT PRIMARY KEY, v TEXT);
            CREATE VIRTUAL TABLE ev_fts USING fts5(text, content='ev', content_rowid='id', tokenize='trigram');
        """)
        db.close()
        idx = sflog.Index(path)
        try:
            idx.update('logs/r/claude/s', 'v1', [{'role': 'user', 'name': None, 'text': 'hello world'}])
            self.assertIn('logs/r/claude/s', idx.hits('hello', False, ['logs/r/claude/s']))
            self.fts_ok(idx)
        finally:
            idx.close()

    def test_case_folding_is_the_same_with_and_without_fts(self):
        texts = ['İstanbul trip', 'xxıxx', 'ſecret plan', 'Straße', 'ΣΊΣΥΦΟΣ', 'Kelvin K']
        queries = ['istanbul', 'xxixx', 'secret', 'STRASSE', 'σίσυφος', 'kelvin k', 'İSTANBUL']
        results = []
        for fts in (True, False):
            idx = sflog.Index(self.base / f'fold-{fts}.sqlite')
            try:
                idx.fts = idx.fts and fts
                for n, t in enumerate(texts):
                    idx.update(f'logs/r/claude/{n}', 'v', [{'role': 'user', 'name': None, 'text': t}])
                dirs = [f'logs/r/claude/{n}' for n in range(len(texts))]
                results.append({q: sorted(idx.hits(q, False, dirs)) for q in queries})
            finally:
                idx.close()
        self.assertEqual(results[0], results[1])
        found = results[0]
        self.assertEqual(found['istanbul'], ['logs/r/claude/0'])
        self.assertEqual(found['İSTANBUL'], ['logs/r/claude/0'])
        self.assertEqual(found['xxixx'], ['logs/r/claude/1'])
        self.assertEqual(found['secret'], ['logs/r/claude/2'])
        self.assertEqual(found['σίσυφος'], ['logs/r/claude/4'])
        self.assertEqual(found['STRASSE'], [])  # ß 는 길이를 바꾸는 접기라 하지 않는다
        self.assertEqual(sflog.fold('İſK'), 'isk')

    def test_expired_sessions_leave_the_index(self):
        self.search('npm test')
        self.meta_file('devin', 'devin-session-1').unlink()  # lifecycle 이 지웠다
        self.assertIn('SEARCH=0개 세션', self.search('npm test'))
        r = sflog.Remote(sflog.sfbackend.LocalBackend(self.store))
        idx = sflog.Index(r.dir / 'index.sqlite')
        try:
            self.assertFalse(any(d.endswith('devin-session-1') for d in idx.sigs()))
            self.assertEqual(idx.db.execute("SELECT count(*) FROM ev WHERE dir LIKE '%devin-session-1'").fetchone()[0], 0)
        finally:
            idx.close()

    def test_in_flight_session_from_1_4_moves_its_meta(self):
        state = self.home / 'logs' / 'sessions' / 'claude-claude-session-1.json'
        st = json.loads(state.read_text())
        del st['meta_key']  # 1.4 가 남긴 진행 기록
        state.write_text(json.dumps(st))
        self.meta_file('claude', 'claude-session-1').unlink()
        self.assertIn('nochange', self.collect('claude', 'claude-session-1', self.base / 'c.jsonl'))
        self.assertTrue(self.meta_file('claude', 'claude-session-1').exists())


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
                be.put(f'logs/_meta/r/claude/{sid}.json', json.dumps({'session_id': sid, 'tool': 'claude',
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
        meta = self.meta_file('claude', 'h-1')
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
        meta = self.meta_file('grok', 'g-2')
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
            codex = json.loads((out['codex'] / 'hooks/hooks.json').read_text())  # 자기 codex.hooks.json — ghflow 훅이 아니다
            self.assertEqual(sorted(codex['hooks']), ['SessionEnd', 'Stop'])
            self.assertTrue(codex['_hbrness']['merge'])
            self.assertIn('${CODEX_PLUGIN_ROOT}/scripts/sfhook.py', json.dumps(codex))
            self.assertNotIn('fetch-templates', json.dumps(codex))
            for o in out.values():
                self.assertEqual(list(o.glob('hooks/*.hooks.json')), [])


if __name__ == '__main__':
    unittest.main()
