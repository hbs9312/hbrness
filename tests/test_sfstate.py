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


class SyncTests(Env):
    def test_two_pcs_share_handoff_and_followups(self):
        self.run_sf('init', '--remote', str(self.remote), pc='a')
        p = self.paths('a')
        self.assertEqual(p['SYNC'], 'on')
        Path(p['HANDOFF_FILE']).parent.mkdir(parents=True, exist_ok=True)
        Path(p['HANDOFF_FILE']).write_text('# Session Handoff\n\n## Next Action\n\nrun tests\n')
        d = Path(p['FOLLOWUPS_DIR'])
        d.mkdir(parents=True, exist_ok=True)
        (d / 'x.md').write_text('---\ntitle: X\nstatus: open\ndiscovered: 2026-10-01\n---\n\n# X\n')
        self.assertIn('SYNC=pushed', self.run_sf('sync', '-m', 'handoff', pc='a'))

        # 다른 PC: clone 경로가 달라도 같은 저장소면 같은 키로 찾는다
        other_clone = self.base / 'home-pc' / 'code' / 'my-app'
        sh('git', 'clone', '-q', str(self.project), str(other_clone), env=self.env('b'))
        sh('git', 'remote', 'set-url', 'origin', 'https://github.com/acme/my-app', cwd=other_clone, env=self.env('b'))
        self.run_sf('init', '--remote', str(self.remote), pc='b', cwd=other_clone)
        status = self.run_sf('status', pc='b', cwd=other_clone)
        self.assertIn('handoff [main]:', status)
        self.assertNotIn('handoff [main]: 없음', status)
        self.assertIn('followups: open 1', status)
        # INDEX.md 는 추적하지 않고 각 PC 에서 다시 만든다
        tracked = sh('git', 'ls-files', cwd=self.base / 'pc-b' / 'state', env=self.env('b'))
        self.assertNotIn('INDEX.md', tracked)
        self.assertIn('github.com/acme/my-app/followups/x.md', tracked)

    def test_concurrent_edits_on_different_items_merge(self):
        self.run_sf('init', '--remote', str(self.remote), pc='a')
        self.run_sf('init', '--remote', str(self.remote), pc='b')
        for pc, slug in (('a', 'from-a'), ('b', 'from-b')):
            d = Path(self.paths(pc)['FOLLOWUPS_DIR'])
            d.mkdir(parents=True, exist_ok=True)
            (d / f'{slug}.md').write_text(f'---\ntitle: {slug}\nstatus: open\n---\n')
        self.assertIn('SYNC=pushed', self.run_sf('sync', pc='a'))
        self.assertIn('SYNC=pushed', self.run_sf('sync', pc='b'))  # push 거절 → rebase → 재시도
        self.run_sf('pull', pc='a')
        d = Path(self.paths('a')['FOLLOWUPS_DIR'])
        self.assertTrue((d / 'from-b.md').exists())

    def test_background_pull_returns_at_once_and_brings_other_pc_changes(self):
        import time
        self.run_sf('init', '--remote', str(self.remote), pc='a')
        self.run_sf('init', '--remote', str(self.remote), pc='b')
        d = Path(self.paths('a')['FOLLOWUPS_DIR'])
        d.mkdir(parents=True, exist_ok=True)
        (d / 'late.md').write_text('---\ntitle: late\nstatus: open\n---\n')
        self.run_sf('sync', pc='a')

        pb = self.paths('b')
        stamp = Path(pb['PULL_STAMP'])
        started = time.monotonic()
        self.assertEqual(self.run_sf('pull', '--background', pc='b'), '')
        self.assertLess(time.monotonic() - started, 2)
        index = Path(pb['INDEX_FILE'])
        for _ in range(100):
            if stamp.exists() and index.exists():
                break
            time.sleep(0.1)
        self.assertTrue((Path(pb['FOLLOWUPS_DIR']) / 'late.md').exists())
        self.assertIn('late', index.read_text())  # --dir 로 그 프로젝트 INDEX 도 다시 만든다

    def test_pull_skips_while_another_pull_runs(self):
        import fcntl
        self.run_sf('init', '--remote', str(self.remote), pc='a')
        lock = self.base / 'pc-a' / '.sfstate-pull.lock'
        with open(lock, 'w') as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            self.assertIn('PULL=skipped', self.run_sf('pull', pc='a'))
        self.assertIn('PULL=ok', self.run_sf('pull', pc='a'))

    def test_without_state_repo_sync_is_local_only(self):
        p = self.paths()
        Path(p['FOLLOWUPS_DIR']).mkdir(parents=True)
        (Path(p['FOLLOWUPS_DIR']) / 'x.md').write_text('---\ntitle: X\n---\n')
        self.assertIn('SYNC=local-only', self.run_sf('sync'))


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
