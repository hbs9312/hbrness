---
name: chronicle
description: >
  Capture the work content, decisions, intent, and tradeoffs behind a git commit
  into a persistent, tool-agnostic chronicle file that any AI tool or human can read
  later to answer "why was this code written?". Writes to `~/.commit-chronicles/`
  (outside the project). Triggered by the ghflow PostToolUse hook right after a
  successful `git commit`, or manually by the user with "/chronicle", "/chronicle <sha>",
  "커밋 기록", "커밋 정리", "commit 기록", "chronicle this commit", or by an incoming
  `ghflow:chronicle` reminder. Also trigger when the user says "이 커밋 왜 한거지 기록해둬",
  "지금 커밋 의도 남겨줘", or similar phrasings focused on preserving commit rationale.
  Usage: /chronicle [sha] [--force] [--quiet]
---

# Commit Chronicle — Write

Persist the **intent**, **decisions**, and **tradeoffs** behind a git commit into a
durable markdown file under `~/.commit-chronicles/`. The file is authored with both
humans and AI tools in mind: structured YAML frontmatter + free-form sections.

Chronicles are **never** auto-ingested into any session. They sit on disk, outside the
project, waiting for someone (human or AI) to look them up when they ask "why was this
code written this way?". Use the companion `ghflow:chronicle-lookup` skill to find
past entries on demand.

## When to run

Run this skill in the following situations:

1. **Hook-nudged** — the ghflow PostToolUse hook emitted a system reminder mentioning
   `ghflow:chronicle` right after a successful `git commit`. The current session still
   holds the decision context; capture it before it evaporates.
2. **User-invoked** — the user typed `/chronicle`, said "커밋 정리해줘", or otherwise
   asked to record a commit's rationale.
3. **Back-fill** — the user asks to chronicle an older commit ("`a4e12a2` 기록 남겨줘").

Do **not** chronicle automatically in cases where the session holds no decision signal:
e.g. the user committed unrelated manual work in another terminal and Claude has no
context. In that case ask once; if confirmed, write a minimal skeleton; otherwise skip.

## Arguments

- `[sha]` — optional. Full or short commit SHA. Defaults to `HEAD`.
- `--force` — overwrite an existing chronicle for this SHA.
- `--quiet` — suppress the final preview; only print the written path.

Examples:
- `/chronicle`
- `/chronicle a4e12a2`
- `/chronicle HEAD~1`
- `/chronicle a4e12a2 --force`

## Procedure

### Step 1 — Confirm we are inside a git repository

```bash
git rev-parse --is-inside-work-tree
```

If this fails, tell the user the working directory is not a git repo and abort.

### Step 2 — Resolve the target commit

Default target is `HEAD`. If an argument is provided, resolve it:

```bash
TARGET="${1:-HEAD}"
SHA=$(git rev-parse --verify "$TARGET^{commit}")
```

If resolution fails, report the invalid ref and abort.

### Step 3 — Compute the repository slug

Prefer the remote URL; fall back to a local-deterministic slug for no-remote repos.

```bash
REMOTE_URL=$(git config --get remote.origin.url || true)
```

Parse `REMOTE_URL` into `<host>__<owner>__<repo>`, accepting all of:
- `git@github.com:owner/repo.git`
- `ssh://git@github.com/owner/repo.git`
- `https://github.com/owner/repo` (with or without `.git`)

If there is no remote, slug is `local__<basename>__<sha1[0:8] of absolute repo root>`.
The chronicle path always lives under `~/.commit-chronicles/<slug>/`.

### Step 4 — Idempotency check

Compute the target file's directory:

```
~/.commit-chronicles/<slug>/<YYYY>/<MM>/
```

Then glob for any file matching `*-<short_sha>-*.md`. If one exists and `--force` is
not set, tell the user it already exists, print its path, and stop (exit success).

### Step 5 — Gather commit metadata

Run in parallel where possible:

```bash
git log -1 --format='%H%n%h%n%an%n%ae%n%aI%n%P%n%s%n%b' "$SHA"
git show --stat --format='' "$SHA"
git show --name-only --format='' "$SHA"
git rev-parse --abbrev-ref HEAD        # current branch (may differ from commit branch)
git branch --contains "$SHA" --format='%(refname:short)' | head -5
```

Extract:
- full SHA, short SHA, author name/email, committed_at (ISO-8601), parents
- subject + body of the commit message
- files changed, insertions/deletions totals
- list of changed file paths
- current branch + branches that contain the commit

### Step 6 — Inspect the diff for substantive work (optional but recommended)

For richer `What changed` content, sample the diff — do **not** dump it verbatim into
the chronicle. Focus on:
- Which files/modules moved, renamed, or split
- Net added/removed symbols (public API, exported functions, tables, endpoints)
- Dependency / config / schema changes

```bash
git show --unified=0 --no-color "$SHA" | head -400
```

Only pull more lines if a specific function needs inspection.

### Step 7 — Synthesise the chronicle body

This is the core value of the skill. Use the **current conversation** as the primary
source of intent/decisions/alternatives/tradeoffs — these are things the diff does not
reveal. Supplement with the commit message and diff findings.

Fill the sections below. Omit a section (or write "N/A") only when the section truly
has no content — do not invent motivations the user never expressed.

**Language rule**: match the language the commit message itself is written in. If the
commit message is Korean, write the chronicle in Korean. If English, English.
Mixed-language commits: default to the language the user used in the session.

**Tone rule**: present-tense factual, not marketing. A future reader wants to learn
what and why, not be sold on the change.

**Budget**: aim for 200–600 words total. Skip padding. If a section is one sentence,
make it one sentence.

Required sections:

- **What changed** — 1–3 paragraphs grounded in the diff. Describe the actual code
  movement: files, modules, APIs touched, behavioural delta. Do not copy the commit
  message verbatim.
- **Why (intent)** — the reason. Problem being solved, user/business need, external
  constraint, incident being fixed. If an upstream issue/PR/conversation drove it,
  cite it.
- **Key decisions** — 1–5 bullets. Each bullet = a non-obvious choice + the reason it
  was chosen. These are the things a future reader would otherwise ask "why this
  approach?" about. Skip if the commit is trivial (version bump, typo).
- **Alternatives considered** — options evaluated and rejected, each with a one-line
  reason. Only include if the conversation or commit message actually reveals them;
  do not invent alternatives.
- **Tradeoffs & constraints** — compromises, known limitations, technical debt this
  commit introduces or accepts. The honest "what's wrong with this" section.
- **Related** — bullets pointing at related issues/PRs, previous commits (by SHA +
  one-line summary), related files/modules, external docs. Pull from the session's
  discussion and from the commit message.
- **Future notes** — things to revisit, follow-ups, gotchas for the next maintainer.

### Step 8 — Assemble the frontmatter

YAML frontmatter is machine-parseable and tool-agnostic. Use this exact shape:

```yaml
---
schema: commit-chronicle/v1
sha: <full sha>
short_sha: <7-char sha>
repo:
  host: <host>
  owner: <owner>
  name: <repo>
  root: <absolute path of repo>
branch: <current branch name>            # may differ from where the commit landed
contained_in: [<branch>, ...]             # output of `git branch --contains`
parents: [<parent sha>, ...]
author:
  name: <name>
  email: <email>
committed_at: <ISO-8601>
message:
  subject: <first line>
  body: |
    <rest of commit message, trimmed>
stats:
  files_changed: <n>
  insertions: <n>
  deletions: <n>
files:
  - <path>
tags: []                                  # optional: ["refactor", "bugfix", "feat", ...]
related:
  issues: []
  prs: []
---
```

Quote values that contain colons, hashes, or starting dashes. Use block scalars (`|`)
for multi-line strings. If `related.issues` or `related.prs` can be inferred from the
commit message or session (`#123`, `fixes #45`), populate them; otherwise leave `[]`.

### Step 9 — Compute the file path

```
~/.commit-chronicles/<slug>/<YYYY>/<MM>/<YYYYMMDDTHHMMSSZ>-<short_sha>-<slug-of-subject>.md
```

- The timestamp uses the commit's `committed_at` (NOT the current wall clock) so
  files sort by commit chronology even on back-fill.
- `slug-of-subject`: ASCII-ize the commit subject, lowercase, replace non-alphanumerics
  with `-`, squeeze `--`+, trim to ~40 chars. Drop emoji.
- Example: `20260418T132700Z-a4e12a2-detect-post-commit-events.md`

Create intermediate directories (`mkdir -p`).

### Step 10 — Write the file + update the repo INDEX.md

1. Write the chronicle file at the computed path using the format in Steps 7–8.
2. Append a one-line entry to `~/.commit-chronicles/<slug>/INDEX.md` so lookup is
   fast. If the INDEX.md does not exist, create it with a short header. Keep entries
   sorted newest-first (prepend).

   Entry shape:
   ```
   - <YYYY-MM-DD> `<short_sha>` <subject> — [<relative path>](<relative path>)
   ```

### Step 11 — Bootstrap the root README.md (idempotent)

If `~/.commit-chronicles/README.md` does not yet exist, create it with the content in
the "Root README template" section below. This documents the storage format for any
future tool or human. Do not overwrite if it exists.

### Step 12 — Report

Print a short confirmation to the user:

```
Chronicle written:
  ~/.commit-chronicles/<slug>/<YYYY>/<MM>/<filename>.md

To look up chronicles later: /chronicle-lookup
```

If `--quiet`, print only the path. If a section was skipped because the session had
no signal for it, mention that briefly so the user can amend if they want.

## Root README template

Write this to `~/.commit-chronicles/README.md` the first time the skill runs on a
machine. Adjust only if the schema version changes.

~~~markdown
# Commit Chronicles

This directory holds **commit chronicles** — per-commit markdown files that record the
*intent, decisions, and tradeoffs* behind a change, so a future reader (human or AI
tool) can answer "why was this code written?" without re-reading the diff or digging
through chat logs.

Chronicles are **not** loaded automatically into any AI session. They live here on
disk for explicit, on-demand lookup.

## Layout

```
~/.commit-chronicles/
├── README.md                              # this file
├── <host>__<owner>__<repo>/
│   ├── INDEX.md                           # newest-first table of entries
│   └── <YYYY>/<MM>/
│       └── <YYYYMMDDTHHMMSSZ>-<short_sha>-<slug>.md
```

The repo slug comes from the git remote: `git@github.com:foo/bar.git` →
`github.com__foo__bar`. Repositories with no remote get `local__<basename>__<hash>`.

## File format

Each chronicle is UTF-8 markdown with YAML frontmatter:

```yaml
---
schema: commit-chronicle/v1
sha: <full 40-char sha>
short_sha: <7-char sha>
repo: { host, owner, name, root }
branch: <branch>
parents: [<sha>, ...]
author: { name, email }
committed_at: <ISO-8601>
message: { subject, body }
stats: { files_changed, insertions, deletions }
files: [<path>, ...]
tags: []
related: { issues: [], prs: [] }
---
```

Followed by these free-form sections (any may be omitted if genuinely empty):
`What changed`, `Why (intent)`, `Key decisions`, `Alternatives considered`,
`Tradeoffs & constraints`, `Related`, `Future notes`.

## How to look things up

- **Any tool**: `grep -r "<keyword>" ~/.commit-chronicles/`
- **Claude Code with ghflow installed**: invoke `/chronicle-lookup`.
- **Direct path**: `~/.commit-chronicles/<slug>/INDEX.md` for newest-first list.

## Principles

- Tool-agnostic plain markdown — no database, no index files a specific tool needs.
- Personal (stored under `$HOME`). Teams that want to share chronicles can symlink
  or sync this directory; it is not committed to any project repo.
- Machine-parseable frontmatter (YAML) + human-friendly body.
- Written once per commit. Amended or rebased commits produce new SHAs → new files.
- Old entries are not auto-pruned; they are cheap to keep.
~~~

## Guidelines

- **Never write inside the project directory.** All paths resolve under `$HOME`.
- Do not dump raw diffs into the chronicle body. Summarise. Long diffs belong in
  `git show` — not in prose.
- Respect the user's language. Korean commit → Korean chronicle.
- Do not invent intent, decisions, or alternatives that the conversation did not
  reveal. A sparse chronicle is better than a fabricated one.
- If the chronicle would be entirely hollow (no What, no Why — just a version bump
  with no discussion), ask the user whether to skip, write a skeleton, or carry
  forward context from the previous chronicle.
- Do not modify anything in the project repo as part of this skill. No staging, no
  commits, no index updates in the target repo.
- The root README.md at `~/.commit-chronicles/README.md` is **bootstrap-only**. Do
  not rewrite it on subsequent runs unless the user explicitly asks.
- Chronicles are append-only from this skill's perspective. If the user wants to
  edit one, they edit the file directly.
