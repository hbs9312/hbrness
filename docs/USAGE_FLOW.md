# hbrness 플러그인 사용 플로우 — 실무 가이드

> 이 문서는 hbrness 5개 플러그인 (ghflow / xreview / dbflow / sessionflow / agentbus) 을 **실제 프로젝트에서 사용하는 순서**를 시나리오별로 정리합니다.
>
> 각 명령은 Claude Code 세션에서 `/plugin:skill` 형태로 실행합니다.

> **범위 안내** — 명세 생성(specflow), 코드 생성(frontflow / backflow), 기획 분석(meeting-prep) 플러그인은 제거되었습니다. hbrness 는 이제 **이슈/PR 워크플로우 · 교차 코드리뷰 · E2E DB 검증 · 세션 관리**를 담당하고, 기획·명세·구현 자체는 hbrness 밖(직접 작성 또는 다른 도구)에서 진행합니다.

---

## 시나리오 1 — 신규 기능 개발 (전체 파이프라인)

이슈 → 구현 → E2E 검증 → 리뷰 → PR 까지 전체 흐름.

### Phase 1: 이슈 · 브랜치 셋업 (ghflow)

```
/ghflow:list-work                          ← 지금 잡을 수 있는 일감 조회
/ghflow:create-issue                       ← GitHub 이슈 생성 (템플릿 기반)
/ghflow:pick-issue                         ← 작업할 이슈 선택 + 메모리 저장
/ghflow:draft-pr                           ← 브랜치 + 빈 커밋 + Draft PR + 이슈 링크
```

### Phase 2: 구현

hbrness 범위 밖. 직접 구현하거나 원하는 도구를 씁니다.

긴 작업이면 세션 관리 스킬로 감싸는 것을 권장 — 아래 [부가 — 세션 관리](#부가--세션-관리-sessionflow-모든-단계-공통) 참고.

```
/phase-loop <자연어 구현 계획>             ← 구현 → 리뷰 → 커밋 → push → PR → 핸드오프를
                                             페이즈마다 반복 (Phase 2~4 를 통째로 자동화)
```

### Phase 3: E2E DB 검증 (dbflow)

백엔드 구현 완료 후. 실제 DB + 실제 API 서버 위에서 검증.

```
# 최초 1회 — 환경 셋업
/dbflow:init                               ← .e2e/ 디렉토리 스캐폴드
# .e2e/config.yml 직접 편집 (source DB, sandbox, migration, auth 설정)

/dbflow:snapshot                           ← 소스 DB → 샌드박스 복제
/dbflow:migrate                            ← 샌드박스에 마이그레이션 적용
/dbflow:up                                 ← 샌드박스 DB 연결 API 서버 기동

# 시나리오 생성 + 실행
/dbflow:gen-scenarios specs/QA-2026-001.md ← QA 명세의 E2E DB 시나리오 표 → .e2e/scenarios/*.yml
# .e2e/fixtures/ 에 필요한 SQL fixture 작성 (cross-feature / edge state)

/dbflow:run signup_persists_user           ← 시나리오 실행 + DB delta 검증
/dbflow:run order_creates_payment
/dbflow:run webhook_idempotent

# 디버깅 — 수동 watch/diff
/dbflow:watch users,orders                 ← 지정 테이블 before 스냅샷
# (API 호출 또는 수동 동작)
/dbflow:diff                               ← insert/update/delete 표시

# 상태 확인 · 정리
/dbflow:status                             ← 현재 샌드박스 상태 조회
/dbflow:validate-scenarios                 ← 시나리오 YAML 무결성 + safety invariant 검사
/dbflow:down                               ← API 서버 종료
/dbflow:reset                              ← 샌드박스 DB 삭제 + 초기화
```

`gen-scenarios` 는 QA 명세 파일을 입력으로 받습니다. 해당 파일은 직접 작성하거나 다른 도구로 생성해서 `specs/` 에 두면 됩니다.

### Phase 4: 리뷰 · 커밋 · PR (xreview + ghflow)

```
# 코드 리뷰 — 반대편 모델에 교차검증
/xreview:live                              ← codex(반대편 에이전트)로 백그라운드 코드리뷰.
                                             런처가 이번 세션의 작업 의도를 --context 로 자동 주입
/xreview:status                            ← 돌고 있는 리뷰 세션 목록
/xreview:stop                              ← 리뷰 세션 종료 (리뷰 내역은 보존)

# 커밋
/ghflow:commit                             ← 팀 커밋 컨벤션에 맞는 메시지 생성 + 커밋
/ghflow:commit -y                          ← (자동 커밋 — 확인 없이 바로 실행)
/ghflow:chronicle                          ← 커밋의 의도·결정·트레이드오프 기록

# PR
/ghflow:create-pr                          ← GitHub PR (템플릿 기반)
/ghflow:review-pr                          ← PR 리뷰 댓글 확인 + 처리 (디폴트: unresolved 만, 토큰 절약)
/ghflow:review-pr 101 --all                ← resolved 까지 포함해서 다시 보기

# 마무리
/ghflow:clear-issue                        ← 이슈 메모리 정리
/ghflow:chronicle-lookup "왜 이렇게 짰지?" ← 과거 커밋의 의도 조회
```

---

## 시나리오 2 — 급한 버그 수정

```
/ghflow:pick-issue                         ← 이슈 선택
/ghflow:draft-pr                           ← 브랜치 + Draft PR

# 바로 코드 수정

/xreview:live                              ← 최소 교차 리뷰
/ghflow:create-pr
/ghflow:chronicle                          ← 왜 이렇게 고쳤는지 기록
```

---

## 시나리오 3 — DB 스키마 변경 후 E2E 재검증

```
# 마이그레이션 파일 직접 작성

/dbflow:migrate --fresh                    ← 샌드박스 재생성 + 마이그레이션
/dbflow:up                                 ← API 서버 재기동
/dbflow:run <scenario>                     ← 기존 시나리오 통과 여부 확인
```

---

## 시나리오 4 — 과거 코드 이해 (회고)

```
/ghflow:chronicle-lookup --file src/services/payment.service.ts
                                           ← 이 파일 관련 커밋의 의도·결정 조회
/ghflow:chronicle-lookup --since 2026-04-01
                                           ← 최근 커밋들의 chronicle 목록
/ghflow:chronicle-lookup "결제 로직 왜 바꿨지"
                                           ← 키워드 검색
```

---

## 시나리오 5 — 긴 작업을 무인으로 굴리기

컨텍스트가 누적되면 품질이 떨어지므로, 페이즈마다 세션을 갈아끼우며 진행합니다.

```
/phase-run <자연어 페이즈 계획>            ← 페이즈 경계마다 컨텍스트 리셋. 커밋은 안 함
/phase-loop <자연어 구현 계획>             ← 위에 리뷰·커밋·push·PR 까지 얹어 PR 단위로 반복

/phase-loop status|pause|resume|stop|reset
```

`phase-loop` 는 개인 레포면 브랜치에 직접, 팀 레포면 워크트리 + 스택 PR 로 진행합니다. tmux 가 필요합니다.

---

## 부가 — 세션 관리 (sessionflow, 모든 단계 공통)

파이프라인 단계가 아니라 어느 시점에서든 쓰는 cross-cutting 스킬. Claude ↔ Codex 가 같은 파일을 공유한다.

```
# 지금 작업을 다음 세션이 그대로 이어받게
/handoff [-m|-o] [메시지]                  ← in-flight 컨텍스트(편집중 파일·마지막 명령·에러·다음 한 줄)를 HANDOFF.md 로 직렬화 (워크트리 단위)
/handoff-clear [-y] [--all]                ← HANDOFF.md + MEMORY.md 라인 정리

# 나중에 처리할 일 (백로그)
/followup [-m|-o] [메시지]                 ← 후속 조치 항목을 followups/ 에 누적 (프로젝트 단위·영속)
/followup-clear [-y]                       ← followups/ 전체 비우기

# 긴 작업을 페이즈로 쪼개 컨텍스트를 비우며 무인 진행
/phase-run <자연어 계획>                   ← 페이즈 분해 → 경계마다 자기 pane 에 /clear + /phase-run continue 자동 주입 → 새 세션이 HANDOFF.md 읽고 다음 페이즈 진행. 자동 커밋 안 함. tmux 필요.
/phase-run continue|status|pause|resume|stop|reset
/phase-loop <자연어 계획>                  ← phase-run + 페이즈마다 xreview 리뷰·커밋·push·PR
/phase-loop continue|status|pause|resume|stop|reset
```

- **handoff** = 지금 이 작업을 다음 세션이 그대로 (1회성·워크트리 단위).
- **followup** = 나중에 할 일 (영속·프로젝트 단위).
- **phase-run** = 긴 다단계 작업을 페이즈마다 컨텍스트를 리셋하며 무인 진행.
- **phase-loop** = phase-run 에 출하(리뷰→커밋→push→PR)를 끼운 상위 루프 — 위 Phase 2~4 를 통째로 감쌀 수 있다.

저장(Tier 1): `~/.hbrness/sessionflow/<project-key>/` → HANDOFF.md, followups/, phases/. 양쪽 MEMORY.md 자동 동기화.

---

## 부가 — 세션 간 에이전트 통신 (agentbus)

서로 다른 tmux 세션에서 돌고 있는 에이전트끼리 별칭으로 메시지를 주고받는다. 프론트/백엔드 세션을 나눠 띄우고 서로 상태를 알릴 때 쓴다.

```
/agent-register frontend                   ← 현재 tmux pane 을 'frontend' 별칭으로 등록
/agent-list                                ← 등록된 에이전트 목록 (죽은 pane 자동 정리)
/agent-send backend "스키마 반영했어"       ← 다른 세션 프롬프트에 직접 주입
/agent-send backend --file plan.md         ← 긴 내용은 inbox 파일로 저장 + 알림만 주입
/agent-inbox                               ← 내 mailbox 조회·열람·읽음 처리
/agent-unregister                          ← 세션 종료 전 별칭 해제
```

fire-and-forget 이다. 회신이 필요하면 받은 쪽이 같은 명령으로 되쏜다.

---

## 모델 배분 (토큰 최적화)

skill 에 `model: sonnet` 이 지정된 기계적 작업은 자동으로 Sonnet 사용. 판단이 필요한 작업은 세션 기본 모델 (Opus) 유지.

| 모델 | 대상 skill | 비율 |
|---|---|---|
| **Sonnet** (자동) | ghflow 전체(commit 포함), agentbus 전체, xreview 전체, dbflow (init~diff), sessionflow (handoff/followup 계열) | 31/36 (86%) |
| **Opus** (세션 기본) | `dbflow:gen-scenarios` / `dbflow:run` / `dbflow:validate-scenarios`, `sessionflow:phase-run` / `phase-loop` | 5/36 (14%) |

---

## 플러그인 상호 의존 맵

```
ghflow (이슈·브랜치·Draft PR)
     │
     ▼
구현 (hbrness 범위 밖)
     │
     ├──────────────► dbflow (E2E DB 검증)
     │                   │
     │                   ├── gen-scenarios ◄── QA 명세 (specs/)
     │                   ├── run ◄── .e2e/scenarios/*.yml
     │                   └── validate-scenarios (invariant 검사)
     ▼
xreview (교차 코드리뷰)
     │
     ▼
ghflow (commit · chronicle · create-pr · review-pr)

sessionflow ── 모든 단계에 걸침 (handoff / followup / phase-run / phase-loop)
agentbus ───── 세션 간 통신 (파이프라인 무관)
```

---

## 원칙

1. **명세는 hbrness 밖에서** — `specs/` 는 사람이 소유하는 산출물. dbflow 가 이를 **읽기만** 한다
2. **리뷰는 반대편 모델로** — 같은 모델이 자기 코드를 리뷰하면 놓치는 게 생긴다. `xreview` 로 claude↔codex 교차
3. **Safety invariant 는 hardcode** — dbflow 의 sandbox naming / pg_dump only / confirm
4. **커밋 의도는 코드 밖에 남긴다** — `chronicle` 이 diff 가 답 못 하는 "왜"를 보존
5. **긴 작업은 페이즈로 끊는다** — 컨텍스트 누적으로 인한 품질 저하를 `phase-run` / `phase-loop` 로 방지
6. **기계적 작업은 Sonnet** — `model: sonnet` frontmatter 로 자동 비용 최적화
