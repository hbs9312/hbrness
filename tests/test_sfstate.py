import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'plugins/sessionflow/scripts/sfstate.py'
spec = importlib.util.spec_from_file_location('sfstate', SCRIPT)
sfstate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sfstate)

GIT_ENV = {
    'GIT_AUTHOR_NAME': 't', 'GIT_AUTHOR_EMAIL': 't@example.com',
    'GIT_COMMITTER_NAME': 't', 'GIT_COMMITTER_EMAIL': 't@example.com',
    'GIT_CONFIG_GLOBAL': os.devnull, 'GIT_CONFIG_NOSYSTEM': '1',
}


def sh(*args, cwd=None, env=None):
    return subprocess.run(args, cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout


class NormalizeRemoteTests(unittest.TestCase):
    def test_same_repo_from_any_url_form(self):
        for url in ('git@github.com:hbs9312/hbrness.git',
                    'https://github.com/hbs9312/hbrness.git',
                    'https://user:token@github.com/hbs9312/hbrness/',
                    'ssh://git@github.com:22/hbs9312/hbrness.git',
                    'https://GitHub.com/HBS9312/hbrness'):
            self.assertEqual(sfstate.normalize_remote(url), 'github.com/hbs9312/hbrness', url)

    def test_local_remotes_have_no_key(self):
        for url in ('', '/srv/repo.git', '../other', 'file:///srv/repo.git'):
            self.assertIsNone(sfstate.normalize_remote(url), url)

    def test_branch_validation(self):
        self.assertTrue(sfstate.valid_branch('feat/x'))
        for bad in ('', '/x', 'x/', 'a/../b', 'a//b'):
            self.assertFalse(sfstate.valid_branch(bad), bad)


class Env(unittest.TestCase):
    """임시 HOME 아래에 프로젝트 repo, bare state remote, PC 두 대(HBRNESS_HOME)를 만든다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name).resolve()
        self.remote = self.base / 'state-remote.git'
        sh('git', 'init', '-q', '--bare', '-b', 'main', str(self.remote), env=self.env())
        self.project = self.base / 'work' / 'my-app'
        self.project.mkdir(parents=True)
        e = self.env()
        sh('git', 'init', '-q', '-b', 'main', cwd=self.project, env=e)
        sh('git', 'remote', 'add', 'origin', 'git@github.com:acme/my-app.git', cwd=self.project, env=e)
        sh('git', 'commit', '-q', '--allow-empty', '-m', 'init', cwd=self.project, env=e)

    def tearDown(self):
        self.tmp.cleanup()

    def env(self, pc='a'):
        return dict(os.environ, **GIT_ENV, HBRNESS_HOME=str(self.base / f'pc-{pc}'),
                    HBRNESS_STATE_DIR=str(self.base / f'pc-{pc}' / 'state'))

    def run_sf(self, *args, pc='a', cwd=None):
        return sh(sys.executable, str(SCRIPT), *args, cwd=cwd or self.project, env=self.env(pc))

    def paths(self, pc='a', cwd=None):
        out = self.run_sf('paths', pc=pc, cwd=cwd)
        return dict(line.split('=', 1) for line in out.splitlines())


class PathTests(Env):
    def test_key_is_repo_and_handoff_is_branch(self):
        p = self.paths()
        self.assertEqual(p['REPO_KEY'], 'github.com/acme/my-app')
        self.assertEqual(p['SYNC'], 'off')  # state repo 를 아직 init 안 함
        self.assertTrue(p['HANDOFF_FILE'].endswith('github.com/acme/my-app/handoffs/main.md'))

    def test_worktree_uses_its_branch_but_same_project(self):
        wt = self.base / 'elsewhere' / 'wt1'
        sh('git', 'worktree', 'add', '-q', '-b', 'feat/x', str(wt), cwd=self.project, env=self.env())
        p = self.paths(cwd=wt)
        self.assertEqual(p['REPO_KEY'], 'github.com/acme/my-app')
        self.assertEqual(p['PROJECT_ROOT'], str(self.project))
        self.assertTrue(p['HANDOFF_FILE'].endswith('handoffs/feat/x.md'))

    def test_no_remote_stays_local(self):
        plain = self.base / 'plain'
        plain.mkdir()
        p = self.paths(cwd=plain)
        self.assertEqual(p['REPO_KEY'], '')
        self.assertIn('/_local/', p['PROJECT_DIR'])


class IndexTests(Env):
    def write_item(self, d, slug, **fm):
        d.mkdir(parents=True, exist_ok=True)
        lines = ['---'] + [f'{k}: {json.dumps(v, ensure_ascii=False)}' for k, v in fm.items()] + ['---', '', f'# {slug}']
        (d / f'{slug}.md').write_text('\n'.join(lines) + '\n')

    def test_index_groups_and_prunes_resolved(self):
        d = Path(self.paths()['FOLLOWUPS_DIR'])
        self.write_item(d, 'a', title='A | pipe', status='open', discovered='2026-01-02', summary='요약 A')
        self.write_item(d, 'b', title='B', status='pending', discovered='2026-01-01')
        self.write_item(d, 'c', title='C', status='idea', discovered='2026-01-03')
        for n in range(3):
            self.write_item(d, f'r{n}', title=f'R{n}', status='resolved', resolved=f'2026-02-0{n + 1}')
        (d / '_config.json').write_text('{"resolved_keep": 2}')
        out = self.run_sf('index', '--prune')
        self.assertIn('PRUNED=r0', out)
        self.assertFalse((d / 'r0.md').exists())
        index = (d / 'INDEX.md').read_text()
        self.assertIn('| A \\| pipe | 요약 A | 2026-01-02 | [a.md](./a.md) |', index)
        self.assertIn('## Decisions Pending', index)
        self.assertIn('- 2026-01-03 C ([c.md](./c.md))', index)
        self.assertIn('## Resolved (최근 2)', index)

        data = json.loads(self.run_sf('index', '--json'))
        self.assertEqual(data['counts'], {'open': 1, 'pending': 1, 'idea': 1, 'resolved': 2})
        self.assertEqual([i['slug'] for i in data['items']], ['a', 'b', 'c', 'r2', 'r1'])
        self.assertEqual(data['items'][0]['summary'], '요약 A')


class NoBackendTests(Env):
    def test_without_backend_sync_is_local_only(self):
        p = self.paths()
        Path(p['FOLLOWUPS_DIR']).mkdir(parents=True)
        (Path(p['FOLLOWUPS_DIR']) / 'x.md').write_text('---\ntitle: X\n---\n')
        out = self.run_sf('sync')
        self.assertIn('SYNC=local-only', out)
        self.assertIn('backend 가 없다', out)

    def test_old_git_state_repo_is_not_synced_any_more(self):
        state = self.base / 'pc-a' / 'state'
        state.mkdir(parents=True)
        sh('git', 'init', '-q', cwd=state, env=self.env())
        p = self.paths()
        self.assertEqual(p['SYNC'], 'off')
        self.assertIn('1.0 에서 없어졌다', self.run_sf('prepare'))


class LocalBackendTests(unittest.TestCase):
    def test_conditional_put(self):
        sfbackend = sfstate.sfbackend
        with tempfile.TemporaryDirectory() as d:
            be = sfbackend.LocalBackend(d)
            be.ensure()
            etag = be.put('repos/a/b.md', b'one', if_none_match=True)
            with self.assertRaises(sfbackend.PreconditionFailed):
                be.put('repos/a/b.md', b'two', if_none_match=True)
            with self.assertRaises(sfbackend.PreconditionFailed):
                be.put('repos/a/b.md', b'two', if_match='stale')
            etag2 = be.put('repos/a/b.md', b'two', if_match=etag)
            self.assertEqual(be.get('repos/a/b.md'), (b'two', etag2))
            self.assertEqual(be.list('repos/'), {'repos/a/b.md': etag2})
            with self.assertRaises(sfbackend.PreconditionFailed):
                be.delete('repos/a/b.md', if_match=etag)  # 그사이 바뀐 버전은 지우지 않는다
            self.assertTrue(be.delete('repos/a/b.md', if_match=etag2))
            self.assertFalse(be.delete('repos/a/b.md'))
            self.assertIsNone(be.get('repos/a/b.md'))
            self.assertFalse((Path(d) / 'repos').exists())  # 빈 디렉토리도 지운다
            with self.assertRaises(sfbackend.BackendError):
                be.put('repos/../escape.md', b'x')

    def test_missing_remote_dir_is_an_error_not_an_empty_store(self):
        sfbackend = sfstate.sfbackend
        with tempfile.TemporaryDirectory() as d:
            be = sfbackend.LocalBackend(Path(d) / 'never-initialised')
            with self.assertRaises(sfbackend.BackendError):
                be.list('repos/')
            with self.assertRaises(sfbackend.BackendError):
                be.put('repos/a.md', b'x')

    def test_conflict_copies_never_overwrite_each_other(self):
        sfbackend = sfstate.sfbackend
        with tempfile.TemporaryDirectory() as d:
            be = sfbackend.LocalBackend(Path(d) / 'store')
            be.ensure()
            cache = sfbackend.Cache(Path(d) / 'state', be)
            f = Path(d) / 'state' / 'h' / 'o' / 'r' / 'x.md'
            f.parent.mkdir(parents=True)
            asides = []
            for text in ('first', 'second'):
                f.write_text(text)
                asides.append(cache._set_aside('h/o/r/x.md'))
            self.assertNotEqual(asides[0], asides[1])
            self.assertEqual([a.read_text() for a in asides], ['first', 'second'])

    def test_partial_pull_still_reports_conflicts(self):
        sfbackend = sfstate.sfbackend

        class Flaky(sfbackend.LocalBackend):
            calls = 0

            def get(self, key):
                if key.endswith('b.md'):
                    raise OSError('disk went away')
                return super().get(key)

        with tempfile.TemporaryDirectory() as d:
            store, state = Path(d) / 'store', Path(d) / 'state'
            be = sfbackend.LocalBackend(store)
            be.ensure()
            cache = sfbackend.Cache(state, be)
            for name in ('a.md', 'b.md'):
                (state / 'h' / 'o').mkdir(parents=True, exist_ok=True)
                (state / 'h' / 'o' / name).write_text('v1')
            cache.push('')
            for name in ('a.md', 'b.md'):
                be.put(f'repos/h/o/{name}', b'remote v2', if_match=cache.entries[f'h/o/{name}']['etag'])
            (state / 'h' / 'o' / 'a.md').write_text('local v2')
            flaky = sfbackend.Cache(state, Flaky(store))
            with self.assertRaises(sfbackend.PartialSync) as cm:
                flaky.pull()
            self.assertEqual([c[0] for c in cm.exception.report['conflicts']], ['h/o/a.md'])
            self.assertEqual(cm.exception.report['conflicts'][0][1].read_text(), 'local v2')


class BackendSyncTests(Env):
    """backend.json(local) 으로 두 PC 가 같은 디렉토리를 원격처럼 쓴다."""

    KEY = 'github.com/acme/my-app'

    def setUp(self):
        super().setUp()
        self.store = self.base / 'store'

    def init(self, pc='a', cwd=None):
        return self.run_sf('init', '--backend', 'local', '--path', str(self.store), pc=pc, cwd=cwd)

    def item(self, pc, slug, text):
        d = Path(self.paths(pc)['FOLLOWUPS_DIR'])
        d.mkdir(parents=True, exist_ok=True)
        (d / f'{slug}.md').write_text(text)
        return d / f'{slug}.md'

    def stored(self, rel):
        return self.store / 'repos' / self.KEY / rel

    def test_two_pcs_share_handoff_and_followups(self):
        self.init('a')
        p = self.paths('a')
        self.assertEqual((p['SYNC'], p['BACKEND']), ('on', f'local:{self.store}'))
        Path(p['HANDOFF_FILE']).parent.mkdir(parents=True, exist_ok=True)
        Path(p['HANDOFF_FILE']).write_text('# Session Handoff\n\n## Next Action\n\nrun tests\n')
        self.item('a', 'x', '---\ntitle: X\nstatus: open\ndiscovered: 2026-10-01\n---\n\n# X\n')
        self.assertIn('SYNC=pushed', self.run_sf('sync', '-m', 'handoff', pc='a'))
        self.assertTrue(self.stored('followups/x.md').exists())
        self.assertTrue(self.stored('handoffs/main.md').exists())
        self.assertFalse(self.stored('followups/INDEX.md').exists())  # 생성물은 올리지 않는다
        self.assertIn('SYNC=nochange', self.run_sf('sync', pc='a'))

        other_clone = self.base / 'home-pc' / 'code' / 'my-app'
        sh('git', 'clone', '-q', str(self.project), str(other_clone), env=self.env('b'))
        sh('git', 'remote', 'set-url', 'origin', 'https://github.com/acme/my-app', cwd=other_clone, env=self.env('b'))
        self.init('b', cwd=other_clone)
        status = self.run_sf('status', pc='b', cwd=other_clone)
        self.assertNotIn('handoff [main]: 없음', status)
        self.assertNotIn('미동기화', status)
        self.assertIn('followups: open 1', status)

    def test_same_item_edited_on_two_pcs_keeps_both(self):
        self.init('a')
        self.init('b')
        self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.run_sf('pull', pc='b')
        self.item('a', 'x', 'from a\n')
        xb = self.item('b', 'x', 'from b\n')
        self.assertIn('SYNC=pushed', self.run_sf('sync', pc='a'))
        out = self.run_sf('sync', pc='b')
        self.assertIn(f'CONFLICT={self.KEY}/followups/x.md', out)
        self.assertEqual(xb.read_text(), 'from a\n')  # 원격본이 원래 자리에
        aside = list((self.base / 'pc-b' / 'state' / '_conflicts').rglob('x.*.md'))
        self.assertEqual([f.read_text() for f in aside], ['from b\n'])  # 이 PC 의 버전은 비켜 둔다
        self.assertEqual(self.stored('followups/x.md').read_text(), 'from a\n')
        self.assertIn('SYNC=nochange', self.run_sf('sync', pc='b'))  # _conflicts 는 올리지 않는다

    def test_pull_keeps_local_edit_when_remote_also_changed(self):
        self.init('a')
        self.init('b')
        self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.run_sf('pull', pc='b')
        self.item('a', 'x', 'from a\n')
        self.run_sf('sync', pc='a')
        xb = self.item('b', 'x', 'from b (not synced)\n')
        self.assertIn(f'CONFLICT={self.KEY}/followups/x.md', self.run_sf('pull', pc='b'))
        self.assertEqual(xb.read_text(), 'from a\n')

    def test_delete_reaches_other_pc(self):
        self.init('a')
        self.init('b')
        xa = self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.run_sf('pull', pc='b')
        xb = Path(self.paths('b')['FOLLOWUPS_DIR']) / 'x.md'
        self.assertTrue(xb.exists())
        xa.unlink()
        self.assertIn('SYNC=pushed', self.run_sf('sync', pc='a'))
        self.assertFalse(self.stored('followups/x.md').exists())
        self.run_sf('pull', pc='b')
        self.assertFalse(xb.exists())

    def test_delete_does_not_drop_newer_edit_from_other_pc(self):
        self.init('a')
        self.init('b')
        xa = self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.run_sf('pull', pc='b')
        self.item('b', 'x', 'edited on b\n')
        self.run_sf('sync', pc='b')
        xa.unlink()
        out = self.run_sf('sync', pc='a')
        self.assertIn('받아 왔다', out)
        self.assertEqual(xa.read_text(), 'edited on b\n')
        self.assertEqual(self.stored('followups/x.md').read_text(), 'edited on b\n')

    def test_moved_remote_dir_fails_pull_and_keeps_local_copies(self):
        self.init('a')
        x = self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.store.rename(self.base / 'store-moved')
        self.assertIn('PULL=failed', self.run_sf('pull', pc='a'))
        self.assertTrue(x.exists())
        x.write_text('v2\n')
        self.assertIn('SYNC=failed', self.run_sf('sync', pc='a'))

    @unittest.skipIf(os.geteuid() == 0, 'root 는 권한 000 디렉토리도 읽는다')
    def test_unreadable_dir_is_not_read_as_deletions(self):
        self.init('a')
        x = self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.item('a', 'y', 'new\n')
        x.parent.chmod(0)
        try:
            self.assertIn('SYNC=failed', self.run_sf('sync', pc='a'))
        finally:
            x.parent.chmod(0o755)
        self.assertTrue(self.stored('followups/x.md').exists())

    def test_reinit_on_fresh_store_at_same_path_reuploads_local_copies(self):
        self.init('a')
        x = self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.store.rename(self.base / 'store-lost')
        out = self.init('a')  # 같은 경로에 빈 저장소를 새로 만든다
        self.assertIn('PULL=ok (받음 0 · 지움 0)', out)
        self.assertIn('PUSH=ok (올림 1', out)
        self.assertTrue(x.exists())
        self.assertEqual(self.stored('followups/x.md').read_text(), 'v1\n')

    def test_migrate_all_reports_conflicts_from_its_pull(self):
        self.init('a')
        self.init('b')
        self.item('a', 'x', 'v1\n')
        self.run_sf('sync', pc='a')
        self.run_sf('pull', pc='b')
        self.item('a', 'x', 'from a\n')
        self.run_sf('sync', pc='a')
        self.item('b', 'x', 'from b\n')
        (self.base / 'pc-b' / 'sessionflow').mkdir()
        self.assertIn(f'CONFLICT={self.KEY}/followups/x.md', self.run_sf('migrate-all', pc='b'))

    def test_init_uploads_existing_state_repo_clone_and_archives_git(self):
        state = self.base / 'pc-a' / 'state'
        sh('git', 'clone', '-q', str(self.remote), str(state), env=self.env())
        (state / 'README.md').write_text('# sessionflow state\n')
        self.item('a', 'old', 'from git days\n')
        sh('git', 'add', '-A', cwd=state, env=self.env())
        sh('git', 'commit', '-q', '-m', 'old', cwd=state, env=self.env())
        out = self.init('a')
        self.assertIn('PUSH=ok (올림 1', out)
        self.assertIn('GIT_ARCHIVE=', out)
        self.assertFalse((state / '.git').exists())
        archive = next(self.base.joinpath('pc-a').glob('state.git-archive-*'))
        self.assertTrue((archive / '.git').is_dir())
        self.assertTrue((archive / 'README.md').exists())
        self.assertEqual(self.stored('followups/old.md').read_text(), 'from git days\n')
        self.assertFalse((self.store / 'repos' / 'README.md').exists())
        self.assertIn('SYNC=nochange', self.run_sf('sync', pc='a'))

    def test_doctor_checks_conditional_writes(self):
        self.init('a')
        out = self.run_sf('doctor', pc='a')
        for line in ('STORE=ok', 'IF_NONE_MATCH=ok', 'IF_MATCH=ok', 'DELETE_IF_MATCH=ok'):
            self.assertIn(line, out)
        self.assertEqual(list((self.store).glob('.doctor/*')), [])  # probe 는 치운다

    def test_background_pull_stamps_inside_state(self):
        import time
        self.init('a')
        self.init('b')
        self.item('a', 'late', '---\ntitle: late\nstatus: open\n---\n')
        self.run_sf('sync', pc='a')
        pb = self.paths('b')
        self.assertTrue(pb['PULL_STAMP'].endswith('/state/.sfstate/pulled'))
        self.assertEqual(self.run_sf('pull', '--background', pc='b'), '')
        for _ in range(100):
            if Path(pb['PULL_STAMP']).exists() and Path(pb['INDEX_FILE']).exists():
                break
            time.sleep(0.1)
        self.assertIn('late', Path(pb['INDEX_FILE']).read_text())


class S3UnitTests(unittest.TestCase):
    """네트워크 없이 S3Backend 의 응답 검증과 자격증명 처리를 본다."""

    def backend(self, responses):
        sfbackend = sfstate.sfbackend

        class Fake(sfbackend.S3Backend):
            def _request(self, method, key='', params=None, body=b'', extra=None):
                return responses.pop(0)

        return Fake({'type': 's3', 'bucket': 'b', 'endpoint': 'http://x'},
                    {'access_key_id': 'k', 'secret_access_key': 's'})

    def xml(self, inner):
        return (200, {}, ('<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
                          + inner + '</ListBucketResult>').encode())

    def test_list_rejects_incomplete_or_odd_responses(self):
        BackendError = sfstate.sfbackend.BackendError
        for bad in (self.xml('<IsTruncated>true</IsTruncated>'),             # 다음 페이지 토큰 없음
                    self.xml('<Contents><Key>repos/a</Key><ETag>"1"</ETag></Contents>'),  # IsTruncated 없음
                    (200, {}, b'<Error><Code>Odd</Code></Error>'),          # 다른 응답
                    (200, {}, b'not xml'),
                    self.xml('<IsTruncated>false</IsTruncated><Contents><Key>repos/a</Key></Contents>')):
            with self.assertRaises(BackendError, msg=bad):
                self.backend([bad]).list('repos/')

    def test_list_follows_continuation_tokens(self):
        be = self.backend([
            self.xml('<IsTruncated>true</IsTruncated><NextContinuationToken>t</NextContinuationToken>'
                     '<Contents><Key>repos/a</Key><ETag>"1"</ETag></Contents>'),
            self.xml('<IsTruncated>false</IsTruncated><Contents><Key>repos/b</Key><ETag>"2"</ETag></Contents>'),
        ])
        self.assertEqual(be.list('repos/'), {'repos/a': '1', 'repos/b': '2'})

    def test_credentials_file_is_never_world_readable(self):
        sfbackend = sfstate.sfbackend
        seen = []
        real_replace = os.replace

        def spy(src, dst):
            seen.append(os.stat(src).st_mode & 0o777)
            return real_replace(src, dst)

        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / 'credentials.json'
            (Path(d) / 'credentials.json.tmp').write_text('stale')  # 앞서 끊긴 쓰기
            old_umask = os.umask(0o022)
            try:
                sfbackend.os.replace = spy
                sfbackend.save_config(f, {'secret_access_key': 's'})
            finally:
                sfbackend.os.replace = real_replace
                os.umask(old_umask)
            self.assertEqual(seen, [0o600])
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)
            self.assertFalse((Path(d) / 'credentials.json.tmp').exists())

    def test_env_credentials_are_all_or_nothing_and_need_no_file(self):
        sfbackend = sfstate.sfbackend
        keys = ('HBRNESS_S3_ACCESS_KEY_ID', 'HBRNESS_S3_SECRET_ACCESS_KEY', 'HBRNESS_S3_SESSION_TOKEN')
        saved = {k: os.environ.pop(k, None) for k in keys}
        try:
            with tempfile.TemporaryDirectory() as d:
                f = Path(d) / 'credentials.json'
                f.write_text('{"access_key_id": "file-k", "secret_access_key": "file-s", "session_token": "old"}')
                os.environ['HBRNESS_S3_ACCESS_KEY_ID'] = 'env-k'  # secret 없이 key 만 — 섞지 않는다
                self.assertEqual(sfbackend.load_credentials(f)['access_key_id'], 'file-k')
                os.environ['HBRNESS_S3_SECRET_ACCESS_KEY'] = 'env-s'
                self.assertEqual(sfbackend.load_credentials(f), {'access_key_id': 'env-k', 'secret_access_key': 'env-s'})
                be = sfbackend.make_backend({'type': 's3', 'bucket': 'b'})  # 파일 경로 없이 환경변수만
                self.assertEqual(be.creds['access_key_id'], 'env-k')
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_cut_off_response_is_a_backend_error(self):
        import http.client
        sfbackend = sfstate.sfbackend

        class Cut:
            status, headers = 200, {}

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                raise http.client.IncompleteRead(b'par', 10)

        be = sfbackend.S3Backend({'type': 's3', 'bucket': 'b', 'endpoint': 'http://x'},
                                 {'access_key_id': 'k', 'secret_access_key': 's'})
        real = sfbackend.urllib.request.urlopen
        sfbackend.urllib.request.urlopen = lambda *a, **k: Cut()
        try:
            with self.assertRaises(sfbackend.BackendError):
                be.get('repos/a.md')
        finally:
            sfbackend.urllib.request.urlopen = real

    def test_init_uses_the_same_credentials_as_later_commands(self):
        import io
        import types
        keys = ('HBRNESS_S3_ACCESS_KEY_ID', 'HBRNESS_S3_SECRET_ACCESS_KEY')
        saved_env = {k: os.environ.pop(k, None) for k in keys + ('HBRNESS_HOME',)}
        saved_stdin = sys.stdin
        try:
            with tempfile.TemporaryDirectory() as d:
                os.environ.update({'HBRNESS_HOME': d, 'HBRNESS_S3_ACCESS_KEY_ID': 'env-k',
                                   'HBRNESS_S3_SECRET_ACCESS_KEY': 'env-s'})
                sys.stdin = io.StringIO('stdin-k\nstdin-s\n')
                a = types.SimpleNamespace(backend='s3', bucket='b', endpoint='http://x', prefix='', region='',
                                          path_style=None, credentials_stdin=True, path='')
                _, be, new = sfstate._init_config(a)
                self.assertEqual(be.creds['access_key_id'], 'env-k')  # load_backend 와 같은 선택
                self.assertEqual(new['access_key_id'], 'stdin-k')      # 저장은 stdin 것
        finally:
            sys.stdin = saved_stdin
            for k, v in saved_env.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v

    def test_stdin_credentials_replace_the_old_set(self):
        import io
        import types
        keys = ('HBRNESS_S3_ACCESS_KEY_ID', 'HBRNESS_S3_SECRET_ACCESS_KEY')
        saved_env = {k: os.environ.pop(k, None) for k in keys + ('HBRNESS_HOME',)}
        saved_stdin = sys.stdin
        try:
            with tempfile.TemporaryDirectory() as d:
                os.environ['HBRNESS_HOME'] = d
                (Path(d) / 'credentials.json').write_text(
                    '{"access_key_id": "old", "secret_access_key": "old", "session_token": "old-token"}')
                sys.stdin = io.StringIO('new-k\nnew-s\n')
                a = types.SimpleNamespace(backend='s3', bucket='b', endpoint='http://x', prefix='', region='',
                                          path_style=None, credentials_stdin=True, path='')
                _, be, new = sfstate._init_config(a)
                self.assertEqual(be.creds, {'access_key_id': 'new-k', 'secret_access_key': 'new-s'})
                self.assertEqual(new, be.creds)
        finally:
            sys.stdin = saved_stdin
            for k, v in saved_env.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


S3_ENV = {k: os.environ.get(f'HBRNESS_TEST_S3_{k.upper()}', '') for k in ('endpoint', 'bucket', 'access_key_id', 'secret_access_key', 'region')}


@unittest.skipUnless(S3_ENV['endpoint'] and S3_ENV['bucket'],
                     'HBRNESS_TEST_S3_ENDPOINT/BUCKET/ACCESS_KEY_ID/SECRET_ACCESS_KEY 가 있을 때만 (MinIO 등)')
class S3BackendTests(Env):
    """실제 S3 API 저장소에 붙는다. 테스트마다 prefix 를 새로 써서 서로 섞이지 않는다."""

    KEY = 'github.com/acme/my-app'

    def setUp(self):
        super().setUp()
        import uuid
        self.prefix = f'sfstate-test/{uuid.uuid4().hex}'

    def init(self, pc='a', cwd=None):
        args = [sys.executable, str(SCRIPT), 'init', '--backend', 's3', '--endpoint', S3_ENV['endpoint'],
                '--bucket', S3_ENV['bucket'], '--prefix', self.prefix, '--credentials-stdin']
        if S3_ENV['region']:
            args += ['--region', S3_ENV['region']]
        r = subprocess.run(args, cwd=cwd or self.project, env=self.env(pc), check=True, capture_output=True,
                           text=True, input=f"{S3_ENV['access_key_id']}\n{S3_ENV['secret_access_key']}\n")
        return r.stdout

    def backend(self):
        cfg = {'type': 's3', 'endpoint': S3_ENV['endpoint'], 'bucket': S3_ENV['bucket'], 'prefix': self.prefix,
               'region': S3_ENV['region'] or 'us-east-1'}
        return sfstate.sfbackend.S3Backend(cfg, {'access_key_id': S3_ENV['access_key_id'],
                                                  'secret_access_key': S3_ENV['secret_access_key']})

    def item(self, pc, slug, text):
        d = Path(self.paths(pc)['FOLLOWUPS_DIR'])
        d.mkdir(parents=True, exist_ok=True)
        (d / f'{slug}.md').write_text(text)
        return d / f'{slug}.md'

    def test_credentials_are_saved_privately(self):
        self.init('a')
        creds = self.base / 'pc-a' / 'credentials.json'
        self.assertEqual(oct(creds.stat().st_mode & 0o777), '0o600')
        self.assertNotIn(S3_ENV['secret_access_key'], (self.base / 'pc-a' / 'backend.json').read_text())

    def test_two_pcs_share_and_conflict(self):
        self.init('a')
        self.init('b')
        self.item('a', 'x', 'v1 한글\n')
        self.assertIn('SYNC=pushed', self.run_sf('sync', pc='a'))
        self.run_sf('pull', pc='b')
        xb = Path(self.paths('b')['FOLLOWUPS_DIR']) / 'x.md'
        self.assertEqual(xb.read_text(), 'v1 한글\n')
        self.item('a', 'x', 'from a\n')
        self.item('b', 'x', 'from b\n')
        self.run_sf('sync', pc='a')
        self.assertIn(f'CONFLICT={self.KEY}/followups/x.md', self.run_sf('sync', pc='b'))
        self.assertEqual(xb.read_text(), 'from a\n')
        Path(self.paths('a')['FOLLOWUPS_DIR'], 'x.md').unlink()
        self.assertIn('SYNC=pushed', self.run_sf('sync', pc='a'))
        self.run_sf('pull', pc='b')
        self.assertFalse(xb.exists())

    def test_list_follows_pages(self):
        be = self.backend()
        be.ensure()
        for n in range(5):
            be.put(f'repos/h/o/r/{n}.md', b'x', if_none_match=True)
        be.page_size = 2
        self.assertEqual(len(be.list('repos/')), 5)

    def test_doctor(self):
        self.init('a')
        out = self.run_sf('doctor', pc='a')
        self.assertIn('IF_NONE_MATCH=ok', out)
        self.assertIn('IF_MATCH=ok', out)
        self.assertIn('DELETE_IF_MATCH=', out)


class MigrateTests(Env):
    def legacy(self, pc='a'):
        d = self.base / f'pc-{pc}' / 'sessionflow' / str(self.project).replace('/', '-')
        (d / 'followups').mkdir(parents=True)
        (d / 'followups' / 'INDEX.md').write_text(
            '# Project Followups — Index\n\n'
            f'> Project: {self.project}\n\n'
            '## Open\n\n| 제목 | 한 줄 설명 | Discovered | 상세 |\n|---|---|---|---|\n'
            '| 캐시 버그 | 편집 뒤 옛 캐시가 살아남 | 2026-09-29 | [cache-bug.md](./cache-bug.md) |\n'
            '| 메모 | 프론트매터 없는 항목 | 2026-09-01 | [plain.md](./plain.md) |\n\n'
            '## Ideas / Improvements\n\n- 2026-09-02 retry 를 지수 백오프로\n\n'
            '## Resolved (최근 13 — 상한 13)\n\n| 제목 | Resolved | 상세 |\n|---|---|---|\n')
        (d / 'followups' / 'cache-bug.md').write_text(
            '---\ntitle: 캐시 버그\nstatus: open\ndiscovered: 2026-09-29\n---\n\n# 캐시 버그\n')
        (d / 'followups' / 'plain.md').write_text('# 메모\n\n본문\n')
        (d / 'HANDOFF.md').write_text('# Session Handoff\n\n> Branch: main\n')
        (d / 'worktrees' / 'gone').mkdir(parents=True)
        (d / 'worktrees' / 'gone' / 'HANDOFF.md').write_text('# old\n\n> Branch: feat/old\n')
        return d

    def test_migrate_keeps_index_summaries_and_skips_dead_worktrees(self):
        legacy = self.legacy()
        out = self.run_sf('prepare')
        self.assertIn('MIGRATE=migrated', out)
        self.assertIn('worktrees/gone/HANDOFF.md: 워크트리가 없어 건너뜀', out)
        p = dict(l.split('=', 1) for l in out.splitlines() if '=' in l and l.split('=', 1)[0].isupper())
        d = Path(p['FOLLOWUPS_DIR'])
        fm, _ = sfstate.parse_frontmatter((d / 'cache-bug.md').read_text())
        self.assertEqual(fm['summary'], '편집 뒤 옛 캐시가 살아남')
        fm, _ = sfstate.parse_frontmatter((d / 'plain.md').read_text())
        self.assertEqual((fm['title'], fm['status'], fm['discovered']), ('메모', 'open', '2026-09-01'))
        ideas = [f for f in d.glob('*.md') if 'status: idea' in f.read_text()]
        self.assertEqual(len(ideas), 1)
        self.assertEqual(json.loads((d / '_config.json').read_text()), {'resolved_keep': 13})
        self.assertTrue(Path(p['HANDOFF_FILE']).exists())
        self.assertTrue((legacy / sfstate.MARKER).exists())
        self.assertTrue((legacy / 'HANDOFF.md').exists())  # 원본은 지우지 않는다
        self.assertIn('MIGRATE=done-before', self.run_sf('prepare'))

    def test_migrate_all_finds_path_from_key_with_dashes(self):
        self.legacy()
        out = self.run_sf('migrate-all', '--dry-run')
        self.assertIn('dry-run → github.com/acme/my-app', out)

    def test_resolve_legacy_key_walks_dashed_names(self):
        target = self.base / 'a-b' / 'c-d-e'
        target.mkdir(parents=True)
        self.assertEqual(sfstate.resolve_legacy_key(str(target).replace('/', '-')), target)


if __name__ == '__main__':
    unittest.main()
