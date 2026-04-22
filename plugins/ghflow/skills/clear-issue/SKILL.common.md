---
name: clear-issue
description: "pick-issue 스킬로 저장한 현재 작업 이슈 메모리(project_current_issue.md)를 삭제하고 MEMORY.md에서 Current Issue 섹션을 제거하는 스킬. 사용자가 '이슈 정리', '이슈 메모리 삭제', '이슈 클리어', '작업 이슈 지워줘', '이슈 완료', 'clear issue', 'done with issue', 'close issue memory', '/clear-issue' 등을 말하면 트리거한다. 이슈 작업이 끝났거나 메모리를 정리하려는 맥락이면 적극적으로 이 스킬을 사용할 것."
harness: [claude]
---

# Clear Issue

pick-issue 스킬이 프로젝트 메모리에 저장한 현재 작업 이슈 정보를 삭제한다. 이슈 작업이 완료되었거나 다른 이슈로 전환할 때, 이전 이슈 컨텍스트를 깔끔하게 정리하는 용도이다.

## 사용법

```
/clear-issue          # 확인 후 삭제
/clear-issue -y       # 확인 없이 즉시 삭제
```

## 실행 흐름

### 1. 메모리 경로 결정

pick-issue와 동일한 방식으로 프로젝트 메모리 경로를 결정한다.

```bash
# 워크트리 여부에 관계없이 원본 레포 루트를 구한다
git_common=$(git rev-parse --git-common-dir)
repo_root=$(dirname "$git_common")
```

`repo_root`를 `tr '/' '-'`로 변환하여 프로젝트 경로를 만든다.

메모리 디렉토리: `~/.claude/projects/{project-path}/memory/`

### 2. 현재 이슈 메모리 확인

`project_current_issue.md` 파일이 존재하는지 확인한다. 존재하지 않으면 "저장된 작업 이슈가 없습니다."라고 알리고 종료한다.

파일이 존재하면 내용을 읽어서 이슈 번호와 제목을 파악한다.

### 3. 삭제 확인

`-y` 플래그가 **없으면**, 사용자에게 확인을 받는다:

```
현재 작업 이슈: #{번호} "{제목}"

이슈 메모리를 삭제할까요?
```

`-y` 플래그가 **있으면**, 확인 없이 바로 삭제한다.

### 4. 메모리 삭제

두 가지를 처리한다:

1. **`project_current_issue.md` 파일 삭제**
   ```bash
   rm <memory-dir>/project_current_issue.md
   ```

2. **`MEMORY.md`에서 Current Issue 섹션 제거**
   - `MEMORY.md`를 읽는다
   - `## Current Issue`로 시작하는 섹션을 찾아 해당 헤딩부터 다음 `##` 헤딩 직전까지 제거한다
   - 제거 후 불필요한 빈 줄이 연속되면 정리한다
   - 수정된 내용을 저장한다

### 5. 완료 보고

```
이슈 #{번호} "{제목}" 메모리를 삭제했습니다.
```

## 주의사항

- 워크트리에서 실행해도 원본 레포 기준 메모리 경로를 사용한다 (pick-issue와 동일).
- MEMORY.md에 Current Issue 섹션이 없어도 에러 없이 `project_current_issue.md` 파일만 삭제한다.
- MEMORY.md 파일 자체가 없는 경우에도 `project_current_issue.md` 삭제만 수행한다.
