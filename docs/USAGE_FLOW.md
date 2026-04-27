# hbrness 플러그인 사용 플로우 — 실무 가이드

> 이 문서는 hbrness 7개 플러그인 (meeting-prep / specflow / xreview / ghflow / frontflow / backflow / dbflow) 을 **실제 프로젝트에서 사용하는 순서**를 시나리오별로 정리합니다.
>
> 각 명령은 Claude Code 세션에서 `/plugin:skill` 형태로 실행합니다.

---

## 시나리오 1 — 신규 기능 개발 (전체 파이프라인)

기획 회의 → 명세 → 이슈 → 구현 → 검증 → PR 까지 전체 흐름.

### Phase 1: 기획 · 회의 준비

```
/meeting-prep:spec-scanner specs/          ← 기존 명세 현황 파악
/meeting-prep:impl-scanner src/            ← 기존 구현 현황 파악
/meeting-prep:meeting-doc-gen              ← 기획·구현 갭 리포트 + 회의 자료
```

회의에서 이번 스프린트 범위 확정.

### Phase 2: 명세 작성 (specflow — 톱다운 체인)

순서가 중요. 앞 단계 산출물이 뒷 단계의 입력.

```
/specflow:generate-fs PRD.md               ← 기능 명세 (FS) — 사용자 스토리, BR, AC
                                             산출: specs/FS-2026-001.md

/specflow:generate-wf specs/FS-2026-001.md ← 와이어프레임 (WF) — 화면 전환, 레이아웃
                                             산출: specs/WF-2026-001.md
  또는
/specflow:extract-wf-from-figma <figma-url> ← Figma 디자인이 있으면 여기서 추출

/specflow:state-matrix specs/WF-2026-001.md ← 화면별 상태 매트릭스 (정상/로딩/에러/빈)

/specflow:extract-ui specs/WF-2026-001.md   ← 화면설계서 (UI) — 컴포넌트 명세, 토큰
                                              산출: specs/UI-2026-001.md

/specflow:generate-ts specs/FS-2026-001.md specs/WF-2026-001.md
                                            ← 기술 명세 (TS) — API, 데이터 모델, ADR
                                              포함: §3.2 OpenAPI fragment
                                                    §4 에러 코드 맵
                                                    §7.1 관측성
                                                    §9 파일 처리 (해당 시)
                                                    §10 webhook (해당 시)
                                              산출: specs/TS-2026-001.md

/specflow:generate-erd specs/TS-2026-001.md ← (선택) ER 다이어그램

/specflow:generate-qa specs/FS-2026-001.md specs/TS-2026-001.md
                                            ← 테스트 명세 (QA)
                                              포함: §5 E2E DB 시나리오 (Phase 1.5)
                                              산출: specs/QA-2026-001.md

/specflow:extract-refs specs/              ← 참조 인덱스 (ID 교차 검증)

/specflow:decompose specs/TS-2026-001.md   ← 구현 태스크 분해 (PR 단위)
                                             산출: specs/PLAN-2026-001-tasks.md
```

### Phase 3: 명세 검증 (xreview — 게이트)

명세를 굳히고 넘어가야 구현 비용 폭발 방지.

```
/xreview:review specs/TS-2026-001.md       ← codex 등 외부 LLM 교차 리뷰
/backend-spec-review specs/TS-2026-001.md  ← 백엔드 관점 단독 리뷰
/backend-team-review specs/TS-2026-001.md  ← 3인 전문가 팀 리뷰 (선택)
```

문제 발견 시:
```
/specflow:revise specs/TS-2026-001.md      ← 피드백 반영해 명세 수정
/specflow:change-impact specs/TS-2026-001.md ← 변경이 다른 문서에 미치는 영향 분석
/spec-refine-loop specs/TS-2026-001.md     ← 리뷰-수정 반복 루프
```

### Phase 4: 이슈 · 브랜치 셋업 (ghflow)

```
/ghflow:create-issue                       ← GitHub 이슈 생성 (템플릿 기반)
/ghflow:pick-issue                         ← 작업할 이슈 선택 + 메모리 저장
/ghflow:draft-pr                           ← 브랜치 + 빈 커밋 + Draft PR + 이슈 링크
```

### Phase 5: 백엔드 구현 (backflow — 바텀업)

기존 프로젝트는 `scan-codebase` 먼저. 순서대로 진행.

```
/backflow:scan-codebase                    ← 기존 서비스·리포지토리·미들웨어 레지스트리 생성
/backflow:map-tasks specs/PLAN-2026-001-tasks.md
                                           ← 태스크 → 파일·레이어 매핑

/backflow:impl-schema specs/TS-2026-001.md ← DB 스키마 + 마이그레이션
/backflow:impl-repositories specs/TS-2026-001.md
                                           ← 리포지토리 패턴
/backflow:impl-error-codes specs/TS-2026-001.md
                                           ← 에러 상수 + HTTP 매핑 + i18n (Phase 1 (1))
/backflow:impl-observability specs/TS-2026-001.md
                                           ← structured logger + tracing + OTel (Phase 1 (2))
/backflow:impl-services specs/TS-2026-001.md
                                           ← 비즈니스 로직 (BR 1:1 매핑)
/backflow:impl-controllers specs/TS-2026-001.md
                                           ← API 엔드포인트 (thin controller)
/backflow:impl-middleware specs/TS-2026-001.md
                                           ← 인증·인가·에러 필터·CORS
/backflow:impl-integrations specs/TS-2026-001.md
                                           ← 외부 서비스 (MQ, 캐시, 스토리지)

# Phase 1 (5) — 파일 업로드가 필요한 경우:
/backflow:impl-file-upload specs/TS-2026-001.md
                                           ← presigned URL + storage adapter + resize

# Phase 1 (6) — Webhook 수신이 필요한 경우:
/backflow:impl-webhook specs/TS-2026-001.md
                                           ← 서명 검증 + idempotency + enqueue

# Phase 1 (3) — OpenAPI 문서 export:
/backflow:export-api-contract specs/TS-2026-001.md
                                           ← openapi/openapi.yaml 생성 (§3.2 + §4 합성)

/backflow:generate-tests specs/TS-2026-001.md
                                           ← 단위·통합 테스트 자동 생성
```

### Phase 6: 프론트엔드 구현 (frontflow — 바텀업)

백엔드와 병렬 가능. Figma 있으면 `extract-figma` 선행.

```
/frontflow:scan-codebase                   ← 기존 컴포넌트·훅·유틸 레지스트리
/frontflow:map-tasks specs/PLAN-2026-001-tasks.md
                                           ← 태스크 → 파일·레이어 매핑

/figma-extract <figma-url>                 ← (선택) Figma 디자인 데이터 추출

/frontflow:impl-tokens specs/UI-2026-001.md
                                           ← 디자인 토큰 (tailwind/CSS variables)
/frontflow:impl-atoms specs/UI-2026-001.md ← 원자 컴포넌트 + Storybook
/frontflow:impl-composites specs/UI-2026-001.md
                                           ← 복합 컴포넌트
/frontflow:impl-pages specs/WF-2026-001.md ← 페이지 (정적 레이아웃 + mock data)
/frontflow:impl-error-handling specs/TS-2026-001.md
                                           ← 에러 핸들러 + UI flow (Phase 1 (1))

# Phase 1 (3) — API 클라이언트 codegen:
/frontflow:sync-api-client                 ← openapi.yaml → 타입 + 함수 + MSW

# Phase 1 (4) — 이벤트 트래킹:
/frontflow:impl-tracking specs/FS-2026-001.md
                                           ← Phase A: 이벤트 상수 + 어댑터 생성
/frontflow:impl-tracking specs/FS-2026-001.md --phase=codemod
                                           ← Phase B: 컴포넌트 hook 삽입 proposal

/frontflow:impl-interactions specs/FS-2026-001.md
                                           ← 상태 관리 + 조건부 렌더 + 애니메이션
/frontflow:impl-api-integration specs/TS-2026-001.md
                                           ← F5 stub → 실제 API 호출 교체 (codegen import)

/frontflow:generate-stories                ← Storybook 스토리 보강
```

### Phase 7: 코드 검증 (validate)

```
# 백엔드
/backflow:validate-code src/               ← 컨벤션·계층·에러·타입·보안 + drift 룰
                                             §7 에러 코드 drift
                                             §8 관측성 drift
                                             §9 API 계약 drift
                                             §10 파일 업로드 drift
                                             §11 webhook drift
/backflow:validate-api specs/TS-2026-001.md ← API 가 TS 계약과 일치하는지 클린룸 검증
/backflow:validate-tests                    ← 테스트 커버리지 검증

# 프론트엔드
/frontflow:validate-code src/              ← 컨벤션·재사용·토큰·타입·접근성
                                             §7 에러 코드 drift
                                             §9 API 계약 drift
                                             §10 이벤트 트래킹 drift
/frontflow:validate-visual                 ← Storybook 기반 시각 QA 체크리스트
/frontflow:validate-a11y                   ← WCAG 접근성 검증
```

### Phase 8: E2E DB 검증 (dbflow)

백엔드 구현 완료 후. 실제 DB + 실제 API 서버 위에서 검증.

```
# 최초 1회 — 환경 셋업
/dbflow:init                               ← .e2e/ 디렉토리 스캐폴드
# .e2e/config.yml 직접 편집 (source DB, sandbox, migration, auth 설정)

/dbflow:snapshot                           ← 소스 DB → 샌드박스 복제
/dbflow:migrate                            ← 샌드박스에 마이그레이션 적용
/dbflow:up                                 ← 샌드박스 DB 연결 API 서버 기동

# 시나리오 생성 + 실행
/dbflow:gen-scenarios specs/QA-2026-001.md ← QA §5 → .e2e/scenarios/*.yml 자동 생성
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

### Phase 9: 커밋 · PR · 리뷰 (ghflow)

```
# 매 커밋마다
git commit -m "feat: 화자 등록 API"
# (chronicle 은 수동 호출 또는 직접 /chronicle)
/ghflow:chronicle                          ← 커밋의 의도·결정·트레이드오프 기록

# PR 생성
/ghflow:create-pr                          ← GitHub PR (템플릿 기반)

# 코드 리뷰
/xreview:review src/                       ← codex 에게 외부 리뷰 위임
/ghflow:review-pr                          ← PR 에 달린 리뷰 댓글 확인 + 처리

# 마무리
/ghflow:clear-issue                        ← 이슈 메모리 정리
/ghflow:chronicle-lookup "왜 이렇게 짰지?" ← 과거 커밋의 의도 조회
```

---

## 시나리오 2 — 기존 코드에 기능 추가

기존 프로젝트에 새 기능 추가. `scan-codebase` 먼저 돌려서 중복 방지.

```
# 1. 기존 코드 파악
/backflow:scan-codebase
/frontflow:scan-codebase

# 2. 명세 (기존 명세가 있으면 incremental)
/specflow:generate-ts --base specs/TS-2026-001.md specs/FS-2026-002.md specs/WF-2026-002.md

# 3. 이후 시나리오 1 의 Phase 4~9 동일
```

---

## 시나리오 3 — 명세만 개선 (구현 X)

```
/specflow:revise specs/TS-2026-001.md      ← 피드백 반영 수정
/xreview:review specs/TS-2026-001.md       ← 외부 리뷰
/specflow:change-impact specs/TS-2026-001.md ← 영향 분석
/spec-refine-loop specs/TS-2026-001.md --iterations 3
                                           ← 리뷰-수정 3회 반복
```

---

## 시나리오 4 — 디자인 (Figma) 부터 시작

```
/figma-extract <figma-url>
/specflow:extract-wf-from-figma <figma-url> ← Figma → 와이어프레임
/specflow:extract-ui specs/WF-2026-001.md   ← → 화면설계서
# 이후 시나리오 1 의 Phase 2 (generate-ts) 부터 이어감
```

---

## 시나리오 5 — 급한 버그 수정 (명세 생략)

```
/ghflow:pick-issue                         ← 이슈 선택
/ghflow:draft-pr                           ← 브랜치 + Draft PR

# 바로 코드 수정 (specflow 생략)

/backflow:validate-code src/               ← 최소 검증
/ghflow:create-pr
/ghflow:chronicle                          ← 왜 이렇게 고쳤는지 기록
```

---

## 시나리오 6 — DB 스키마 변경 후 E2E 재검증

```
/backflow:impl-schema specs/TS-2026-001.md ← 새 마이그레이션 생성
/dbflow:migrate --fresh                    ← 샌드박스 재생성 + 마이그레이션
/dbflow:up                                 ← API 서버 재기동
/dbflow:run <scenario>                     ← 기존 시나리오 통과 여부 확인
```

---

## 시나리오 7 — 과거 코드 이해 (회고)

```
/ghflow:chronicle-lookup --file src/services/payment.service.ts
                                           ← 이 파일 관련 커밋의 의도·결정 조회
/ghflow:chronicle-lookup --since 2026-04-01
                                           ← 최근 커밋들의 chronicle 목록
/ghflow:chronicle-lookup "결제 로직 왜 바꿨지"
                                           ← 키워드 검색
```

---

## 모델 배분 (토큰 최적화)

skill 에 `model: sonnet` 이 지정된 기계적 작업은 자동으로 Sonnet 사용. 판단이 필요한 작업은 세션 기본 모델 (Opus) 유지.

| 모델 | 대상 skill | 비율 |
|---|---|---|
| **Sonnet** (자동) | impl-*, scan-*, map-*, patch-*, generate-tests/stories, export-api-contract, sync-api-client, dbflow (init~diff), ghflow 전체, meeting-prep 전체 | 58/83 (70%) |
| **Opus** (세션 기본) | generate-fs/ts/qa/wf, extract-ui, decompose, validate-*, reimpl-*, xreview, dbflow:run/gen-scenarios/validate-scenarios | 25/83 (30%) |

---

## 플러그인 상호 의존 맵

```
meeting-prep ──────► specflow ──────► ghflow (이슈·PR)
                        │                    │
                        │                    ▼
                        │              frontflow / backflow (구현)
                        │                    │
                        │                    ├── impl-error-codes ◄── TS §4
                        │                    ├── impl-observability ◄── TS §7.1
                        │                    ├── export-api-contract ◄── TS §3.2 + §4
                        │                    │       │
                        │                    │       ▼
                        │                    ├── sync-api-client ◄── openapi.yaml
                        │                    ├── impl-tracking ◄── FS §7
                        │                    ├── impl-file-upload ◄── TS §9
                        │                    ├── impl-webhook ◄── TS §10
                        │                    │
                        │                    ▼
                        │              validate-* (검증)
                        │                    │
                        ▼                    ▼
                   xreview ◄──────── (명세 리뷰 + 코드 리뷰)
                                            │
                                            ▼
                                        dbflow (E2E DB 검증)
                                            │
                                            ├── gen-scenarios ◄── QA §5
                                            ├── run ◄── .e2e/scenarios/*.yml
                                            └── validate-scenarios (invariant 검사)
```

---

## 원칙

1. **명세가 굳기 전까지 구현 금지** — xreview 게이트 통과 전 front/back 착수 X
2. **scan-codebase 를 플러그인 도입 시점 1회** — 기존 코드 중복 구현 방지
3. **TS 가 source of truth** — 모든 impl skill 은 TS (+ FS/WF/UI/QA) 를 읽고 코드 생성
4. **OpenAPI 가 front↔back 계약** — export-api-contract → sync-api-client 파이프
5. **Safety invariant 는 hardcode** — dbflow 의 sandbox naming / pg_dump only / confirm
6. **벤더 중립** — tracking adapter / storage adapter / signature adapter 모두 어댑터 패턴
7. **기계적 작업은 Sonnet** — model: sonnet frontmatter 로 자동 비용 최적화
