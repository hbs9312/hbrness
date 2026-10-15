---
name: handoff-clear
description: "현재 브랜치(또는 --all 로 저장소 전체)의 핸드오프 파일을 삭제하고 backend 에 반영(다른 PC 에도 사라짐)한 뒤, 양쪽 도구(Claude / Codex) MEMORY.md 의 Handoff 섹션에서 해당 라인을 정리한다. 핸드오프에 적힌 작업이 끝나 다음 세션에서 이어받을 필요가 없을 때 사용. 사용자가 'clear handoff', 'delete handoff', 'remove handoff', 'handoff done', 'handoff complete', '핸드오프 삭제', '핸드오프 정리', '/handoff-clear' 등을 말하면 트리거한다. Usage: /handoff-clear [-y] [--all]"
model: sonnet
---

# Handoff Clear Skill

`handoff` 스킬이 만든 핸드오프 파일과 양쪽 도구 `MEMORY.md` 의 `## Handoff` 섹션에서 해당 라인을 정리한다. 기본은 **현재 브랜치** 의 핸드오프만 정리한다. 핸드오프는 backend 로 동기화되므로 **여기서 지우면 다른 PC 에서도 사라진다.**

`phase-run` / `phase-loop` / `relay` 가 쓰는 로컬 `HANDOFF.md`(`~/.hbrness/sessionflow/<경로키>/...`)는 건드리지 않는다.

## 인자

- `-y`: 확인 없이 즉시 삭제.
- `--all`: 현재 저장소의 **모든** 브랜치 핸드오프를 한 번에 정리. `-y` 와 조합 시 무확인 진행.

## 스크립트

`SF` 는 다음 명령을 뜻한다:

```bash
python3 "${SKILL_DIR}/../../scripts/sfstate.py"
```

```bash
SF prepare
```

출력의 `HANDOFF_FILE`(현재 브랜치), `HANDOFFS_DIR`(저장소 전체), `BRANCH`, `MEMORY_KEY`, `SYNC` 를 쓴다.

### MEMORY.md (양쪽 모두)

```text
{CLAUDE_MEMORY_PREFIX}/<MEMORY_KEY>{CLAUDE_MEMORY_SUFFIX}/MEMORY.md
{CODEX_MEMORY_PREFIX}/<MEMORY_KEY>{CODEX_MEMORY_SUFFIX}/MEMORY.md
```

## 실행 흐름

### 1. 대상 핸드오프 결정

- `--all` 없음: `HANDOFF_FILE` 만
- `--all`: `HANDOFFS_DIR` 아래 모든 `*.md` (하위 디렉토리 포함 — 브랜치 이름의 `/` 는 디렉토리가 된다)

### 2. 존재 확인

대상 파일이 하나도 없으면 사용자에게 "정리할 핸드오프가 없습니다" 라고 알리고 종료한다 (단, MEMORY.md 의 잔여 라인도 추가로 정리 — Step 5 참고).

### 3. 요약과 확인

각 핸드오프의 브랜치·`Host`·`Next Action` (또는 그에 준하는 마지막 메모) 을 사용자에게 보여준다.

- `-y` 가 있으면 그대로 진행.
- 없으면 사용자에게 삭제 여부를 확인받는다 ("Delete (Recommended)" / "Cancel"). `SYNC=on` 이면 다른 PC 에서도 사라진다고 함께 알린다.
- `--all` 인 경우, 삭제될 핸드오프 수가 1개를 넘으면 한 번 더 경고한다.

### 4. 삭제 + 동기화

대상 파일을 삭제한다. 절대 경로를 따옴표로 감싼다. 소스 레포 파일은 절대 건드리지 않는다.

```bash
rm "<path>"
```

삭제 뒤 빈 하위 디렉토리(예: `handoffs/feat/`)는 지운다 (`rmdir`, 실패해도 무시). 같은 저장소의 `followups/` 는 절대 건드리지 않는다 — followup 정리는 `followup-clear` 의 책임이다.

```bash
SF sync -m "handoff-clear: <브랜치 목록>"
```

`SYNC=` 결과를 보고에 넣는다.

### 5. 양쪽 MEMORY.md 정리

대상 두 파일 각각에 대해:

1. 파일이 있으면 읽는다.
2. `## Handoff` 섹션 내부에서 삭제된 핸드오프에 해당하는 라인만 제거한다.
   - 핸드오프 경로(또는 브랜치 이름)가 라인에 포함된 경우를 매칭 기준으로 한다.
   - 예전 형식(`~/.hbrness/sessionflow/...HANDOFF.md`) 라인이 같은 작업을 가리키면 함께 제거한다.
3. `## Handoff` 섹션에 활성 핸드오프 라인이 더 이상 남지 않으면 섹션 자체를 제거한다 (헤딩 ~ 다음 `## ` 직전).
4. 다른 섹션 내용은 보존한다. 특히 `## Followups` 섹션이 있다면 건드리지 않는다.
5. 정리 후 파일이 빈 줄/공백만 남으면 `MEMORY.md` 자체를 삭제한다.
6. 파일이 없거나 `## Handoff` 섹션이 없으면 그 파일은 건너뛴다.

다른 PC 의 MEMORY.md 는 이 PC 에서 고칠 수 없다. 그쪽에 남은 라인은 가리키는 파일이 없어진 상태가 되며, 그 PC 에서 `/handoff load` 나 `/handoff-clear` 를 돌리면 정리된다.

### 6. 완료 보고

사용자에게 알린다:

- 삭제된 핸드오프 (브랜치 + 경로) 목록
- `SYNC` 결과 (다른 PC 에도 반영됐는지)
- 어느 쪽 MEMORY.md 가 갱신/삭제되었는지
- (참고) 같은 저장소의 followups/ 는 그대로 유지된다는 사실
