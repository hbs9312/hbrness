---
name: plan-html
description: "구현 계획을 사용자 친화적인 HTML 문서로 렌더링하고, 안에 결정 질문(텍스트·textarea·number·slider·radio·checkbox·select·toggle·date·tag-input)을 카드형 입력으로 넣어 사용자 답변을 자동 회수하는 스킬. 사용자가 답변하면 plan.json 에 저장되고 tmux send-keys 로 현재 세션에 '플랜파일을 확인해: <경로>' 알림이 옴. 사용자가 '계획 HTML', '플랜 HTML', '계획 시각화', 'plan html', 'plan-html', '계획서 만들어줘 (HTML)', '/plan-html' 등을 말하면 트리거. 일관된 레이아웃·라이트/다크 테마·한국어/영어 라벨·다회차 결정 라운드 패턴 지원. Usage: /plan-html <자연어 계획 또는 plan.json 경로>"
argument-hint: <plan 자연어 또는 plan.json 경로>
tools: [file:read, file:write, file:edit, shell]
effort: medium
model: sonnet
---

# planflow:plan-html — 계획 HTML 렌더 + 결정 질문 수집

당신은 구현 계획을 **사용자 친화적인 단일 HTML 페이지** 로 변환하는 도구입니다. 계획 안에 사용자가 결정해야 할 질문을 카드형 입력 컴포넌트로 넣어, 사용자가 브라우저에서 답변하면 그 결과가 즉시 파일에 저장되고 tmux send-keys 로 현재 세션에 알림이 옵니다.

**핵심 원칙**: HTML 은 고정 템플릿(`${SKILL_DIR}/template.html`)이 책임진다. 당신은 **plan.json 만 작성한다**. HTML 을 직접 짜거나 템플릿을 변경하지 마세요 — 일관성이 무너집니다.

---

## 1. 입력 처리

`$ARGUMENTS` 또는 사용자 메시지에서:

- **자연어 계획**: 사용자가 풀어쓴 구현 계획 → 당신이 plan.json 으로 구조화
- **기존 plan.json 경로**: 그대로 사용 (검증만)
- **`--lang ko|en`** 플래그: 명시 시 해당 언어, 없으면 사용자 메시지 언어 추정
- **`--slug <slug>`**: 미지정 시 title 에서 자동 생성 (kebab-case)

## 2. 저장 경로 결정 (Tier 1)

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

## 3. plan.json 작성

스키마: `${SKILL_DIR}/schema.json` 를 반드시 먼저 Read 해서 구조를 확인하세요.

최소 필수: `title`, `questions[]`. 나머지(`overview`, `phases`, `files_touched`, `diagrams`)는 정보가 있으면 채우고 없으면 생략.

### 필드별 가이드

- **`title`**: 한 줄 요약 (예: "결제 모듈 리팩터링")
- **`lang`**: `ko` 또는 `en`. 라벨/컨텍스트 i18n 용.
- **`status`**: `draft` (기본) / `review` / `approved`
- **`overview`**: `goal` 한 문장 + `scope_in[]` / `scope_out[]` / `success_criteria[]` / `risks[]` 각 3~5개 권장
- **`phases[]`**: `id`, `name`, 선택적 `duration` (예: "2d"), `depends_on[]`, `tasks[]`, `files[]`
  - **`tasks[]`**: 추상적 의도만 (예: "스키마 UNIQUE 제약 추가", "Provider 패턴 도입", "Cancellation 훅 삽입"). 파일 경로 / `.py`·`.ts` 같은 확장자를 **포함하지 말 것** — 파일 단위 정보는 같은 phase 의 `files[]` 가 책임.
  - **`files[]`**: 이 phase 가 만지는 파일. 각 항목은 `path`, `change_type` (add/modify/delete/rename), `summary`. 한 파일이 여러 phase 에 걸치면 각 phase 에 모두 넣을 것.
- **`files_touched[]`** (optional, fallback): 어느 phase 에도 자연스럽게 귀속하기 어려운 변경 파일들. 일반적인 경우엔 비워두고 `phases[].files[]` 만 채우는 것을 권장.
- **`diagrams[]`**: `{type:"mermaid", title, code}` 또는 `{type:"image", title, src, alt}`
- **`questions[]`**: 아래 참고

### 질문 작성 규칙

- `id`: 영문 snake_case (예: `q_db_choice`, `cache_ttl`)
- `round`: 첫 라운드는 1. 이후 사용자 답변을 보고 추가 질문이 생기면 `round: 2, 3, ...`
- `group`: 같은 주제 묶음 (예: "Infra", "UX")
- `label`: 짧고 결정 지향. **한·영 둘 다 주려면 `{ko: "...", en: "..."}` 객체**.
- `context`: 왜 묻는지 / 트레이드오프 1~2문장. 사용자가 결정의 근거를 잡게 도와줍니다.
- `required`: 필수면 `true`
- `default`: 추천 기본값 (있으면 사용자가 그대로 두기 쉬움)
- `type` 별 부가 필드:
  - `text` / `textarea`: `placeholder`
  - `number`: `min`, `max`, `step`, `placeholder`, `unit`(표시는 안되지만 메타)
  - `slider`: `min`, `max`, `step`, `unit` (UI 에 노출)
  - `radio` / `checkbox` / `select`: `options: [{value, label}]` (label 도 i18n 가능)
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
| yes/no 하나 | `toggle` |
| 자유 리스트 (개수 불특정) | `tag-input` |

### 한국어 / 영어 라벨

- `lang: ko` 면 i18n 객체의 `ko` 우선
- 둘 다 표시하려면 `{ ko: "...", en: "..." }` 형태로 작성
- 단순 문자열을 주면 그대로 사용 (i18n 우회)

## 4. 실행

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

## 5. 사용자 응답 후 흐름

사용자가 브라우저에서 답변/질문/리뷰를 보내면 helper 가 다음 메시지를 tmux send-keys 로 현재 페인에 입력합니다:

- 답변 제출: `플랜파일을 확인해: @<plan.json 절대경로>`
- 역질문: `사용자 질문: <text>`
- 리뷰 코멘트 제출: `리뷰 등록됨 [N건]: @<plan.json 절대경로>`

당신은 이 메시지를 받으면:

1. **답변 케이스**: `plan.json` 을 다시 Read → `questions[].answer` 가 채워진 항목 확인 → 다음 라운드가 필요하면 `round: N+1` 으로 새 질문 append → `node ${SKILL_DIR}/scripts/start.mjs "$plan_dir"` 재실행 (helper 가 살아있으면 재사용, 브라우저는 SSE 로 자동 reload)
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

## 6. 종료

작업이 끝나면:

```bash
node ${SKILL_DIR}/scripts/stop.mjs "$plan_dir"
```

또는 helper 는 30분 idle 시 자동 종료됩니다. `planflow:plan-html-stop` 스킬을 별도로 호출해도 됩니다.

## 7. 사용자에게 보고

스킬 실행 후 다음 정보를 알리세요:

- 생성한 plan.json 경로
- 브라우저 URL (`http://localhost:<port>`)
- 질문 개수와 라운드 구성
- "사용자가 답변하면 자동으로 알림이 옵니다" 안내

## 가이드라인

- **plan.json 만 다루세요**. HTML 출력을 직접 편집하거나, render.mjs / template.html / helper-server.mjs 를 만지지 말 것. 일관된 UI 가 무너집니다.
- 질문은 **결정 지향**으로 — 정보 요청보다 "이 중 무엇을 고를지" 형태가 좋습니다.
- 한 라운드의 질문 개수는 5~7개 권장. 너무 많으면 사용자가 지칩니다.
- `context` 에 트레이드오프를 명시하세요 — 사용자가 결정 근거를 잡습니다.
- mermaid 다이어그램은 **간결하게**. 복잡한 다이어그램은 시각적 노이즈입니다.
- 사용자가 한 번에 자연어로만 줬다면, 1~2 라운드로 끝낼 수 있게 핵심 결정만 추려 질문하세요.
