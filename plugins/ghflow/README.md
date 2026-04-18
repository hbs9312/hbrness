# ghflow

GitHub 이슈·PR·리뷰·커밋 기록을 잇는 워크플로우 스킬 모음.

## 워크플로우

```
pick-issue → draft-pr → (작업 + commit → chronicle) → create-pr → review-pr → clear-issue
                ↑                                           ↑
          create-issue (필요 시)               chronicle-lookup (과거 결정 조회)
```

## 스킬

| 스킬 | 트리거 | 역할 |
|---|---|---|
| `create-issue` | `/create-issue`, "이슈 만들어줘" | 조직 이슈 템플릿에 맞춰 GitHub 이슈 생성 |
| `pick-issue` | `/pick-issue`, "내 이슈 보여줘" | assigned 이슈 목록 → 선택 → 프로젝트 메모리에 저장 |
| `draft-pr` | `/draft-pr`, "Draft PR 만들어줘" | 이슈 번호 기반으로 브랜치+빈 커밋+Draft PR 생성, 이슈 연결 |
| `create-pr` | `/create-pr`, "PR 만들어줘" | 조직 PR 템플릿(`.github` 레포)을 가져와 PR 생성 |
| `review-pr` | `/review-pr`, "PR 리뷰 확인" | PR 리뷰 댓글 가져와 코드와 함께 검토 |
| `clear-issue` | `/clear-issue`, "이슈 정리" | pick-issue가 저장한 현재 작업 이슈 메모리 삭제 |
| `chronicle` | `/chronicle`, "커밋 기록해줘" | git commit 의 의도·결정·트레이드오프를 `~/.commit-chronicles/` 에 기록 |
| `chronicle-lookup` | `/chronicle-lookup`, "왜 이렇게 짰지?" | 과거 chronicle 검색·표시 (SHA / 파일 / 기간 / 키워드) |

## 템플릿 로딩 (SessionStart 훅)

Claude Code 세션이 시작되면 `hooks/fetch-templates.py`가 자동 실행되어 현재 레포와 조직의 `.github` 레포에서 이슈/PR 템플릿을 가져온다. 결과는 `/tmp/ghflow/<org>__<repo>/templates.json`에 저장되며, `create-issue`·`create-pr` 스킬이 이 파일을 직접 읽어 사용한다.

- **캐시 없음**: 세션 시작 시마다 원본에서 새로 가져오고, 세션 내내 그 스냅샷을 사용한다.
- **병합 규칙**: 현재 레포 템플릿이 조직 `.github` 레포 템플릿보다 우선한다. 파일명이 겹치면 현재 레포가 이긴다.
- **훅이 실패한 경우**: gh 미인증, 네트워크 문제 등으로 파일이 없으면 스킬이 사용자에게 안내한 뒤 템플릿 없이 진행할지 묻는다.
- **갱신 방법**: 원격에서 템플릿이 바뀌면 Claude Code 세션을 재시작한다.

## 커밋 기록 (PostToolUse 훅 + chronicle 스킬)

`git commit` 이 성공하면 `hooks/commit-chronicle.py` 가 PostToolUse 로 실행되어 Claude 에게 `ghflow:chronicle` 을 호출하도록 유도한다. 훅은 감지만 하고, 실제 기록은 스킬이 현재 대화 컨텍스트에서 의도·의사결정·대안·트레이드오프를 뽑아 작성한다.

저장 위치는 **프로젝트 바깥** 인 `~/.commit-chronicles/<host>__<owner>__<repo>/YYYY/MM/` 이며, 어떤 AI 도구나 사람이든 읽을 수 있는 **YAML frontmatter + 마크다운** 형식이다. 세션에 자동 주입되지 않고, 필요할 때 `ghflow:chronicle-lookup` 이나 `grep` 으로 조회한다.

- **Non-blocking**: 훅은 막지 않는다. 대화에 맥락이 없으면 Claude 가 건너뛴다.
- **Idempotent**: 같은 SHA 에 대한 chronicle 이 이미 있으면 훅이 조용히 지나간다 (amend/rebase 노이즈 방지).
- **Schema**: `commit-chronicle/v1` — `What changed / Why / Key decisions / Alternatives / Tradeoffs / Related / Future notes` 섹션.
- **부트스트랩**: 처음 실행 시 `~/.commit-chronicles/README.md` 가 자동 생성되어 포맷을 설명한다.

## 의존성

- `gh` CLI 인증 필요 (`gh auth login`) — 이슈/PR 계열 스킬
- 조직 템플릿 사용 시 `.github` 레포 접근 권한 필요
- `python3` (macOS·대부분의 Linux에 기본 포함) — SessionStart / PostToolUse 훅 실행에 사용
- `git` — chronicle 계열 스킬 및 훅에서 메타데이터 조회
