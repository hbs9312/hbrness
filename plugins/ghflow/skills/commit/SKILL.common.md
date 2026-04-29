---
name: commit
model: sonnet
description: >
  Generate commit messages for staged/unstaged changes. Detects multiple repositories
  under the current directory and generates separate commit messages per repo. Use -y
  to commit immediately.
  Usage: /commit [-y]
---

# Commit Skill

Generate commit messages following the team's commit convention, then optionally stage
and commit. Supports multi-repo workspaces.

## Arguments

Parse `$ARGUMENTS`:

- **`-y`** (optional) — Stage and commit immediately. Without it, display the plan only.

## Commit Convention

All generated messages must follow this format.

### Header

```
{tag}({scope}): {subject}
```

| Field | Required | Rule |
|---|---|---|
| **tag** | yes | One of the tags below |
| **scope** | recommended | Module or area in kebab-case, inside parentheses |
| **subject** | yes | Imperative mood, ≤50 chars, no trailing period |

### Tags

| Tag | Use |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | No behavior change, code improvement |
| `style` | Formatting only (not UI style) |
| `chore` | Build, config, dependency changes |
| `docs` | Documentation |
| `test` | Test code |

### Body (optional but recommended when non-trivial)

Blank line after header. Wrap at 72 chars.

Write **Why / What / Impact** only. Never describe **How** — the code already does that.

```
{tag}({scope}): {subject}

Why:
{reason for the change}

What:
- {change summary 1}
- {change summary 2}

Impact:
- {effect on existing behavior, if any}
```

### Breaking Change

Mark with `!` after scope or `BREAKING CHANGE:` footer:

```
feat(auth)!: change token payload structure
```

### Footer

| Key | Use |
|---|---|
| `Refs` | Jira issue link (`Refs: VVT-12`) |
| `BREAKING CHANGE` | Breaking change detail |
| `Co-authored-by` | Co-author attribution |

### Prohibitions

- No empty subjects like `fix: 수정` or `feat: 기능 추가`
- No mixing different types of changes in one commit
- No WIP commits merged without squash/rebase

## Procedure

### Step 1: Discover Repositories

```bash
find . -name ".git" -type d -maxdepth 3 2>/dev/null | sort
```

Each result's parent is a repo root. If none found, inform user and stop.

### Step 2: Per-Repository Analysis

For **each** repository:

#### 2-1. Gather changes

```bash
git -C <repo> status --short
```

No changes → skip with note.

#### 2-2. Collect diffs

```bash
git -C <repo> diff --stat
git -C <repo> diff
git -C <repo> diff --cached --stat
git -C <repo> diff --cached
git -C <repo> ls-files --others --exclude-standard
```

#### 2-3. Detect sensitive files

Check for `.env`, `credentials`, `secret`, `token`, `*.pem`, `*.key`, `id_rsa`, etc.
If found, **exclude** from commit plan and warn.

#### 2-4. Get recent style

```bash
git -C <repo> log --oneline -5
```

#### 2-5. Generate commit message

Based on all changes (staged + unstaged + untracked, excluding sensitive files):

1. Pick the correct **tag** from the convention.
2. Determine the **scope** from the primary area of change.
3. Write a **subject** ≤50 chars, imperative mood.
4. If the change is non-trivial, write **Why / What / Impact** body.
5. Add `Refs: {JIRA-KEY}` footer if a Jira key is detectable from the branch name.
6. Append `Co-authored-by: Claude <noreply@anthropic.com>` as the last footer line.

#### 2-6. Categorize files

- `modified` — tracked, changed
- `new file` — untracked
- `deleted` — tracked, removed
- `renamed` — moved/renamed

### Step 3: Display Commit Plan

```
## Commit Plan

### <repo-path>

**Files to commit:**
- file1.txt (modified)
- file2.ts (new file)

**Excluded (sensitive):**
- .env (skipped)

**Commit message:**
> feat(auth): add Google OAuth login
>
> Why:
> Social login was the top-requested feature in user surveys.
>
> What:
> - Add Google OAuth2 flow with PKCE
> - Add /api/auth/google callback endpoint
>
> Refs: VVT-42
> Co-authored-by: Claude <noreply@anthropic.com>
```

Single repository → omit repo-path header.

### Step 4: Execute or Wait

#### If `-y` provided:

1. Stage files individually by name (never `git add -A` or `git add .`):
   ```bash
   git -C <repo> add file1.txt file2.ts ...
   ```

2. Commit using HEREDOC for proper formatting:
   ```bash
   git -C <repo> commit -m "$(cat <<'EOF'
   {full commit message}
   EOF
   )"
   ```

3. Verify:
   ```bash
   git -C <repo> log --oneline -1
   ```

4. Summary after all repos:
   ```
   ## Committed
   - <repo>: <short-hash> <subject>
   ```

#### If `-y` NOT provided:

End with:
```
Commit this? (reply yes or `/commit -y` to execute)
```

On affirmative reply, execute without re-analysis.

## Guidelines

- Never push to remote. Local commit only.
- Never modify git config.
- Never use `--no-verify` or skip hooks.
- If pre-commit hook fails, report the error. Do not retry with `--no-verify`.
- Always stage by explicit file names. Never `git add -A` or `git add .`.
- Never stage or commit sensitive files. Always exclude and warn.
