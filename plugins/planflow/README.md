# planflow

구현 계획을 사용자 친화적인 HTML 문서로 렌더링하는 스킬 묶음. LLM 은 plan.json 만 작성하고 HTML 은 고정 템플릿이 책임지므로, 매 호출마다 동일한 레이아웃·일관 품질을 보장한다.

## Skills

| Skill | 역할 |
|---|---|
| `plan-html` | plan.json 을 받아 HTML 렌더 + helper 서버 기동 + 브라우저 오픈 |
| `plan-html-stop` | 활성 helper 서버 종료 |

## Decision Round 패턴

사용자 결정이 필요한 질문을 카드형 입력 컴포넌트(text/textarea/number/slider/radio/checkbox/select/toggle/date/tag-input)로 표시. 사용자가 답변하면:

1. `~/.hbrness/<project>/plans/<slug>/answers.json` 에 누적 저장
2. `plan.json` 의 해당 question 에 answer/answered_at 채움
3. tmux send-keys 로 현재 pane 에 `플랜파일을 확인해: <path>` 알림
4. Claude 가 파일을 읽고 분석 → 다음 라운드 질문 추가 → render → SSE reload

사용자 역질문(`Ask Claude` 패널)은 `사용자 질문: <text>` 프리픽스로 send-keys 전송 + `questions.log` 에 누적.

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
