# 다음 세션 시작 프롬프트

> 새 Claude 세션에서 이 파일 내용을 그대로 붙여넣어 시작하면 됩니다.

---

## 프롬프트 (이하 그대로 복사·붙여넣기)

hbrness 레포 작업 이어서 한다. 다음 부트스트랩 절차를 정확히 지켜.

### 1. 컨텍스트 로드 (선두 작업)

다음 5개 파일을 **순서대로** 읽어 현재 상태와 작업 규칙을 파악:

1. `~/.claude/projects/-Users-seok-development-hbrness/HANDOFF.md` — 가장 최근 addendum (2026-04-27 Phase 1 (1)~(6) 완료) 부터 역순으로 읽어 어디까지 진행됐고 다음 무엇 할지 파악
2. `~/.claude/projects/-Users-seok-development-hbrness/memory/feedback_hbrness_workflow.md` — main 직접 작업·매 commit 확인·push 별도 확인 규칙
3. `~/.claude/projects/-Users-seok-development-hbrness/memory/feedback_questions_analyze_only.md` — 질문조 메시지엔 분석만, 명령조에만 행동
4. `docs/plugin-gaps-and-plan.md` (저장소 안) — 5-Phase 로드맵 캐노니컬 (특히 §3.4 Phase 1.5 dbflow)
5. `docs/designs/phase-1-*.md` 6개 (Phase 1 (1)~(6) 설계 문서) — 동일 패턴 참조

읽은 후 한 줄 요약으로 "어디까지 했고 다음 무엇 시작" 만 보고하고 사용자 지시를 기다려.

### 2. 작업 워크플로우 — Phase 1.5 dbflow 적용 규칙

이번 phase 부터 다음 워크플로우 (Phase 1 (4)~(6) 에서 검증됨):

```
[1] 별도 브랜치 (`phase-1.5-dbflow` 또는 sub-phase 별)
[2] 각 sub-phase 마다:
    a. 설계 doc 작성 (Opus)
    b. xreview:review-bridge agent → codex 리뷰 (5축 perspective)
    c. critical/warning 반영해 doc revision (plan deviation 은 commit msg + Revision 헤더)
    d. design doc commit (사용자 확인 없이 자동 — 이번 Phase 부터 별도 브랜치 자동 commit 패턴)
    e. Task A/B/D 등 실제 구현 — Sonnet agent 위임 (model: sonnet)
    f. 각 task commit 자동
[3] sub-phase 마지막에 phase-end codex 리뷰 (선택 — sub-phase 가 작으면 skip 가능)
[4] post-review fixup commit (필요 시)
[5] 모든 sub-phase 완료 후 사용자가 main 에 머지
```

**xreview 호출 형식** (검증된 형태, 5축 perspective):
1. 선행 design doc 일관성 (특히 Phase 1 (3)~(6) 의 selected-adapter facade 패턴)
2. 다음 task 도출 가능성 — 빈틈 없이
3. 선행 Phase 산출물 연계 정확성 (ErrorMeta hook, observability bootstrap_file, file_upload metadata schema 등)
4. 영역별 보안·정합성 (예: dbflow 의 sandbox naming hardcode, host whitelist)
5. 다운스트림 LLM 모호성 (Sonnet 가 SKILL 만 보고 정확히 구현 가능한지)

### 3. 다음 작업 — Phase 1.5 dbflow (7 sub-phase)

`docs/plugin-gaps-and-plan.md` §3.4 의 9 skill 을 7 sub-phase 로 분할 진행. velvetalk 의 `../velvetalk/backend/.claude/skills/e2e-db/` 1332줄 Python CLI 가 포팅 원본.

| Sub-phase | 범위 | 산출 | 추정 |
|---|---|---|---|
| **1.5.0** 설계 doc + dbflow plugin 등록 + AUTHORING Tier 0 dbflow 반영 | 골격 | `docs/designs/phase-1.5-dbflow.md`, `plugins/dbflow/` 디렉토리 + `plugin.json`, `AUTHORING.md` 갱신 | 1 commit |
| **1.5.1** specflow:generate-qa §E2E DB 시나리오 섹션 + qa-rules | 입력 포맷 | qa-rules 갱신 + template 갱신 + SKILL prompt 갱신 | 2 commit |
| **1.5.2** dbflow:init / status / reset (가장 단순) + safety invariant 핵심 | 골격 명령 | 3 skill + safety_invariants.md (sandbox naming hardcode 등) | 2 commit |
| **1.5.3** dbflow:up / down (PID 관리) + dbflow:snapshot / migrate (DB 작업) | 환경 명령 | 4 skill | 3 commit |
| **1.5.4** dbflow:watch / diff (table delta) | 검증 명령 | 2 skill | 2 commit |
| **1.5.5** dbflow:run + dbflow:gen-scenarios (시나리오 실행 + QA 연계) | 핵심 통합 | 2 skill | 3 commit |
| **1.5.6** backflow 훅 (impl-schema 후 dbflow:migrate 제안) + ghflow 훅 (chronicle future_notes) + dbflow validate 룰 | 통합 + 검증 | 2 skill 또는 SKILL prompt 갱신 + validate-rules | 2 commit |

**총 ~15 commit, 2~3주 추정**

#### Phase 1.5 의 핵심 invariant (절대 변경 금지)

velvetalk e2e-db 에서 그대로 가져옴:
- 소스 DB 에 쓰기 금지 (pg_dump 만, host whitelist 검증)
- 샌드박스 DB 이름은 반드시 `sandbox` 또는 `e2e` 포함. 위반 시 drop 거부
- 파괴적 작업 (`snapshot`, `reset`, `--fresh`) 은 기존 샌드박스 존재 시 사용자 확인 후 진행

이 invariant 는 **hardcode** 로 SKILL 본문에 박힘 — config 변수로 빼지 않음. Phase 1.5 codex 리뷰가 이 부분을 가장 엄격하게 검사할 것.

#### Phase 1.5 스코프 제한 (의도적)

- **대상 스택**: Postgres + Docker + Alembic(Python) + uv (velvetalk 와 동일)
- 일반화 (Node/Prisma/MySQL, 비-Docker) 는 Phase 2 어댑터로 분리
- README 에 "현재 지원 스택" 명시

#### 시작 명령

사용자가 명시적으로 "Phase 1.5 시작해" 라고 하면:
1. `git checkout main` (필요 시 phase-1-final 머지 확인)
2. `git checkout -b phase-1.5-dbflow` 신규 브랜치
3. Sub-phase 1.5.0 부터 시작

### 4. plan 변동 처리 규약

xreview 가 critical/warning 으로 큰 구조 변경을 요구하면:

1. 사용자에게 **변동 요약 표** 로 보고 (원래 → 변경, 근거)
2. 자동 적용 (이번 phase 워크플로우는 자동 commit)
3. commit 메시지에 "Plan deviations" 섹션으로 기록
4. 해당 설계 doc 의 상단에 **Revision** 헤더 추가 (Phase 1 (1)~(6) 모든 설계 doc 참조)

### 5. 작업 시 주의 (이전 세션 학습 누적)

- **Codex 가 자기 모델명을 `gpt-5.5` 로 보고함** — 픽션. 실제 codex CLI 는 GPT-5/5.1. 자체 self-reporting 무시
- **Committer identity** 가 `Seok <seok@Seokui-MacBookPro.local>` 기본값. 솔로 레포라 OK
- **Stacked PR 규약 비활성** — 이 레포 한정
- **chronicle 은 commit 직후 자동** — PostToolUse 훅이 reminder 발사
- **커밋 메시지에 plan 변동 명시** — 다음 세션이 추적 가능하게
- **Phase 1.5 는 단일 marathon 으로 진행 위험** — sub-phase 별로 끊어서 commit. 한 sub-phase 가 끝나면 사용자 확인 받지 말고 다음으로 넘어가도 OK (이번 phase 워크플로우는 자율)
- **velvetalk 의 1332줄 Python 을 한 번에 read 하면 토큰 부담** — 필요한 부분만 잘라서 read

### 6. 진행률·시간 추산 (참고)

- 필수 영역 (Phase 0 + 1 + 1.5): **약 75% 완료**, **2~3주 분량 남음** (Phase 1.5 만)
- Phase 1.5 dbflow 완료 후 mandatory 100%
- Phase 2 / 3 는 프로젝트 드리븐 또는 조직 합의 후

### 7. 머지·관리 작업 (사용자가 결정)

- `phase-1-final` 브랜치 (Phase 1 (4)~(6) 17 commits) 의 main 머지 — 사용자가 검토 후
- `~/.claude/plugins/*.{cleanup,emergency,hbrness-bak}.*` 백업 정리 (HANDOFF 에 미해결 TODO 로 남아있음)

---

이상이 부트스트랩. 다 읽었으면 한 줄 요약 + "Phase 1.5 sub-phase 1.5.0 부터 시작할까?" 물어보고 사용자 지시 기다려.
