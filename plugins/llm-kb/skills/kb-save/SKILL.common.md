---
name: kb-save
description: "방금 어시스턴트가 한 답변을 LLM Wiki(개인 지식 베이스)에 강제로 저장한다. 자동 Stop 훅이 skip 한 항목을 사용자가 수동으로 남기고 싶을 때 쓴다. 사용자가 'kb 저장', '지식 저장', '이거 저장해둬', '방금 답변 KB에 넣어', 'save to kb', 'kb-save', '/kb-save', '/kb-save PITR' 등을 말하면 트리거한다. Usage: /kb-save [개념명]"
model: sonnet
tools: [file:read, file:write, file:edit, shell]
---

# kb-save Skill

자동 KB 훅이 저장하지 않은 항목(필터에서 떨어졌거나, 판정 LLM이 `skip` 한 경우)을 **사용자가 수동으로** 강제 저장한다. `~/.hbrness/llm-kb/entries/` 에 한국어 단일 markdown 파일로 추가한다.

## 인자

- (인자 없음) — 어시스턴트 답변에서 핵심 개념명을 자동 추론해 사용.
- `<개념명>` — 사용자가 직접 표제를 지정. 한글/영어 무관.

## 저장 위치 (Tier 1 — 도구 무관 공유)

```text
~/.hbrness/llm-kb/entries/<slug>.md
~/.hbrness/llm-kb/INDEX.md            # 갱신
```

## 실행 흐름

### 1. 컨텍스트 수집

대상 컨텍스트 = **현재 대화에서 사용자의 마지막 질문과 어시스턴트의 마지막 답변**. 다음 우선순위로 수집한다.

1. 직전 어시스턴트 turn 의 본문(스킬을 호출하는 직전의 자기 응답).
2. 그 직전 사용자 turn (질문 컨텍스트로만 사용).
3. 사용자가 인자로 `<개념명>` 을 줬다면 그 단어를 표제 후보로 우선.

답변에 코드 블록만 있고 설명이 없으면 사용자에게 "설명 텍스트가 없어서 추출이 어렵다 — 다시 설명해 달라" 고 안내하고 중단한다.

### 2. 저장 가능성 검사

다음에 해당하면 사용자에게 확인을 받고 진행하거나 중단한다.

- **민감 정보 후보 (credential, token, 내부 호스트명, 회사 내부 시스템명)** — 발견 시 해당 부분을 마스킹할지/저장 취소할지 사용자에게 묻는다.
- **프로젝트 한정 컨텍스트** ("이 프로젝트", "이 코드", 특정 파일/함수명) — 사용자에게 "프로젝트 한정 내용입니다. 그래도 저장합니까?" 확인. yes 면 진행, no 면 중단.

### 3. 한국어 변환

원문이 영어든 한글이든 **저장은 무조건 한국어**로. 영어 개념은 한국어 설명 + 괄호 안에 원어 병기. 다음 골격으로 추출:

```yaml
name: "한국어 표제 (원어)"
slug: kebab-ascii-slug   # 영어/로마자 기반. 예: pitr, kafka-rebalancing
description: "한 줄 요약 (한국어, 80자 이내)"
domain: [주-도메인, 선택-부도메인]   # 예: [database, backup]
aliases: [원어, 다른 한국어 표기]
```

본문(body):
1. 정의 — 한 문단.
2. 핵심 메커니즘/사용 맥락 — 1~2 문단.
3. (있으면) 비교/관련 개념.

### 4. 파일 작성

`~/.hbrness/llm-kb/entries/<slug>.md` 가:

- **없으면** → 새로 작성. `created_at = updated_at = 지금(KST)`.
- **이미 있으면** → 기존 파일을 읽어 사용자에게 보여주고:
  - "덮어쓰기 (overwrite)" / "병합 (merge)" / "취소 (cancel)" 중 선택받는다.
  - merge 시 본문은 기존 + 새 내용 통합, frontmatter 의 `created_at` 은 보존, `updated_at` 만 갱신.

저장 포맷:

```markdown
---
name: "<한국어 표제 (원어)>"
slug: <slug>
description: "<한 줄 요약>"
domain:
  - <domain1>
  - <domain2>
aliases:
  - "<alias1>"
  - "<alias2>"
lang: ko
source: kb-save
created_at: <ISO-8601 KST>
updated_at: <ISO-8601 KST>
---

# <한국어 표제 (원어)>

<본문>
```

### 5. INDEX.md 갱신

`~/.hbrness/llm-kb/INDEX.md` 를 다음과 같이 갱신:

- 파일이 없으면 새로 만든다.
- 해당 도메인 섹션이 있으면 항목을 추가/갱신.
- 없으면 새 도메인 섹션을 알파벳 순으로 끼워 넣는다.
- 헤더의 "마지막 갱신" 타임스탬프와 "총 N개 항목" 카운트도 갱신.

INDEX 형식:

```markdown
# Knowledge Base Index

> 마지막 갱신: <ISO-8601 KST>  ·  총 <N>개 항목

## <domain>
- [<표제>](entries/<slug>.md) — <description>
```

### 6. 완료 보고

사용자에게 알린다:

- 저장된 파일의 절대 경로.
- 새로 만들었는지 / 덮어썼는지 / 병합했는지.
- INDEX 가 갱신되었는지.

## 가이드라인

- **언어 강제 한국어**. 사용자가 영어로 요청해도 저장은 한국어.
- **개념 1개 = 파일 1개**. 답변이 여러 개념을 다뤘다면 가장 핵심 하나만 저장하고 나머지는 사용자에게 "/kb-save 추가로 저장하시려면 다음 개념명을 알려주세요" 안내.
- 디렉토리가 없으면 `mkdir -p ~/.hbrness/llm-kb/entries` 로 생성.
- 어떤 경우에도 사용자 확인 없이 기존 파일을 덮어쓰지 말 것.
