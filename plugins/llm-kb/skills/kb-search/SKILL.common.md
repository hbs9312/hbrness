---
name: kb-search
description: "개인 지식 베이스(LLM Wiki)에서 특정 개념·키워드를 검색해 관련 항목을 보여준다. 사용자가 'kb 검색', '지식 검색', 'KB에서 찾아줘', '내가 저장한 거 보여줘', 'PITR이 뭐였더라', 'search kb', 'kb-search', '/kb-search' 등을 말하면 트리거한다. KB 자동 저장 훅이 누적해 둔 ~/.hbrness/llm-kb/entries/ 의 한국어 노트들을 대상으로 한다. Usage: /kb-search <query>"
model: haiku
tools: [search:grep, search:glob, file:read]
---

# kb-search Skill

사용자가 자신의 LLM Wiki(`~/.hbrness/llm-kb/`)에서 개념을 다시 꺼내 볼 때 쓰는 스킬. 자동 저장 훅이 누적해 둔 한국어 노트를 빠르게 찾아 준다.

## 인자

- `<query>` — 한글/영어 키워드. 슬러그(`pitr`)·표제(`Point-in-Time Recovery`)·본문 어디에 있어도 매치.

## 대상 디렉토리

```text
~/.hbrness/llm-kb/entries/
```

디렉토리가 없거나 비어 있으면 "KB가 비어 있습니다. Stop 훅이 아직 항목을 만들지 않았거나, llm-kb 플러그인이 새 환경입니다." 라고 안내한다.

## 실행 흐름

### 1. 디렉토리 존재 확인

`~/.hbrness/llm-kb/entries/` 가 있는지 확인한다. 없으면 위 안내 후 종료.

### 2. 검색

사용자 query 를 case-insensitive 로 grep 한다. 본문(`name`, `description`, `aliases`, body) 전체를 대상.

- 1차: query 를 그대로 grep. `\bquery\b` 단어 경계 시도.
- 매치가 비면 2차: query 를 공백으로 토큰화해 OR 매치.
- 매치가 여전히 비면 3차: query 의 substring 으로 슬러그 비교 (`ls entries/` 후 fuzzy match).

### 3. 출력 포맷

상위 5개를 다음 포맷으로 보여준다. 길이는 1줄 요약 위주.

```text
검색어: "<query>" — N개 항목 매치

1. [PITR (Point-in-Time Recovery)](~/.hbrness/llm-kb/entries/pitr.md)
   DB의 특정 시점 상태로 복원하는 기능 [database, backup]

2. ...

(N>5 인 경우) 외 N-5개 더 있음 — 더 보고 싶으면 `/kb-list <domain>` 사용.
```

각 항목은:
- 1줄째: `[표제](파일경로)` — 사용자가 클릭 가능한 형태.
- 2줄째: `description` (frontmatter에서) + 도메인 태그.

### 4. 매치 0개일 때

```text
"<query>" 와 일치하는 항목이 없습니다.

비슷한 슬러그: pitr-recovery, point-in-time, ...
또는 `/kb-list` 로 전체 목록을 보세요.
```

비슷한 슬러그는 `ls entries/` 결과에서 query 의 일부 substring 매치를 보여준다.

## 가이드라인

- 본문 전체를 출력하지 말 것 — 사용자가 파일 경로 클릭해 직접 열게 한다.
- query 가 너무 짧으면 (2자 이하) "더 구체적으로 입력해 주세요" 라고 응답.
- 항상 실제 파일 시스템을 읽어서 결과를 만든다. 환각 항목 금지.
