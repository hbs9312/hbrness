# 다음 세션 시작 프롬프트

> 새 Claude 세션에서 이 파일 내용을 그대로 붙여넣어 시작하면 됩니다.
> 이 파일은 git ignore 또는 의도적 untracked 으로 관리 (커밋해도 무방).

---

## 프롬프트 (이하 그대로 복사·붙여넣기)

hbrness 레포 작업 이어서 한다. 다음 부트스트랩 절차를 정확히 지켜.

### 1. 컨텍스트 로드 (선두 작업)

다음 4개 파일을 **순서대로** 읽어 현재 상태와 작업 규칙을 파악해:

1. `~/.claude/projects/-Users-seok-development-hbrness/HANDOFF.md` — 가장 최근 addendum (2026-04-26 Phase 0+1(1)+1(2) 완료) 부터 역순으로 읽어 어디까지 진행됐는지·다음 무엇 할지 파악
2. `~/.claude/projects/-Users-seok-development-hbrness/memory/feedback_hbrness_workflow.md` — main 직접 작업·매 commit 확인·push 별도 확인 규칙
3. `~/.claude/projects/-Users-seok-development-hbrness/memory/feedback_questions_analyze_only.md` — 질문조 메시지엔 분석만, 명령조에만 행동
4. `docs/plugin-gaps-and-plan.md` (저장소 안) — 5-Phase 로드맵 캐노니컬

읽은 후 한 줄 요약으로 "어디까지 했고 다음 무엇 시작" 만 보고하고 사용자 지시를 기다려.

### 2. 작업 워크플로우 — Phase 1 (3) 이후 모든 task 에 적용

이 레포에서는 **PR 없이 main 직접 작업** + 다음 7-step 루프:

```
[Step 1] 사용자가 task 지시 (예: "Phase 1 (3) Task A 진행")
[Step 2] 관련 파일 read + edit (작업 자체 — 커밋·push 안 함)
[Step 3] xreview:review-bridge agent 호출 (codex 에 리뷰 위임)
         input: 변경 파일 + 설계 doc (ground truth) + perspective
         output: findings (severity 별)
[Step 4] findings 분석:
         - critical / warning 모두 적용 검토
         - plan 변동(설계 doc 수정 필요) 발생 시 별도 표로 사용자에게 알림
         - info 는 선택 적용
[Step 5] 변경 적용 (edit)
[Step 6] 사용자에게 diff 요약 + 커밋 메시지 초안 제시 → 승인 대기
[Step 7] 승인 시 commit (자동 chronicle 훅 트리거됨), push 는 사용자 별도 지시 시
```

**xreview 호출 형식** (Phase 1 (1)·(2) 에서 검증된 형태):

```
Skill: xreview:review-bridge (Agent 도구로 호출)
prompt 구조:
  files: <변경 파일 절대 경로 + 설계 doc 절대 경로>
  context: <Task 번호·Phase·무엇을 변경 중인지·어떤 commit 의 후속인지>
  perspective:
    1. 설계 doc 대비 일관성 (ground truth)
    2. 다운스트림 skill 이 사용할 수 있는 형태인가
    3. 이전 Phase 산출물과 연계 정확한가 (예: ErrorMeta hook 같은)
    4. 다른 머지 시나리오에서 misclassify 가능성
    5. 다운스트림 LLM 이 헷갈릴 부분 (skill prompt 의 모호함)
  cli_tool: codex
  extra_instructions: 구체적 finding 우선, 5–10건 안쪽 권장, 스타일 nit 지양
```

### 3. 다음 작업 — Phase 1 (3) API 계약 동기화

로드맵 §3.3 (3) 의 ROI 1순위 항목. 4-step 패턴:

| Task | 내용 | 참조 모델 |
|---|---|---|
| **A** | `specflow:generate-ts` 에 §API 계약 (OpenAPI fragment) 섹션 의무화 + ts-rules 신규 그룹 (warning grace) | Phase 1 (2) Task A 패턴 (`e048032`) |
| **B** | `backflow:export-api-contract` skill 신설 — 라우트 → OpenAPI/tRPC schema 출력. 기존 `frontflow:impl-api-integration` 에서 이 부분 분리 | Phase 1 (2) Task B 패턴 (`39e16c4`) |
| **B'** | `frontflow:sync-api-client` skill 신설 — 스키마 → TS 클라이언트·타입·MSW 핸들러 codegen | B 와 같은 commit 또는 후속 |
| **C** | `frontflow:impl-api-integration` housekeeping — sync-api-client 결과를 import 하도록 SKILL prompt 수정 | Phase 1 (2) Task C 패턴 (`e1a6a22`) |
| **D** | `backflow:validate-code` 와 `frontflow:validate-code` 에 §9 API 계약 drift 룰 — 양방향·byte-level 비교 | Phase 1 (1) Task D 패턴 (`33da800`) + Phase 1 (2) §8 패턴 (`f67e375`) |

**먼저 할 것**: `docs/designs/phase-1-api-sync.md` 설계 문서 작성. Phase 1 (1)·(2) 설계 doc 과 동일 구조 (목표 / Non-goals / TS 포맷 / 스킬 카드 / 동기화 메커니즘 / 출력 예시 / 마이그레이션 / CONTRACTS 갱신 / Future / DoD / 다음 작업).

설계 문서도 동일하게 codex 리뷰 받음 — Task 0 격으로.

### 4. plan 변동 처리 규약

xreview 가 critical/warning 으로 큰 구조 변경을 요구하면:

1. 사용자에게 **변동 요약 표** 로 보고 (원래 → 변경, 근거)
2. 사용자 승인 후 적용
3. commit 메시지에 "Plan deviations" 섹션으로 기록
4. 해당 설계 doc 의 상단에 **Revision** 헤더 추가 (Phase 1 (2) `phase-1-observability.md` 참조)

Phase 1 (2) Task B 에서 3건 발생한 사례 그대로 패턴화.

### 5. 작은 housekeeping (가능하면 시작 전)

- [ ] `plugins/backflow/skills/validate-code/SKILL.common.md` 의 §7·§8 위치 정리. 현재 §8 이 §7 위에 있음 (편집 사고). Write 로 한 번에 재작성. 작은 commit (5분).
- [ ] xreview 사후 리뷰 (Phase 1 (2) Task C `e1a6a22`, Task D `f67e375`) — session limit 으로 skip 했음. 적용된 변경에 retro 리뷰. critical 발견 시 patch commit.

이 둘은 사용자가 "housekeeping 부터" 라고 명시할 때만. 명시 없으면 바로 Phase 1 (3) 진입.

### 6. 작업 시 주의 (이전 세션 학습)

- **Codex 가 자기 모델명을 `gpt-5.5` 로 보고함** — 픽션. 실제 codex CLI 는 GPT-5/5.1. 자체 self-reporting 무시, 검토 결과만 신뢰.
- **Committer identity** 가 `Seok <seok@Seokui-MacBookPro.local>` 기본값으로 작동 — 솔로 레포라 OK. 수정 안 함.
- **Stacked PR 규약 비활성** — 이 레포 한정. diff 300줄 초과해도 직접 main 커밋 가능.
- **chronicle 은 commit 직후 자동** — PostToolUse 훅이 reminder 발사. 커밋 후 바로 `~/.commit-chronicles/github.com__hbs9312__hbrness/` 에 기록.
- **커밋 메시지에 plan 변동 명시** — 다음 세션이 추적 가능하게.

### 7. 진행률·시간 추산 (참고)

- 필수 영역 (Phase 0+1+1.5): 약 38% 완료, **5–7주 분량 남음**
- Phase 1 (3): 1주 예상 (1·2 와 같은 패턴, ~10 commit)
- Phase 1 (4)~(6): 각 0.5–1주
- Phase 1.5 dbflow: 2–3주 (가장 복잡, velvetalk 1332줄 Python 포팅)
- Phase 2/3: optional

---

이상이 부트스트랩. 다 읽었으면 한 줄 요약 + "Phase 1 (3) 설계 문서부터 시작할까?" 물어보고 사용자 지시 기다려.
