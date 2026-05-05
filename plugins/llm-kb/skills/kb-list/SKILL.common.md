---
name: kb-list
description: "개인 지식 베이스(LLM Wiki)의 전체 목록 또는 특정 도메인의 항목들을 보여준다. 사용자가 'kb 목록', 'kb 리스트', '내 지식 베이스 보여줘', 'wiki 목록', 'kb-list', '/kb-list', '/kb-list database' 등을 말하면 트리거한다. ~/.hbrness/llm-kb/INDEX.md 를 기준으로 한다. Usage: /kb-list [domain]"
model: haiku
tools: [file:read, search:glob, shell]
---

# kb-list Skill

`~/.hbrness/llm-kb/INDEX.md` 를 기준으로 사용자가 가진 지식 베이스 항목을 둘러본다.

## 인자

- (인자 없음) — 전체 INDEX 를 도메인별로 그대로 보여준다.
- `<domain>` — 해당 도메인 섹션만 필터링. 예: `/kb-list database`.

## 대상 파일

```text
~/.hbrness/llm-kb/INDEX.md
~/.hbrness/llm-kb/entries/
```

INDEX.md 가 없으면 entries/ 를 직접 walk 하여 임시 출력. 둘 다 없으면 "KB가 비어 있습니다" 안내.

## 실행 흐름

### 1. INDEX 읽기

`~/.hbrness/llm-kb/INDEX.md` 를 읽는다.

- 있으면 그대로 사용.
- 없고 `entries/` 에 항목이 있으면, `ls -la entries/` 로 슬러그 목록을 만들어 임시 출력 (도메인 분류 없음).

### 2. 도메인 인자 처리

`<domain>` 이 주어지면:
- INDEX 에서 `## <domain>` 섹션을 찾아 그 섹션만 출력.
- 매치되는 도메인이 없으면 가용 도메인 목록을 안내.

### 3. 출력 형식

전체 목록일 때:

```text
지식 베이스 — 총 N개 항목 · 마지막 갱신 {timestamp}

## database (3)
- [PITR](~/.hbrness/llm-kb/entries/pitr.md) — DB의 특정 시점 상태로 복원
- ...

## frontend (2)
- ...
```

도메인 필터일 때:

```text
도메인: database (3개 항목)

- [PITR](~/.hbrness/llm-kb/entries/pitr.md) — DB의 특정 시점 상태로 복원
- ...
```

### 4. 항목 너무 많으면

50개 초과시 도메인별 카운트만 먼저 보여 주고 "전체를 보려면 `/kb-list <domain>` 사용" 안내.

## 가이드라인

- INDEX.md 본문을 그대로 베껴 보여 주는 것이 기본. 절대 임의로 항목을 만들어 내지 말 것.
- 사용자가 도메인 이름을 정확히 모를 가능성 — 비슷한 도메인 자동 제안.
- 파일 경로는 절대 경로(`~/.hbrness/...`)로 노출해 사용자가 바로 열 수 있게.
