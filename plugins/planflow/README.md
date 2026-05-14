# planflow

구현 계획을 사용자 친화적인 HTML 문서로 렌더링하는 스킬 묶음. LLM 은 코드베이스를 먼저 조사한 뒤 plan.json 만 작성하고, HTML 은 고정 템플릿이 책임지므로 매 호출마다 동일한 레이아웃·일관 품질을 보장한다.

## Skills

| Skill | 역할 |
|---|---|
| `plan-html` | 코드 조사 기반 plan.json 작성/검증 + HTML 렌더 + helper 서버 기동 + 브라우저 오픈 |
| `plan-html-stop` | 활성 helper 서버 종료 |

## Code-aware Review 패턴

`plan-html` 은 자연어 구현 요청을 바로 질문지로 만들지 않고, 먼저 관련 파일과 현재 구조를 확인한다. plan.json 의 `overview.summary`, `overview.current_state`, `overview.proposed_approach` 는 그 조사 결과를 사람이 읽기 좋은 문단으로 담고, `overview.review_focus` 는 사용자가 특히 확인해야 할 부분만 짧게 남긴다.

결정사항 질문은 코드로 판단할 수 없는 제품/운영/리스크 선택에만 사용한다. 각 질문은 필요하면 `evidence`, `recommendation`, `tradeoffs` 를 함께 담아 사용자가 "무엇을 모르는지"가 아니라 "무엇을 확인했고 어떤 결정을 부탁하는지"를 볼 수 있게 한다.

## Decision Round 패턴

사용자 결정이 필요한 질문을 카드형 입력 컴포넌트(text/textarea/number/slider/radio/checkbox/select/toggle/date/tag-input)로 표시. 사용자가 답변하면:

1. `~/.hbrness/<project>/plans/<slug>/answers.json` 에 누적 저장
2. `plan.json` 의 해당 question 에 answer/answered_at 채움
3. tmux send-keys 로 현재 pane 에 `플랜파일을 확인해: <path>` 알림
4. Claude 가 파일을 읽고 답변을 계획 본문에 반영
5. 필요한 경우 다음 라운드 질문 추가 → render → SSE reload

HTML 은 질문 단계와 계획 검토 단계를 분리한다. 답변되지 않은 `questions[]` 가 있으면 화면에는 질문 라운드만 표시하고, 모든 질문이 끝난 뒤에 개요·단계·파일·다이어그램을 계획서로 보여준다. 계획 화면에서는 우측 `답변` 버튼으로 라운드 답변 사이드바를 열어 확인한다.

사용자 역질문은 하단 고정 프롬프트에서 입력받고, `사용자 질문: <text>` 프리픽스로 send-keys 전송 + `questions.log` 에 누적한다.

인라인 리뷰 코멘트는 `comments[]` 에 저장된다. Claude 는 코멘트가 가리키는 anchor 를 확인해 plan 본문을 수정하고, `replies[]` 에 반영/보류 사유를 남긴다. 열린 질문과 미처리 코멘트가 없어지면 계획 상태를 `approved` 로 바꿀 수 있다.

## 산출물 (Tier 1)

```
~/.hbrness/<project_slug>/plans/<plan_slug>/
├── plan.json        ← source of truth
├── index.html       ← 렌더 결과
├── answers.json     ← 누적 답변
├── questions.log    ← 사용자 역질문 로그
├── server.json      ← helper port + pid
└── assets/          ← 다이어그램 이미지 첨부
```
