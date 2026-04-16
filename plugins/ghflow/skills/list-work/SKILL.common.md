---
name: list-work
description: "현재 레포의 PR과 이슈 목록을 조회하여 보기 좋게 정리하는 스킬. GitHub 프로젝트 번호를 전달하면 해당 프로젝트에 속한 항목만 필터링한다. 사용자가 'PR 목록', '이슈 목록', '내 작업 목록', '작업 현황', 'PR 리스트', '이슈 리스트', 'my work', 'list work', 'list prs', 'list issues', '내 PR 보여줘', '내 이슈 보여줘', '프로젝트 현황', '/list-work' 등을 말하면 트리거한다. PR이나 이슈의 현황을 파악하려는 맥락이면 적극적으로 이 스킬을 사용할 것."
---

# List Work

현재 레포에서 사용자의 PR과 이슈 목록을 가져와 보기 좋게 정리하여 보여준다. GitHub 프로젝트 번호를 전달하면 해당 프로젝트에 포함된 항목만 필터링한다.

## 사용법

```
/list-work                        # 내 open PR + issue 목록
/list-work <project-number>       # 특정 GitHub 프로젝트의 항목만
/list-work --prs                  # PR만 보기
/list-work --issues               # issue만 보기
/list-work <project-number> --prs # 프로젝트 내 PR만 보기
```

## 실행 흐름

### 1. 현재 레포 정보 및 사용자 확인 (병렬 실행)

아래 명령을 병렬로 실행한다:

```bash
gh repo view --json nameWithOwner,defaultBranchRef --jq '{nameWithOwner: .nameWithOwner, defaultBranch: .defaultBranchRef.name}'
gh api user --jq '.login'
```

레포 정보를 확인할 수 없으면 사용자에게 알리고 중단한다.
`gh` CLI가 인증되지 않았으면 사용자에게 `gh auth login`을 안내한다.

`nameWithOwner`에서 `owner`와 `repo`를 분리한다 (예: `owner/repo` → `owner`, `repo`).

### 2. 데이터 가져오기

인자 파싱 결과에 따라 분기한다.

#### 2-A. 프로젝트 번호가 없는 경우 (기본 모드)

`--prs`, `--issues` 플래그에 따라 필요한 것만 가져온다. 플래그가 없으면 둘 다 가져온다.

**PR 목록** (`--issues` 전용이 아닌 경우):
```bash
gh pr list --author @me --state open --json number,title,state,isDraft,headRefName,baseRefName,createdAt,updatedAt,labels,reviewDecision,url --limit 30
```

**이슈 목록** (`--prs` 전용이 아닌 경우):
```bash
gh issue list --assignee @me --state open --json number,title,state,labels,milestone,createdAt,updatedAt,url --limit 30
```

가능한 경우 두 명령을 **병렬**로 실행한다.

#### 2-B. 프로젝트 번호가 있는 경우 (프로젝트 필터 모드)

GitHub Projects v2 API를 사용하여 해당 프로젝트의 항목을 가져온다.

```bash
gh project item-list <project-number> --owner <owner> --format json --limit 100
```

반환된 결과에서 `content.type`이 `Issue` 또는 `PullRequest`인 항목을 분리한다.
`--prs` 플래그가 있으면 PullRequest만, `--issues` 플래그가 있으면 Issue만, 플래그가 없으면 둘 다 보여준다.

각 항목에서 `content.number`를 추출한 뒤, 상세 정보를 가져온다:

**PR 상세 정보** (PR이 1개 이상인 경우):
```bash
gh pr list --state all --json number,title,state,isDraft,headRefName,baseRefName,createdAt,updatedAt,labels,reviewDecision,url --limit 100
```
반환된 PR 목록에서 프로젝트 항목의 number와 매칭되는 것만 필터링한다.

**이슈 상세 정보** (이슈가 1개 이상인 경우):
```bash
gh issue list --state all --json number,title,state,labels,milestone,createdAt,updatedAt,url --limit 100
```
반환된 이슈 목록에서 프로젝트 항목의 number와 매칭되는 것만 필터링한다.

**중요**: 프로젝트 모드에서는 `--state all`을 사용한다. 프로젝트 내 closed/merged 항목도 보여줘야 전체 진행 상황을 파악할 수 있다.

### 3. 결과 포맷팅 및 출력

가져온 데이터가 없으면 적절한 메시지를 출력한다:
- 기본 모드: "현재 열려있는 PR이나 이슈가 없습니다."
- 프로젝트 모드: "프로젝트 #{번호}에 포함된 항목이 없습니다."

데이터가 있으면 아래 형식으로 출력한다.

#### 헤더

```
## 📊 작업 현황 — {repo-name}
```

프로젝트 모드인 경우:
```
## 📊 작업 현황 — {repo-name} · Project #{번호}
```

#### PR 섹션 (PR이 있을 때)

```
### Pull Requests ({N}건)

| # | 번호 | 제목 | 상태 | 브랜치 | 리뷰 | 업데이트 |
|---|------|------|------|--------|------|----------|
| 1 | #123 | 로그인 기능 구현 | 🟢 Open | feat/login → main | ✅ Approved | 2일 전 |
| 2 | #120 | API 리팩토링 | 📝 Draft | refactor/api → main | 🔄 Review required | 5일 전 |
| 3 | #115 | 결제 모듈 연동 | 🟣 Merged | feat/payment → main | ✅ Approved | 1주 전 |
| 4 | #110 | 버그 수정 | 🔴 Closed | fix/bug → main | — | 2주 전 |
```

**상태 표시 규칙:**
- `🟢 Open` — state=OPEN, isDraft=false
- `📝 Draft` — state=OPEN, isDraft=true
- `🟣 Merged` — state=MERGED
- `🔴 Closed` — state=CLOSED

**리뷰 표시 규칙:**
- `✅ Approved` — reviewDecision=APPROVED
- `🔄 Review required` — reviewDecision=REVIEW_REQUIRED
- `⛔ Changes requested` — reviewDecision=CHANGES_REQUESTED
- `—` — 리뷰 없음 또는 Draft

**업데이트 시간**: `updatedAt`을 상대 시간으로 변환 (예: "2일 전", "1주 전", "3시간 전").

#### 이슈 섹션 (이슈가 있을 때)

```
### Issues ({N}건)

| # | 번호 | 제목 | 상태 | 라벨 | 마일스톤 | 업데이트 |
|---|------|------|------|------|----------|----------|
| 1 | #42  | 로그인 에러 수정 | 🟢 Open | 🐛 bug | Sprint 3 | 1일 전 |
| 2 | #38  | 검색 기능 추가 | 🟢 Open | ✨ enhancement | Sprint 4 | 3일 전 |
| 3 | #35  | API 캐싱 적용 | 🔴 Closed | 🚀 performance | - | 1주 전 |
```

**상태 표시 규칙:**
- `🟢 Open` — state=OPEN
- `🔴 Closed` — state=CLOSED

**라벨 표시 규칙**: 대표 라벨 1개를 아이콘과 함께 표시한다. 라벨이 여러 개면 첫 번째 라벨만 표시하고 나머지는 `+N`으로 표기한다.
- `bug` → `🐛 bug`
- `enhancement` → `✨ enhancement`
- `documentation` → `📚 docs`
- `performance` → `🚀 performance`
- `question` → `❓ question`
- 기타 → 아이콘 없이 라벨명 그대로

**마일스톤**: 없으면 `-`

#### 요약 푸터

```
---
📈 **요약**: PR {open}건 열림 · {draft}건 드래프트 · {merged}건 머지됨 | 이슈 {open}건 열림 · {closed}건 닫힘
```

프로젝트 모드가 아닌 기본 모드에서는 open 상태만 가져오므로:
```
---
📈 **요약**: PR {N}건 열림 ({draft}건 드래프트) | 이슈 {N}건 열림
```

### 4. 후속 액션 안내

목록 출력 후 사용자가 할 수 있는 후속 액션을 간결하게 안내한다:

```
💡 **다음 액션**: 특정 PR/이슈 번호를 말하면 상세 정보를 확인할 수 있습니다.
```

## 주의사항

- 기본 모드에서는 `--author @me` (PR) 및 `--assignee @me` (이슈)로 **사용자 본인의 항목만** 가져온다.
- 프로젝트 모드에서는 프로젝트 전체 항목을 가져오므로 다른 사람의 PR/이슈도 포함된다.
- `updatedAt` 상대 시간 계산은 현재 시각 기준으로 한다. 정확한 계산이 어려우면 ISO 날짜를 짧은 형식(예: `04/14`)으로 표시해도 된다.
- 프로젝트 번호는 GitHub Projects v2의 번호이다. URL에서 확인 가능: `github.com/orgs/{org}/projects/{number}` 또는 `github.com/users/{user}/projects/{number}`.
- `gh project item-list`가 실패하면 (프로젝트가 없거나 권한이 없는 경우) 적절한 에러 메시지를 보여주고 중단한다.
- 테이블 행이 너무 많으면 (30건 초과) 상위 30건만 표시하고 "외 {N}건 더 있음"을 표기한다.
