---
name: draft-pr
description: "GitHub 이슈 번호를 기반으로 브랜치 생성, 빈 커밋, Draft PR 생성, 이슈-브랜치 연결까지 한번에 처리하는 스킬. 사용자가 'Draft PR 만들어줘', '이슈 작업 시작', 'PR 초안', 'draft pr', '빈 PR 생성', '이슈 브랜치 만들어줘', '/draft-pr' 등을 말하면 트리거한다. 이슈 기반으로 브랜치를 만들거나 Draft PR을 생성하려는 맥락이면 적극적으로 이 스킬을 사용할 것."
model: sonnet
---

# Draft PR

GitHub 이슈 번호를 기반으로 브랜치 생성 → 빈 커밋 → Draft PR 생성 → 이슈-브랜치 연결을 자동으로 처리한다.

## 사용법

```
/draft-pr <issue-number> [base-branch]
```

- `issue-number`: 필수. GitHub 이슈 번호 (예: 78)
- `base-branch`: 선택. 지정하지 않으면 자동으로 결정

## 실행 흐름

### 1. 레포지토리 정보 추출

현재 git remote에서 owner/repo를 자동 추출한다.

```bash
REPO_INFO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
OWNER=$(echo "$REPO_INFO" | cut -d'/' -f1)
REPO=$(echo "$REPO_INFO" | cut -d'/' -f2)
```

### 2. 이슈 정보 조회

```bash
gh issue view {issue_number} --json title,body --jq '{title, body}'
```

이슈 제목과 본문을 추출한다. 본문에서 `관련 PR` 또는 `Related` 섹션의 PR 번호도 파싱한다.

### 3. Base 브랜치 결정

우선순위에 따라 base 브랜치를 결정한다:

**3-1. 사용자가 명시적으로 지정한 경우** → 그대로 사용

**3-2. 미지정 시 → 이슈 body에서 관련 PR 탐색**

이슈 body에서 `관련 PR`, `Related PR`, `#숫자` 패턴을 찾는다. 관련 PR이 발견되면:

```bash
gh pr view {related_pr_number} --json headRefName --jq '.headRefName'
```

해당 PR의 head 브랜치를 base로 사용한다. 관련 PR이 여러 개면 가장 최근(번호가 큰) 것을 선택한다.

**3-3. 관련 PR이 없는 경우** → 이슈 body에서 parent issue(`#숫자`)를 찾고, 해당 이슈에 연결된 브랜치/PR을 확인:

```bash
gh issue develop {parent_issue_number} --list
```

또는:

```bash
gh pr list --search "closes #{parent_issue_number}" --json headRefName --jq '.[0].headRefName'
```

**3-4. 모두 실패 시** → `dev` 브랜치를 기본값으로 사용. `dev`가 없으면 `main` 사용.

### 4. 브랜치명 생성

이슈 번호 + 이슈 제목에서 slug를 생성한다.

규칙:
- 이슈 제목에서 prefix(fix:, feat:, chore: 등)를 추출
- 나머지 텍스트를 영문 slug로 변환 (한글이면 핵심 키워드를 영문으로 번역)
- 형식: `{issue_number}-{prefix}-{slug}` (예: `78-fix-chat-creation-failure`)
- 최대 50자로 제한

### 5. 원격 브랜치 생성 + 이슈 연결 (GraphQL)

`createLinkedBranch` mutation은 **새 브랜치를 원격에 생성하면서 동시에 이슈에 연결**한다. 이미 존재하는 브랜치에는 동작하지 않으므로, 반드시 git push 전에 실행해야 한다.

**5-1. 필요한 ID 조회:**

이슈 node ID, 레포지토리 ID, base 브랜치의 HEAD oid를 한번에 조회한다.

```bash
gh api graphql -f query='query {
  repository(owner: "{owner}", name: "{repo}") {
    id
    ref(qualifiedName: "refs/heads/{base_branch}") {
      target { oid }
    }
    issue(number: {issue_number}) { id }
  }
}'
```

**5-2. 브랜치 생성 + 이슈 연결:**

```bash
gh api graphql -f query='mutation {
  createLinkedBranch(input: {
    issueId: "{issue_node_id}",
    oid: "{base_branch_head_oid}",
    name: "{branch_name}",
    repositoryId: "{repo_node_id}"
  }) {
    linkedBranch { id ref { name } }
  }
}'
```

성공하면 `linkedBranch.id`가 반환된다. 실패해도 워크플로우는 계속 진행한다 (Step 5-3에서 수동 생성).

**5-3. 로컬 체크아웃 + 빈 커밋 + 푸시:**

```bash
git fetch origin {branch_name}
git checkout -b {branch_name} origin/{branch_name}
git commit --allow-empty -m "chore: empty commit for draft PR #{issue_number}

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin {branch_name}
```

만약 Step 5-2가 실패하여 원격 브랜치가 없는 경우:

```bash
git fetch origin {base_branch}
git checkout origin/{base_branch} -b {branch_name}
git commit --allow-empty -m "chore: empty commit for draft PR #{issue_number}

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push -u origin {branch_name}
```

### 6. Draft PR 생성

```bash
gh pr create --draft \
  --base {base_branch} \
  --title "{이슈 제목}" \
  --body "## Summary
- {이슈 설명 1줄 요약}

Closes #{issue_number}

## Related
- {이슈 body에서 추출한 관련 PR 목록}

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

body는 HEREDOC으로 전달하여 포맷을 보존한다.

### 7. 결과 출력

완료 후 아래 정보를 사용자에게 표시한다:

```
- 브랜치: {branch_name} (from {base_branch})
- Draft PR: {pr_url}
- 이슈-브랜치 연결: 완료/실패
```

## 에러 처리

- 이슈가 존재하지 않으면 즉시 중단하고 안내
- base 브랜치가 원격에 없으면 사용자에게 확인 요청
- 동일한 브랜치명이 이미 존재하면 사용자에게 확인 요청
- `createLinkedBranch` 실패는 경고만 출력 (PR 생성은 이미 완료)
