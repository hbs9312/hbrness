---
name: chronicle-lookup
description: >
model: sonnet
  Search and display previously-recorded commit chronicles from
  `~/.commit-chronicles/` to answer "why was this code written this way?",
  "왜 이렇게 짰지?", "이 함수 왜 바꿨지?", "이 파일 이전에 무슨 결정이 있었지?",
  "what was the reasoning behind commit <sha>?", or similar archaeology
  questions about intent/decisions/history that the diff alone cannot answer.
  Trigger when the user asks to look up, find, search, show, or recall a past
  commit's rationale, or invokes "/chronicle-lookup", "/chronicle-find",
  "커밋 기록 찾아줘", "chronicle 찾아줘". Do NOT trigger to write a new
  chronicle — that is the `ghflow:chronicle` skill. Use this skill whenever
  a question can plausibly be answered by prior chronicles before re-reading
  large diffs or git log.
  Usage: /chronicle-lookup [query] [--sha <sha>] [--file <path>] [--since <date>] [--all-repos] [--list [N]]
---

# Commit Chronicle — Lookup

Surface previously-written chronicles on demand. Chronicles live under
`~/.commit-chronicles/` (outside any project) and are never auto-loaded — this
skill is the explicit read path.

Use this skill when the user asks questions whose answer is *why* not *what*:

- "왜 이 API를 이렇게 설계했지?"
- "이 마이그레이션은 어떤 대안을 검토했지?"
- "이 파일에 대한 최근 의사결정 좀 보여줘"
- "what was the reasoning behind the auth rewrite last month?"
- "show me chronicles touching `src/auth/middleware.ts`"

If a question is obviously answerable from the current diff or recent commits
without prior-decision context, skip this skill and just answer. This skill is
for decision archaeology, not for every lookup.

## Arguments

Arguments can appear in any order. Unknown non-flag tokens are treated as a
free-text `query`.

- `[query]` — free-text search across chronicle bodies and frontmatter.
- `--sha <sha>` — show the chronicle for a specific commit (full or short SHA).
- `--file <path>` — find chronicles whose `files:` list includes this path.
- `--since <date>` — filter to chronicles committed on/after `<date>`
  (`YYYY-MM-DD` or relative like `7d`, `1mo`).
- `--all-repos` — search across every repo's chronicles, not just the current
  repo's slug. Default is current-repo-only.
- `--list [N]` — list the N most recent chronicles (default 10). Skips content
  rendering.

Examples:

- `/chronicle-lookup`                              # list 10 most recent for this repo
- `/chronicle-lookup auth middleware`              # text search
- `/chronicle-lookup --sha a4e12a2`                # show specific SHA
- `/chronicle-lookup --file src/auth.ts`           # file-scoped
- `/chronicle-lookup --since 2026-03-01`           # recent window
- `/chronicle-lookup rebase --all-repos`           # cross-repo text search
- `/chronicle-lookup --list 5`

## Procedure

### Step 1 — Locate the chronicle root

```bash
ROOT="$HOME/.commit-chronicles"
```

If `$ROOT` does not exist, tell the user "no chronicles have been written yet"
and suggest that after the next `git commit`, the ghflow hook will prompt
Claude to write one. Abort.

### Step 2 — Determine the search scope

Unless `--all-repos` is passed, scope to the current repo's slug:

```bash
REMOTE_URL=$(git config --get remote.origin.url 2>/dev/null || true)
```

Parse `<host>__<owner>__<repo>` from the URL (see the `chronicle` skill's
parsing rules). If there is no remote, use the local-fallback slug
(`local__<basename>__<sha1[0:8]>`).

If `--all-repos`, search directory `$ROOT/**` instead of `$ROOT/<slug>/**`.

If the scoped directory does not exist, tell the user no chronicles exist
for this repo and optionally suggest `--all-repos` if they had one.

### Step 3 — Build the candidate file list

Apply filters in this order:

1. **SHA filter** (`--sha <sha>`): find a file whose name contains the short
   SHA (`*-<short>-*.md`). Accept exact-length short SHAs (4+ chars). If
   multiple hits for an ambiguous prefix, list them and ask which to open.

2. **File filter** (`--file <path>`): grep frontmatter `files:` lists for the
   given path. Use a grep like:
   ```bash
   grep -rl --include='*.md' -E "^\s*-\s+$(printf '%q' "$path")\s*$" "$SCOPE_DIR"
   ```
   Match on substring if the provided path is a fragment (e.g. "auth.ts"
   matches `src/auth/middleware.ts` if substring).

3. **Since filter** (`--since <date>`): resolve to an absolute ISO date, then
   filter by the filename timestamp prefix (filenames start with
   `YYYYMMDDTHHMMSSZ-`).

4. **Text query**: if `[query]` is present, `grep -r -l -i` for the tokens
   across candidate files (or all files under scope if no other filter has
   narrowed yet). Score by match count for ranking.

5. **List mode** (`--list [N]`): skip all of the above; just collect up to N
   newest files by filename sort.

### Step 4 — Present results

**When exactly one file matches**, render it:

1. Print the file path in a relative form rooted at `$HOME/.commit-chronicles/`.
2. Summarise the frontmatter as a compact header:
   ```
   sha       a4e12a2 (<full sha>)
   committed 2026-04-18T13:27:00Z by <author>
   branch    <branch>
   stats     <n> files, +<insertions>/-<deletions>
   files     <top 3 files — if more, say "… and N more">
   ```
3. Print the body in full. If the body is very long (>300 lines), collapse
   the `What changed` section to its first paragraph and note the truncation.

**When multiple files match**, render a table newest-first:

```
| date       | sha      | subject                         | files |
|------------|----------|---------------------------------|-------|
| 2026-04-18 | a4e12a2  | Detect post-commit events …     | 2     |
| 2026-04-17 | 226d518  | 0.5.0                            | 7     |
```

Then ask which one to open, or offer `--list N` if results were truncated.

**When no file matches**, report "no chronicles matched" and, if the scope was
current-repo-only, suggest retrying with `--all-repos`.

### Step 5 — Trace related chronicles (optional)

If the rendered chronicle's `related.issues` or `related.prs` or `parents`
contain references, offer to follow them:

- A parent SHA with its own chronicle → offer to render it.
- An issue number → offer to `gh issue view`.
- A PR number → offer to `gh pr view`.

Do not chase these automatically; just mention what's available.

## Search performance notes

- Chronicles are plain markdown; `grep -r` over `~/.commit-chronicles/` is
  fine for thousands of entries. No indexer is used.
- The per-repo `INDEX.md` file (maintained by the `chronicle` skill) is
  newest-first and is the fastest way to browse without shell tools. Read it
  first when the user asks "최근 커밋 기록 보여줘" — it is often enough.

## Guidelines

- **Read-only.** Never edit or delete chronicle files from this skill. If the
  user wants to correct a chronicle, point them at the file path and let them
  edit it directly.
- **Never write into the project directory** as part of this skill.
- If the user phrases a question that could be answered by the current diff
  more cheaply than by chronicle search ("what does this function do?" —
  that is a read-the-code question, not an archaeology question), say so
  and skip the lookup.
- Do not paste more than one chronicle body at a time by default — offer a
  list first so the user chooses.
- When a query returns a chronicle the user clearly already has in mind
  (they quoted a SHA), skip the "did you mean this file" confirmation and
  render directly.
- Respect the chronicle's language in summaries. If a chronicle is Korean,
  describe it in Korean.
