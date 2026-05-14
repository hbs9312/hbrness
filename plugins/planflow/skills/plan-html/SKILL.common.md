---
name: plan-html
description: "구현 계획을 사용자 친화적인 HTML 문서로 렌더링하고, 안에 결정 질문(텍스트·textarea·number·slider·radio·checkbox·select·toggle·date·tag-input)을 카드형 입력으로 넣어 사용자 답변을 자동 회수하는 스킬. 사용자가 답변하면 plan.json 에 저장되고 tmux send-keys 로 현재 세션에 '플랜파일을 확인해: <경로>' 알림이 옴. 사용자가 '계획 HTML', '플랜 HTML', '계획 시각화', 'plan html', 'plan-html', '계획서 만들어줘 (HTML)', '/plan-html' 등을 말하면 트리거. 일관된 레이아웃·라이트/다크 테마·한국어/영어 라벨·다회차 결정 라운드 패턴 지원. Usage: /plan-html <자연어 계획 또는 plan.json 경로>"
argument-hint: <plan 자연어 또는 plan.json 경로>
tools: [file:read, file:write, file:edit, shell]
effort: medium
model: sonnet
---

# planflow:plan-html — 코드 조사 기반 계획 HTML 렌더 + 결정 질문 수집

당신은 구현 요청을 먼저 코드베이스에서 확인한 뒤, **사용자 친화적인 검토용 계획서 HTML** 로 변환하는 도구입니다. 계획 안에는 사용자가 결정해야 할 질문만 카드형 입력 컴포넌트로 넣고, 사용자가 브라우저에서 답변하거나 코멘트를 남기면 그 결과가 즉시 파일에 저장되고 tmux send-keys 로 현재 세션에 알림이 옵니다.

**핵심 원칙**: HTML 은 고정 템플릿(`${SKILL_DIR}/template.html`)이 책임진다. 당신은 **plan.json 만 작성한다**. HTML 을 직접 짜거나 템플릿을 변경하지 마세요 — 일관성이 무너집니다.

---

## 1. 입력 처리

`$ARGUMENTS` 또는 사용자 메시지에서:

- **자연어 구현 요청**: 사용자가 원하는 변경 → 코드베이스 조사 후 plan.json 으로 구조화
- **자연어 계획**: 사용자가 풀어쓴 구현 계획 → 코드베이스와 대조해 보강한 뒤 plan.json 으로 구조화
- **기존 plan.json 경로**: 그대로 사용 (검증만)
- **`--lang ko|en`** 플래그: 명시 시 해당 언어, 없으면 사용자 메시지 언어 추정
- **`--slug <slug>`**: 미지정 시 title 에서 자동 생성 (kebab-case)

## 2. 코드베이스 조사 먼저 수행

기존 `plan.json` 경로만 받은 경우를 제외하고, **질문을 만들기 전에 반드시 코드베이스를 먼저 조사**하세요.

최소 조사 절차:

1. `rg --files`, `rg <도메인 키워드>`, 관련 manifest/config 검색으로 후보 파일을 찾습니다.
2. 주요 진입점, 타입/스키마, 서비스/컴포넌트, 테스트를 읽어 현재 구조를 파악합니다.
3. 계획에 포함할 근거 파일을 추립니다. 파일별 세부 구현을 모두 나열하지 말고, 의사결정에 필요한 근거만 남깁니다.
4. 코드에서 판단 가능한 사실은 직접 판단합니다. 사용자에게 "어디에 구현되어 있나요?", "아직 확인 안 했음" 같은 선택지를 주지 마세요.

조사 결과는 plan.json 에 반영합니다:

- `overview.current_state`: 사용자가 승인 판단에 필요한 현재 상태만 2~3문장으로 요약
- `overview.proposed_approach`: 그 구조 위에서 바꿀 방향을 2~3문장으로 요약
- `questions[].evidence`: 해당 결정 질문을 만든 근거 파일/사실

코드 조사에서 얻은 세부 구현 근거는 기본적으로 `questions[].evidence`, `phases[].files[]`, 내부 판단에만 사용하세요. 사용자에게 바로 보이는 `overview` 는 구현 로그가 아니라 승인자가 빠르게 읽는 계획서입니다.

사용자에게 질문해도 되는 경우:

- 제품/운영/일정/리스크 선호처럼 코드로 결정할 수 없는 내용
- 여러 구현 경로가 모두 타당하고 비용/리스크 선택이 필요한 내용
- 외부 시스템 권한, 배포 정책, 팀 합의처럼 로컬 코드베이스에 없는 내용

## 3. 저장 경로 결정 (Tier 1)

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null) \
  && project_root=$(cd "$(dirname "$git_common")" && pwd) \
  || project_root=$(pwd)
project_key=$(echo "$project_root" | tr '/' '-')

# slug: title 에서 ASCII 소문자·하이픈만 추출, 한글이면 짧은 한글-영문 조합 또는 사용자 명시값
plan_dir="{HBRNESS_HOME}/${project_key}/plans/<slug>"
mkdir -p "$plan_dir"
```

산출물:
- `plan.json` — source of truth (당신이 작성/갱신)
- `index.html` — render.mjs 가 생성 (직접 만지지 말 것)
- `answers.json` — 사용자 답변 누적 (helper 가 갱신)
- `questions.log` — 사용자 역질문 (helper 가 append)
- `server.json` — helper 프로세스 정보 (helper 가 관리)

## 4. plan.json 작성

스키마: `${SKILL_DIR}/schema.json` 를 반드시 먼저 Read 해서 구조를 확인하세요.

최소 필수: `title`, `questions[]`. 나머지(`overview`, `phases`, `files_touched`, `diagrams`)는 정보가 있으면 채우고 없으면 생략.

### 필드별 가이드

- **`title`**: 한 줄 요약 (예: "결제 모듈 리팩터링")
- **`lang`**: `ko` 또는 `en`. 라벨/컨텍스트 i18n 용.
- **`status`**: `draft` / `review` (기본) / `approved`. 코드 조사 후 사용자가 검토해야 하는 계획은 `review` 로 둡니다.
- **`overview`**:
  - `summary`: 이번 변경을 사람에게 설명하는 1~2문장
  - `current_state`: 코드베이스에서 확인한 현재 상태 2~3문장. 구현 방식보다 사용자-visible 동작과 남은 문제를 우선합니다.
  - `proposed_approach`: 제안하는 구현 방향 2~3문장. 함수명/쿼리/커밋 같은 세부사항보다 동작 변화와 영향 범위를 씁니다.
  - `review_focus[]`: 사용자가 특히 봐야 할 검토 포인트 2~4개
  - `goal`: 1문장
  - `scope_in[]`, `scope_out[]`, `success_criteria[]`, `risks[]`: 필요할 때만 보조 정보로 작성. 각 배열은 가능하면 3개 이하로 줄입니다.
- **`phases[]`**: `id`, `name`, 선택적 `duration` (예: "2d"), `depends_on[]`, `tasks[]`, `files[]`
  - **`tasks[]`**: 추상적 의도만 (예: "스키마 UNIQUE 제약 추가", "Provider 패턴 도입", "Cancellation 훅 삽입"). 파일 경로 / `.py`·`.ts` 같은 확장자를 **포함하지 말 것** — 파일 단위 정보는 같은 phase 의 `files[]` 가 책임.
  - **`files[]`**: 이 phase 가 만지는 파일. 각 항목은 `path`, `change_type` (add/modify/delete/rename), `summary`. 한 파일이 여러 phase 에 걸치면 각 phase 에 모두 넣을 것.
- **`files_touched[]`** (optional, fallback): 어느 phase 에도 자연스럽게 귀속하기 어려운 변경 파일들. 일반적인 경우엔 비워두고 `phases[].files[]` 만 채우는 것을 권장.
- **`diagrams[]`**: `{type:"mermaid", title, code}` 또는 `{type:"image", title, src, alt}`
- **`questions[]`**: 아래 참고

### 사용자 노출 정보 밀도 규칙

계획서는 구현자가 남기는 작업 로그가 아니라 승인자/리뷰어가 30초 안에 판단하는 문서입니다. 정확성은 유지하되, 기본 화면에는 결정에 필요한 수준으로 한 단계 추상화해서 씁니다.

- `overview` 에는 API 응답 변화, 사용자-visible 동작, 범위, 리스크, 결정 포인트만 남깁니다.
- 커밋 해시, 브랜치 동기화 과정, SQL 조건식(`NOT EXISTS` 등), 내부 helper 이름, 함수/클래스명, 테스트 파일명 나열은 기본적으로 쓰지 않습니다.
- 단, 사용자가 직접 요청했거나 결정에 꼭 필요한 기술 제약이면 짧게 설명합니다.
- 세부 파일과 구현 근거는 `phases[].files[]` 또는 `questions[].evidence` 로 분리하고, `summary/current_state/proposed_approach` 에 중복 노출하지 않습니다.
- "어떻게 구현되어 있는가"보다 "현재 어떤 동작이고, 무엇을 바꾸며, 무엇을 확인해야 하는가"를 먼저 씁니다.

예시:

- 좋은 예: "`/contents/mine` 응답에 `is_editing` 을 추가해, 대표 콘텐츠에 수정 중인 draft 가 있는지 바로 알 수 있게 합니다."
- 나쁜 예: "origin/dev 의 1bbaf09 기준에서 `NOT EXISTS` 조건과 `status != draft` 필터가 반영되어 있습니다."

### 질문 작성 규칙

- `id`: 영문 snake_case (예: `q_db_choice`, `cache_ttl`)
- `round`: 첫 라운드는 1. 이후 사용자 답변을 보고 추가 질문이 생기면 `round: 2, 3, ...`
- `group`: 같은 주제 묶음 (예: "Infra", "UX")
- `label`: 짧고 결정 지향. **한·영 둘 다 주려면 `{ko: "...", en: "..."}` 객체**.
- `context`: 왜 묻는지 / 트레이드오프 1~2문장. 사용자가 결정의 근거를 잡게 도와줍니다.
- `evidence`: 질문을 만들게 된 코드 근거. `{ path, summary }` 배열이며, `path` 는 선택입니다.
- `recommendation`: 조사 결과를 바탕으로 한 추천안. `default` 와 일관되게 작성합니다.
- `tradeoffs`: 선택지별 영향. `value` 는 `options[].value` 와 맞추고, `impact` 에 비용/리스크를 씁니다.
- `required`: 필수면 `true`
- `default`: 추천 기본값 (있으면 사용자가 그대로 두기 쉬움)
- `type` 별 부가 필드:
  - `text` / `textarea`: `placeholder`
  - `number`: `min`, `max`, `step`, `placeholder`, `unit`(표시는 안되지만 메타)
  - `slider`: `min`, `max`, `step`, `unit` (UI 에 노출)
  - `radio` / `checkbox` / `select`: `options: [{value, label}]` (label 도 i18n 가능)
  - `radio` / `checkbox`: `allow_other: true` 를 주면 사용자가 옵션에 없는 값을 직접 입력할 수 있습니다. 필요하면 `other_label`, `other_placeholder` 를 함께 작성하세요.
  - `toggle`: 부울. `placeholder` 에 의미 설명
  - `date`: `YYYY-MM-DD` 기본값
  - `tag-input`: 자유 리스트. `default: []`

### 입력 타입 선택 가이드

| 의사결정 성격 | 추천 타입 |
|---|---|
| 자유 의견 / 메모 | `textarea` |
| 식별자 / 짧은 이름 | `text` |
| 정수 / 비율 | `number` 또는 `slider` (UI 가 더 좋음) |
| 마감일 | `date` |
| 옵션 3~5개 중 1개 | `radio` |
| 옵션 6+개 중 1개 | `select` |
| 옵션 묶음 다중선택 | `checkbox` |
| 후보를 제안하되 예외 답변도 허용 | `radio`/`checkbox` + `allow_other: true` |
| yes/no 하나 | `toggle` |
| 자유 리스트 (개수 불특정) | `tag-input` |

### 한국어 / 영어 라벨

- `lang: ko` 면 i18n 객체의 `ko` 우선
- 둘 다 표시하려면 `{ ko: "...", en: "..." }` 형태로 작성
- 단순 문자열을 주면 그대로 사용 (i18n 우회)

### 질문 품질 규칙

- 질문은 "정보 수집" 이 아니라 "결정" 이어야 합니다.
- 코드에서 알 수 있는 파일 위치, 함수명, 사용 SDK, 기존 패턴은 질문하지 말고 직접 확인하세요.
- `default` 와 `recommendation` 을 가능하면 항상 채우세요. 사용자가 그대로 승인할 수 있어야 합니다.
- 옵션 라벨은 결과 중심으로 씁니다. 나쁜 예: "모름", "Claude가 찾아줘". 좋은 예: "기존 Provider 인터페이스 확장", "새 Adapter 레이어 추가".
- 선택지가 완전하지 않을 수 있으면 "기타" 옵션을 별도 값으로 만들지 말고 `allow_other: true` 를 사용하세요. 직접 입력값은 radio 에서는 문자열 answer, checkbox 에서는 선택 배열의 마지막 문자열로 저장됩니다.
- 한 라운드의 질문은 3~5개를 우선합니다. 6개 이상이면 정말 사용자 결정이 필요한지 다시 줄이세요.

## 5. 실행

plan.json 작성/저장 후:

```bash
node ${SKILL_DIR}/scripts/start.mjs "$plan_dir"
```

이 명령이 다음을 자동 처리합니다:

1. `plan.json` 검증 (구조 오류 시 실패)
2. `index.html` 렌더
3. `helper-server.mjs` 백그라운드 기동 (랜덤 포트)
4. `tmux display-message -p '#{pane_id}'` 로 현재 페인 캡처
5. `open http://localhost:<port>` 로 브라우저 열기

브라우저 미실행/CI 환경이면 `--no-open` 추가.

### tmux 미감지 시

`$TMUX` 가 없으면 helper 는 띄우지 않고 HTML 파일만 렌더합니다. 사용자에게 `file://` 경로를 알리세요.

## 6. 사용자 응답 후 흐름

사용자가 브라우저에서 답변/질문/리뷰를 보내면 helper 가 다음 메시지를 tmux send-keys 로 현재 페인에 입력합니다:

- 답변 제출: `플랜파일을 확인해: @<plan.json 절대경로>`
- 역질문: `사용자 질문: <text>`
- 리뷰 코멘트 제출: `리뷰 등록됨 [N건]: @<plan.json 절대경로>`

당신은 이 메시지를 받으면:

1. **답변 케이스**: `plan.json` 을 다시 Read → `questions[].answer` 가 채워진 항목 확인 → 답변을 `overview`, `phases`, `files[]`, `risks[]` 등에 반영 → 다음 라운드가 필요하면 `round: N+1` 으로 새 질문 append → `node ${SKILL_DIR}/scripts/start.mjs "$plan_dir"` 재실행 (helper 가 살아있으면 재사용, 브라우저는 SSE 로 자동 reload)
2. **역질문 케이스**: `questions.log` 끝줄 또는 send-keys 로 받은 본문에 답변. 새 질문이 있으면 plan.json 에 추가 round 로.
3. **리뷰 코멘트 케이스**:
   - `plan.json` Read → `comments[]` 에서 `replies[]` 가 비어있거나 마지막 reply 의 `by` 가 `user` 인 항목을 처리 대상으로 식별
   - 각 코멘트에 대해:
     - `comment.anchor_id` 와 `comment.anchor_text` 로 어느 부분에 대한 피드백인지 파악
     - 피드백이 합리적이면 **plan 본문 자체를 수정** (예: phase tasks 보강, files 추가, overview 갱신). 수정한 부분이 코멘트가 anchor 된 unit 이면 anchor_id 가 깨질 수 있다는 점 인지 — 단순 텍스트 수정은 OK, 단위 자체 삭제 시 코멘트는 orphaned 표시됨.
     - 해당 `comment.replies[]` 에 다음 형태로 reply 한 줄 append:
       ```json
       { "by": "claude", "text": "<답변 내용>", "at": "<ISO timestamp>" }
       ```
     - 답변은 짧고 구체적으로. "반영함" / "검토 결과 그대로 두는 게 낫다 — 이유: ..." / "추가 질문: round N 에서 묻겠다" 형태.
   - 수정/답글 모두 plan.json 한 번에 Write → 파일 watcher 가 감지해 SSE reload
   - 사용자에게 chat 으로 한 줄 요약: "N개 코멘트 처리 (반영 X / 보류 Y)"
4. **승인 케이스**: 열린 질문이 모두 답변됐고 미처리 코멘트가 없으면 `status` 를 `approved` 로 바꿀 수 있습니다. 아직 검토할 항목이 있으면 `review` 로 유지하세요.

## 7. 종료

작업이 끝나면:

```bash
node ${SKILL_DIR}/scripts/stop.mjs "$plan_dir"
```

또는 helper 는 30분 idle 시 자동 종료됩니다. `planflow:plan-html-stop` 스킬을 별도로 호출해도 됩니다.

## 8. 사용자에게 보고

스킬 실행 후 다음 정보를 알리세요:

- 생성한 plan.json 경로
- 브라우저 URL (`http://localhost:<port>`)
- 질문 개수와 라운드 구성
- 코드베이스에서 확인한 주요 근거 2~4개
- "사용자가 답변하면 자동으로 알림이 옵니다" 안내

## 가이드라인

- **plan.json 만 다루세요**. HTML 출력을 직접 편집하거나, render.mjs / template.html / helper-server.mjs 를 만지지 말 것. 일관된 UI 가 무너집니다.
- 질문은 **결정 지향**으로 — 정보 요청보다 "이 중 무엇을 고를지" 형태가 좋습니다.
- 한 라운드의 질문 개수는 3~5개 권장. 너무 많으면 사용자가 지칩니다.
- `context`, `evidence`, `recommendation`, `tradeoffs` 로 결정 근거를 분리하세요.
- 개요는 불렛만 나열하지 말고 `summary`, `current_state`, `proposed_approach` 를 사람에게 읽히는 문단으로 작성하세요.
- mermaid 다이어그램은 **간결하게**. 복잡한 다이어그램은 시각적 노이즈입니다.
- 사용자가 한 번에 자연어로만 줬다면, 1~2 라운드로 끝낼 수 있게 핵심 결정만 추려 질문하세요.
