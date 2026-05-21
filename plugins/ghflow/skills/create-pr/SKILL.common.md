---
name: create-pr
model: sonnet
description: >
  This skill should be used when the user asks to "create pr", "make pr", "open pull request",
  "PR 올려줘", "PR 만들어줘", "풀리퀘 생성", or invokes /create-pr.
  It creates a GitHub Pull Request using the PR template fetched directly from
  `soy-media/.github` at the moment the skill runs (no cache, no shared helper).
  Usage: /create-pr [base-branch] [--draft] [--assignee <login>] [message]
---

# Create PR Skill

Create a GitHub Pull Request using the PR template stored in the
`soy-media/.github` repository. The template is fetched directly via `gh api` each
time the skill runs, so the latest remote version is always used and there is no
cache file or hook to keep in sync.

## Arguments

Arguments can appear in any order. Parsing rules:

- `--draft`: Optional flag. Create the PR as a draft. Can appear anywhere.
- `--assignee {login}`: Optional. GitHub username to assign to the PR. If omitted, defaults to `@me` (the authenticated user). Use `--assignee ""` to explicitly create with no assignee.
- `[base-branch]`: Optional. The target branch to merge into. Identified as the first non-flag, non-quoted token. If omitted, defaults to the repo's default branch.
- `"[message]"`: Optional. Free-text instructions or context, enclosed in double quotes. For example, review focus areas, additional context for reviewers, or specific instructions on how to fill the template. This message is used when generating the PR title and body.

Examples:
- `/create-pr`
- `/create-pr develop`
- `/create-pr --draft`
- `/create-pr develop --draft "DB 마이그레이션 부분 집중 리뷰 부탁"`
- `/create-pr --draft "인증 로직 변경 중심으로 봐주세요" develop`
- `/create-pr --assignee octocat`
- `/create-pr develop --assignee octocat --draft`

## Procedure

### Step 1: Validate Git State

1. Confirm we are inside a git repository.
2. Get the current branch name. If on the default branch (main/master), warn the user and abort.
3. Check if there are uncommitted changes. If so, inform the user and ask whether to proceed or commit first.
4. Check if the current branch has a remote tracking branch and is pushed. If not pushed, push with `-u` flag after confirming with the user.

### Step 2: Sync with Base Branch

Before gathering PR context, ensure the current branch is up to date with the base branch to avoid merge conflicts after PR creation.

1. **Determine base branch**: Use the argument if provided, otherwise detect the repo's default branch:
   ```bash
   gh repo view --json defaultBranchRef -q '.defaultBranchRef.name'
   ```

2. **Fetch latest remote changes**:
   ```bash
   git fetch origin {base}
   ```

3. **Rebase onto the updated base branch**:
   ```bash
   git rebase origin/{base}
   ```

4. **If rebase conflicts occur**:
   - List conflicting files with `git diff --name-only --diff-filter=U`
   - Show each conflict to the user and resolve them one by one
   - After resolving each file, stage it with `git add {file}`
   - Continue the rebase with `git rebase --continue`
   - If too many conflicts or the user wants to abort, run `git rebase --abort` and inform the user

5. **Force-push the rebased branch** (since rebase rewrites history):
   ```bash
   git push --force-with-lease
   ```
   Use `--force-with-lease` instead of `--force` for safety — it will fail if someone else pushed to the branch in the meantime.

### Step 3: Gather PR Context

Collect information needed to fill in the PR:

1. **Base branch**: Already determined in Step 2.
2. **Commits**: Get all commits from the branch divergence point:
   ```bash
   git log --oneline {base}..HEAD
   ```
3. **Full diff**: Get the overall diff to understand the changes:
   ```bash
   git diff {base}...HEAD
   ```
4. **Changed files**: List all changed files:
   ```bash
   git diff --name-status {base}...HEAD
   ```

### Step 4: Fetch PR Template from soy-media/.github

Fetch the PR template directly from the org-level `soy-media/.github` repo at
runtime. There is no cache file and no shared helper — every invocation hits the
GitHub API.

```bash
TEMPLATE_BODY=$(gh api \
  "repos/soy-media/.github/contents/.github/PULL_REQUEST_TEMPLATE/pull_request_template.md" \
  -q '.content' 2>/dev/null | base64 -d)
```

Notes:
- The org is hardcoded to `soy-media`. The skill ignores the current repo and any
  org-`.github` discovery logic.
- The path is the current canonical location
  (`.github/PULL_REQUEST_TEMPLATE/pull_request_template.md`). If GitHub returns
  a 404, fall back once to `.github/pull_request_template.md` on the same repo.
- If both paths fail or the result is empty (gh unauthenticated, network
  failure, template removed), inform the user and ask whether to proceed with a
  freeform body generated from commits/diff, or abort. Do **not** silently
  invent a body.

Use `TEMPLATE_BODY` directly as the template to fill in Step 5. There is no
multi-template selection step — `soy-media/.github` exposes a single PR
template, so just fill it in.

### Step 5: Fill In the Template

Analyze the commits and diff gathered in Step 3, then fill in the selected template's `body` intelligently:

- Replace placeholder sections (e.g., `## Summary`, `## Changes`, `## Description`) with actual content
  derived from the commits and code changes.
- If the user provided a `[message]`, incorporate it — use it as additional context for the summary, as reviewer guidance (e.g., "focus on the DB migration"), or to emphasize specific aspects of the changes.
- Keep the template's structure and section headings intact.
- If the template has checkboxes (e.g., `- [ ] Tests added`), leave them as-is for the user to check manually.
- Write in the same language as the template (if Korean, write in Korean; if English, write in English).
- Be concise but informative. Focus on **what** changed and **why**.

### Step 6: Generate PR Title

Create a concise PR title (under 70 characters) based on the changes:
- Summarize the main purpose of the PR
- Use conventional style if the repo follows it (e.g., `feat:`, `fix:`, `chore:`)
- Check recent merged PRs for title style reference:
  ```bash
  gh pr list --state merged --limit 5 --json title -q '.[].title'
  ```

### Step 7: Preview and Confirm

Present the following to the user for review using the AskUserQuestion tool:

- **Title**: The generated PR title
- **Template source**: Always `soy-media/.github` (show explicitly so the user
  can confirm)
- **Base branch**: The target branch
- **Assignee**: The resolved assignee (e.g., `@me` or the specified username)
- **Body**: The filled-in template content (show a summary, not the full body if too long)

Options:
- "Create PR (Recommended)" — proceed with the generated content
- "Edit title" — let the user provide a custom title
- "Edit body" — let the user modify the body before creating
- "Cancel" — abort

### Step 8: Create the Pull Request

```bash
gh pr create --base {base_branch} --title "{title}" --body "$(cat <<'EOF'
{filled_template_body}
EOF
)" --assignee {assignee} [--draft]
```

- Add `--draft` flag if the user passed `--draft` argument.
- `{assignee}` is `@me` by default, or the value from `--assignee` if explicitly provided. If the user passed `--assignee ""`, omit the `--assignee` flag entirely.

After successful creation, display the PR URL to the user.

## Guidelines

- Fetch the PR template inline with `gh api` against `soy-media/.github` —
  do not rely on `fetch-templates.py`, `/tmp/ghflow/*`, or any cached state.
- The template is refreshed on every invocation, so edits pushed to
  `soy-media/.github` are picked up on the next run.
- Respect the template's original formatting and structure when filling it in.
- Do not modify checkbox items — leave them for the user to manage.
- If the template contains sections that don't apply to the current changes, write "N/A" or leave them empty rather than removing them.
- The PR body content should be factual and based on the actual diff — do not fabricate changes.
