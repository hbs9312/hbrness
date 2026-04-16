---
name: pick-issue
description: "GitHub 원격 저장소에서 사용자에게 assign된 이슈 목록을 가져와 작업할 이슈를 선택하게 한 뒤, 선택된 이슈의 내용을 프로젝트 메모리에 저장하는 스킬. 사용자가 '이슈 선택', '작업할 이슈', '이슈 골라줘', '내 이슈 보여줘', '이슈 목록', 'pick issue', 'my issues', 'assigned issues', 'what should I work on', '어떤 이슈 작업할까', '/pick-issue' 등을 말하면 트리거한다. 이슈를 고르거나 작업을 시작하려는 맥락이면 적극적으로 이 스킬을 사용할 것."
---

# Pick Issue

현재 프로젝트의 GitHub 원격 저장소에서 사용자에게 assign된 이슈를 가져와 보여주고, 작업할 이슈를 선택하면 해당 이슈의 상세 내용을 프로젝트 메모리에 기록한다. 이를 통해 이후 세션에서도 현재 작업 중인 이슈의 컨텍스트를 유지할 수 있다.

## 사용법

```
/pick-issue              # assign된 이슈 목록을 보여주고 선택
/pick-issue --all        # assign 여부와 관계없이 모든 open 이슈 표시
```

## 실행 흐름

### 1. 현재 레포 정보 및 사용자 확인 (병렬 실행)

아래 두 명령을 병렬로 실행한다:

```bash
gh repo view --json nameWithOwner --jq '.nameWithOwner'
gh api user --jq '.login'
```

레포 정보를 확인할 수 없으면 사용자에게 알리고 중단한다.
`gh` CLI가 인증되지 않았으면 사용자에게 `gh auth login`을 안내한다.

### 2. Assign된 이슈 목록 가져오기

```bash
# 기본: 사용자에게 assign된 open 이슈
gh issue list --assignee @me --state open --json number,title,labels,milestone,updatedAt --limit 30

# --all 플래그: 모든 open 이슈
gh issue list --state open --json number,title,labels,milestone,updatedAt --limit 30
```

### 3. 이슈 목록 표시 및 선택

가져온 이슈가 없으면 "assign된 open 이슈가 없습니다. 전체 이슈를 볼까요?"라고 물어본다.
사용자가 동의하면 `--all` 모드로 다시 가져온다. 전체 이슈도 없으면 종료한다.

이슈가 있으면, 다음과 같은 형식으로 보기 좋게 목록을 출력한다:

```
## 📋 내게 할당된 이슈 (repo-name)

| # | 번호 | 제목 | 라벨 | 마일스톤 |
|---|------|------|------|----------|
| 1 | #42  | 로그인 에러 수정 | bug | Sprint 3 |
| 2 | #38  | 검색 기능 추가 | enhancement | Sprint 4 |
| 3 | #35  | API 응답 캐싱 | performance | - |
```

그 다음 AskUserQuestion 도구를 사용하여 사용자에게 작업할 이슈 번호를 물어본다.
질문 예시: "어떤 이슈를 작업하시겠어요? (번호를 입력하세요, 예: 1 또는 #42)"

사용자가 순서 번호(1, 2, 3...)나 이슈 번호(#42, 42)로 응답하면 해당 이슈를 선택한다.

### 4. 선택된 이슈 상세 정보 가져오기

```bash
gh issue view <issue-number> --json number,title,body,labels,milestone,assignees,state,url,comments
```

이슈의 전체 내용(본문, 코멘트 포함)을 가져온다.

### 5. 프로젝트 메모리에 저장

선택된 이슈의 내용을 프로젝트 메모리에 기록한다.

**메모리 파일 경로 결정:**

1. `git rev-parse --show-toplevel`로 git 루트 경로를 구한다
2. 워크트리인 경우 git 루트가 `.claude/worktrees/...` 하위이므로, 이때는 `git rev-parse --git-common-dir`을 사용해 **원본 레포의 루트**를 구한다:
   ```bash
   git_common=$(git rev-parse --git-common-dir)  # e.g., /home/seok/development/velvetalk/fe/.git
   repo_root=$(dirname "$git_common")             # e.g., /home/seok/development/velvetalk/fe
   ```
3. 구한 `repo_root`를 `tr '/' '-'`로 변환하여 프로젝트 경로를 만든다
4. `~/.claude/projects/{project-path}/memory/` 디렉토리 아래에 저장한다

이렇게 하면 워크트리에서 실행해도 원본 레포 기준 경로에 저장되어, Claude Code가 로드하는 메모리 경로와 일치한다.

**메모리 파일 작성:**

파일명: `project_current_issue.md`

```markdown
---
name: current-working-issue
description: 현재 작업 중인 GitHub 이슈 #{번호} - {제목}
type: project
---

## 현재 작업 이슈

- **레포**: {nameWithOwner}
- **이슈**: #{번호} {제목}
- **URL**: {url}
- **라벨**: {라벨 목록}
- **마일스톤**: {마일스톤 또는 없음}
- **선택일**: {현재 날짜}

## 이슈 내용

{이슈 본문}

## 주요 코멘트

{최근 코멘트 요약 — 코멘트가 많으면 최근 5개만. 코멘트가 없으면 이 섹션 생략}
```

**MEMORY.md 인덱스 업데이트:**

프로젝트의 `MEMORY.md`에 해당 메모리 파일에 대한 포인터를 추가하거나 업데이트한다.

```markdown
## Current Issue
- [project_current_issue.md](memory/project_current_issue.md) — 현재 작업 중인 이슈 #{번호}: {제목}
```

기존에 "Current Issue" 섹션이 있으면 교체하고, 없으면 추가한다.

### 6. 완료 보고

사용자에게 선택된 이슈와 메모리 저장이 완료되었음을 간결하게 알린다:

```
✅ 이슈 #{번호} "{제목}"을 작업 이슈로 설정했습니다.
메모리에 저장되어 이후 세션에서도 컨텍스트가 유지됩니다.
```

## 주의사항

- 이미 `project_current_issue.md` 메모리가 존재하면 덮어쓴다 (이전 이슈 → 새 이슈로 교체).
- 이슈 본문이 매우 긴 경우(500줄 이상) 핵심 내용만 요약하여 저장한다. 메모리는 간결해야 한다.
- 코멘트에 코드 리뷰나 기술적 논의가 포함되어 있으면 해당 내용도 메모리에 반영한다.
- 메모리 경로는 **git 원본 레포 루트** 기준으로 결정한다. 워크트리에서 실행해도 원본 레포 경로를 사용해야 Claude Code가 메모리를 정상 로드한다. 예를 들어 cwd가 `/home/seok/development/velvetalk-fe/.claude/worktrees/my-branch`여도 메모리 경로는 `~/.claude/projects/-home-seok-development-velvetalk-fe/memory/project_current_issue.md`이다.
