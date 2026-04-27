---
name: create-pr
description: >
model: sonnet
  This skill should be used when the user asks to "create pr", "make pr", "open pull request",
  "PR 올려줘", "PR 만들어줘", "풀리퀘 생성", or invokes /create-pr.
  It creates a GitHub Pull Request using the PR template fetched at session start by the
  ghflow SessionStart hook (from the current repo and the org's .github repo).
  Usage: /create-pr [base-branch] [--draft] [--assignee <login>] [message]
---

# Create PR Skill

Create a GitHub Pull Request using a PR template that was fetched at session start by the
ghflow SessionStart hook. This skill does **not** fetch or cache templates itself — it reads
the hook output directly.

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

### Step 4: Load PR Template from Hook Output

The ghflow SessionStart hook has already fetched PR templates from both the current repo and
the org's `.github` repo, and written them to a JSON file. This skill does not fetch or cache
templates — it reads the hook output directly.

**Read path:**
```bash
REPO_ID=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
SLUG=$(echo "$REPO_ID" | sed 's|/|__|')
TEMPLATES_FILE="/tmp/ghflow/${SLUG}/templates.json"
```

**File structure (relevant subset):**
```json
{
  "repo": "org/repo",
  "fetched_at": "...",
  "pr_templates": [
    { "source": "org/repo",   "path": ".github/pull_request_template.md", "body": "..." },
    { "source": "org/.github","path": "workflow-templates/PULL_REQUEST_TEMPLATE.md", "body": "..." }
  ]
}
```

**Selection rules:**
1. The hook already picks a single source: current repo wins over org `.github` — you will only ever see entries from one source in `pr_templates`.
2. **Single entry** (single-file form like `.github/PULL_REQUEST_TEMPLATE.md`): use it directly.
3. **Multiple entries** (directory form like `.github/PULL_REQUEST_TEMPLATE/*.md`): infer the best match from the user's `[message]` / branch name / commits, then confirm the choice in Step 7's preview. If inference is ambiguous, present the list (template name derived from `path` filename, e.g. `feature.md` → "Feature") and let the user pick before filling in.
4. If `pr_templates` is empty or the templates file does not exist:
   - Inform the user that no PR template was found (hook may not have run, gh may be unauthenticated, or no template exists).
   - Ask whether to proceed with a freeform body generated from commits/diff, or abort.

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
- **Template source**: Which repo the template came from (current repo vs org `.github`)
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

- Never fetch templates yourself — always read from `/tmp/ghflow/<slug>/templates.json` produced by the SessionStart hook.
- Template freshness is **session-scoped**: if the remote template changes during the session, the change is not reflected. The user must restart the session to pick up updates.
- Respect the template's original formatting and structure when filling it in.
- Do not modify checkbox items — leave them for the user to manage.
- If the template contains sections that don't apply to the current changes, write "N/A" or leave them empty rather than removing them.
- The PR body content should be factual and based on the actual diff — do not fabricate changes.
