---
name: followup-clear
description: "현재 저장소의 followups 디렉토리(항목 파일 전체 + INDEX.md)를 삭제하고 state repo 에 반영(다른 PC 에도 사라짐)한 뒤, 양쪽 도구(Claude / Codex) MEMORY.md 의 Followups 섹션을 정리한다. 누적된 후속 조치 항목이 모두 처리됐거나 더 이상 유효하지 않아 한 번에 비우고 싶을 때 사용. 개별 항목만 해결하려면 followup 스킬에서 해당 항목을 Resolved 처리하는 것으로 충분하다. 사용자가 'clear followup', 'delete followup', 'reset followups', 'followup 정리', '후속 조치 비우기', '/followup-clear' 등을 말하면 트리거한다. Usage: /followup-clear [-y]"
model: sonnet
---

# Followup Clear Skill

`followup` 스킬이 만든 `followups/` 디렉토리(항목별 상세 파일 전체 + 생성된 `INDEX.md`)와 양쪽 도구 `MEMORY.md` 의 `## Followups` 섹션을 정리한다. 누적된 항목 전체를 한 번에 비우는 용도이며, 개별 항목 해결은 `/followup` 으로 해당 항목을 Resolved 처리하는 것으로 충분하다. followup 은 state repo 로 동기화되므로 **여기서 지우면 다른 PC 에서도 사라진다.**

## 인자

- `-y`: 확인 없이 즉시 삭제.

## 스크립트

`SF` 는 다음 명령을 뜻한다:

```bash
python3 "${SKILL_DIR}/../../scripts/sfstate.py"
```

```bash
SF prepare
```

출력의 `FOLLOWUPS_DIR`, `INDEX_FILE`, `REPO_KEY`, `MEMORY_KEY`, `SYNC` 를 쓴다.

### MEMORY.md (양쪽 모두)

```text
{CLAUDE_MEMORY_PREFIX}/<MEMORY_KEY>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md
{CODEX_MEMORY_PREFIX}/<MEMORY_KEY>{CODEX_MEMORY_SUFFIX}/MEMORY.md
```

## 실행 흐름

### 1. 위치 확인

`FOLLOWUPS_DIR` 이 없거나 항목 파일이 없으면 사용자에게 "정리할 followup 이 없습니다" 라고 알리고, MEMORY.md 의 잔여 `## Followups` 섹션만 추가로 정리한다 (Step 4).

### 2. 요약과 확인

`INDEX_FILE` 을 읽고 `Open` / `Decisions Pending` 항목 수와 제목 목록을 사용자에게 보여준다.

확인:

- `-y` 가 있으면 그대로 진행.
- 없으면 사용자에게 삭제 여부를 확인받는다 ("Delete (Recommended)" / "Cancel"). `SYNC=on` 이면 다른 PC 에서도 사라진다고 함께 알린다.
- Open + Pending 항목이 5개 이상이면 추가로 한 번 더 경고한다 (실수 방지).

### 3. followups/ 삭제 + 동기화

`FOLLOWUPS_DIR` 디렉토리 전체만 삭제한다. 절대 경로를 따옴표로 감싼다. 소스 레포 파일은 절대 건드리지 않는다.

```bash
rm -rf "<FOLLOWUPS_DIR>"
SF sync -m "followup-clear"
```

같은 저장소의 `handoffs/` 는 절대 건드리지 않는다. 핸드오프 정리는 `handoff-clear` 스킬의 책임이다. `SYNC=` 결과를 보고에 넣는다.

### 4. 양쪽 MEMORY.md 정리

대상 두 파일 각각에 대해:

1. 파일이 있으면 읽는다.
2. `## Followups` 섹션이 있으면 해당 헤딩부터 다음 `## ` 헤딩 직전까지(또는 파일 끝까지) 제거한다.
3. 다른 섹션 내용은 보존한다. 특히 `## Handoff` 섹션이 있다면 건드리지 않는다.
4. 정리 후 파일이 빈 줄/공백만 남으면 `MEMORY.md` 자체를 삭제한다.
5. 파일이 없거나 `## Followups` 섹션이 없으면 그 파일은 건너뛴다.

### 5. 완료 보고

사용자에게 알린다:

- `followups/` 디렉토리가 삭제되었는지 (`REPO_KEY` 와 함께)
- `SYNC` 결과 (다른 PC 에도 반영됐는지)
- 어느 쪽 MEMORY.md 가 갱신/삭제되었는지
- (참고) 같은 저장소의 핸드오프는 그대로 유지된다는 사실
