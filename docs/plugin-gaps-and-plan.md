# hbrness 플러그인 워크플로우 · 실무 보강 로드맵

> Generated: 2026-04-23
> Scope: `plugins/{meeting-prep, specflow, xreview, ghflow, frontflow, backflow}`
> Purpose: 현재 플러그인을 효율적으로 조합하는 방법 + 실무 관점에서 누락된 부분 + 이를 메우는 실행 플랜

---

## 1부. 현재 플러그인 효율적 사용 순서

### 1.1 전체 파이프라인

```
meeting-prep ─► specflow ─► ghflow(pick+draft) ─► frontflow / backflow ─► ghflow(chronicle+create-pr+review-pr+clear)
                  │                                    │
                  └─── xreview (명세 리뷰) ──────────────┴─── xreview (코드 리뷰)
```

**설계 축**: *기획 → 명세 → 이슈 → 구현 → 리뷰·머지*, 각 경계마다 `xreview` 로 외부 LLM 교차검증.

### 1.2 단계별 사용 순서

#### Step 1 — 킥오프 / 회의 준비 `meeting-prep`
- `/spec-scanner` + `/impl-scanner` 병렬 → `/meeting-doc-gen`
- **산출물**: 기획·구현 갭 리포트, 이번 스프린트의 명세 범위

#### Step 2 — 명세 작성 `specflow`
톱다운 체인 (순서 고정):
1. `/generate-fs` — 기능 명세 (FS)
2. `/generate-wf` 또는 `/extract-wf-from-figma` — 와이어프레임
3. `/state-matrix` — 화면별 상태 매트릭스
4. `/extract-ui` — 화면설계서 (UI)
5. `/generate-ts` — 기술 명세 (TS) · 필요 시 `/generate-erd`
6. `/generate-qa` — 테스트 명세
7. `/extract-refs` — 참조 인덱스
8. `/decompose` — 구현 태스크 분해 (Stacked PR 단위로 설계)

수정 흐름: `/change-impact` → `/spec-refine-loop`

#### Step 3 — 명세 검증 `xreview`
- `/xreview:review <spec-file>` — 다른 모델(codex 등) 관점 교차 리뷰
- `/backend-spec-review` — 백엔드 관점 단독 리뷰
- `/backend-team-review` — 3인 팀 리뷰
- `/spec-refine-loop` — 반복 개선 루프

**게이트 원칙**: 여기서 명세를 굳히고 넘어가야 이후 구현 비용이 폭발하지 않음.

#### Step 4 — 이슈·브랜치 셋업 `ghflow`
1. `/create-issue` (필요 시) → `/pick-issue` 로 작업 대상 고정
2. `/draft-pr` — 브랜치 + 빈 커밋 + Draft PR + 이슈 링크

Stacked PR 전제: 명세 분해 결과를 보고 Child PR 단위를 먼저 설계.

#### Step 5 — 구현 `frontflow` / `backflow`
레이어 독립, 병렬 가능. 둘 다 **바텀업**.

- **frontflow**: `scan-codebase → map-tasks → impl-tokens → impl-atoms → impl-composites → impl-pages → impl-interactions → impl-api-integration` + `generate-stories` + `validate-{code,visual,a11y}`
  - Figma 있으면 `/figma-extract` 또는 `extract-figma` 선행
- **backflow**: `scan-codebase → map-tasks → impl-schema → impl-repositories → impl-services → impl-controllers → impl-middleware → impl-integrations → generate-tests` + `validate-{code,api,tests}`

기존 프로젝트는 각 플러그인의 `scan-codebase` 를 **맨 먼저** 돌려서 중복 구현 방지.

#### Step 6 — 커밋·리뷰 `ghflow` + `xreview`
- 커밋마다 `ghflow:chronicle` 자동 트리거 (PostToolUse 훅)
- Child PR 단위 `/create-pr` → 필요 시 `/xreview:review` 로 외부 LLM 2차 리뷰
- 리뷰 반영: `/review-pr`
- 마무리: `/clear-issue` + 머지, 과거 근거 조회는 `/chronicle-lookup`

### 1.3 상황별 최적화

| 상황 | 순서 최적화 |
|---|---|
| 신규 기능, 이해관계자 회의부터 | meeting-prep → specflow → xreview → ghflow → front/back → ghflow |
| 기존 코드에 기능 추가 | front/back `scan-codebase` **먼저** → specflow → xreview → ghflow → 구현 |
| 명세만 개선 | specflow(revise) → xreview 반복 (`/spec-refine-loop`) |
| 디자인부터 받음 | `/figma-extract` → `specflow:extract-wf-from-figma` → `/extract-ui` → 이하 동일 |
| 급한 버그 수정 | ghflow(pick → draft) → 구현 → ghflow(chronicle → create-pr) — specflow 생략 허용 |

### 1.4 원칙 요약

- **명세가 굳기 전까지 구현 금지** — xreview 게이트 통과 전 front/back 착수 금지
- **scan-codebase 를 플러그인 도입 시점 1회** 돌려 레지스트리 확보
- **Stacked PR 기준(≤300줄·≤10파일)** 은 `decompose` 단계에서 이미 반영
- **chronicle 은 훅으로 자동** — 수동 호출은 오래된 커밋 회고 때만

---

## 2부. 실무 관점 누락·보강 분석

### 2.1 frontflow 보강 후보

| 영역 | 현재 | 실무에서 필요한 것 |
|---|---|---|
| **이벤트 트래킹/애널리틱스** | 없음 | GA4/Amplitude/Mixpanel 이벤트 매핑 skill. 기획서 "이 버튼 클릭 추적" 을 코드에 일관되게 심는 자동화 |
| **i18n / 다국어** | 없음 | 번역 키 추출·리소스 정리. 한국어 하드코딩 후 영문화는 지옥 |
| **SEO / 메타데이터** | 없음 | Next.js metadata, OpenGraph, sitemap, robots |
| **에러 모니터링 연동** | 없음 | Sentry SDK 세팅 + ErrorBoundary + source map 업로드 |
| **상태 관리 설계** | 없음 | 전역 store (Zustand/Redux) 스키마 설계. atoms/composites 전 단계에 와야 함 |
| **폼 전담 skill** | composites 안에 녹음 | react-hook-form + zod, 다단계·조건부 필드는 별도 skill 가치 |
| **Storybook 인터랙션 테스트** | generate-stories | play function·addon-interactions 자동 생성까지 |
| **E2E 시나리오** | validate-visual 중심 | Playwright 사용자 시나리오 자동 생성 (QA 명세 → spec.ts) |
| **성능/번들 검증** | 없음 | Lighthouse CI, bundle-size guard |
| **반응형·BP 검증** | screenshot-compare | 브레이크포인트별 스냅샷 매트릭스 |
| **PWA/오프라인** | 없음 | 선택이지만 필요한 프로젝트에선 매번 반복 |

### 2.2 backflow 보강 후보

| 영역 | 현재 | 실무에서 필요한 것 |
|---|---|---|
| **로깅·트레이싱** | middleware 일부 | structured log 포맷, correlation/request ID, OpenTelemetry 계측 전용 skill |
| **캐싱 전략** | integrations 일부 | Redis 키 네이밍·TTL·무효화 규약 설계 skill. 서비스에 애드혹으로 짜면 유지보수 폭탄 |
| **데이터 마이그레이션(1회성)** | impl-schema(구조만) | 스키마와 분리된 **데이터 변환** 스크립트 (backfill, denorm 채우기) |
| **배치·스케줄러·워커** | integrations 혼재 | cron job / worker queue 전용 skill. 소유자·재시도·dead-letter 설계 |
| **파일 업로드·스토리지** | 없음 | presigned URL, 이미지 리사이즈/썸네일, 확장자 화이트리스트 — 모든 서비스에 반복 |
| **에러 코드 표준화** | 없음 | 전역 에러 코드 맵 + i18n 메시지 + HTTP 상태 매핑. 프론트와 계약 공유 |
| **API 버전·Deprecation** | 없음 | v1/v2 병존, sunset 헤더, 마이그레이션 가이드 생성 |
| **레이트 리밋·쿼터** | middleware 일부 | 키별/유저별 정책, 사용량 노출 |
| **인가(AuthZ) 정책 설계** | middleware(가드 구현) | 역할·권한 매트릭스를 **명세 → 정책 코드** 로 떨구는 skill |
| **부하 테스트** | 없음 | k6·artillery 시나리오 (주요 endpoint) |
| **보안 검증** | validate-code 일부 | SQLi/XSS/CSRF/IDOR 자동 점검, Secret 누출 스캔 |
| **Webhook/멱등성** | integrations | 서명 검증, 리플레이 방지, idempotency-key 패턴 skill |

### 2.3 두 플러그인 사이의 **계약 레이어** (가장 크게 빠짐)

현재 `specflow → frontflow / backflow` 는 있지만 front ↔ back 사이의 **타입·계약 동기화** 파이프가 약함. 실무에서 가장 자주 깨지는 부분.

- **OpenAPI / tRPC / protobuf 기반 타입 생성** — 백 변경 시 프론트 클라이언트·타입이 자동 재생성. 현재 `impl-api-integration` 은 수동에 가까움
- **Mock 서버 구동** — 백엔드 미완성 상태에서도 프론트가 돌 수 있게. MSW/prism 자동 세팅
- **Contract test** — 프론트 기대 vs 백엔드 실제 응답. Pact 같은 CDC 자동화

### 2.4 공통(메타) 레벨 누락

1. **Feature flag / 롤아웃** — Child PR 전략 무용지물 되는 주범. LaunchDarkly/Unleash/간이 플래그
2. **환경 설정** — `.env` 스키마 (zod-env), secrets 관리, 환경별 config diff
3. **CI/CD·Dockerfile** — 명세가 있어도 배포 파이프라인은 여전히 수작업
4. **릴리스 노트·CHANGELOG 자동화** — chronicle 은 있지만 유저 향 릴리스 노트 합성은 별도
5. **가시성(Observability) 대시보드** — Grafana/Datadog 패널 정의 IaC

### 2.5 우선순위 요약 (주관)

**먼저 손대면 ROI 큼 (Phase 1)**
1. API 계약 동기화 (front↔back) — 유일하게 양쪽 플러그인이 같이 깨지는 축
2. 로깅·에러코드 표준 — 한 번 정해두면 전 서비스 일관성
3. 이벤트 트래킹 (프론트) — 기획이 명세에 쓰지만 구현 단계에서 휘발
4. 파일 업로드 / Webhook 멱등성 (백) — 거의 모든 서비스가 결국 필요

**팀/프로젝트 성격 따라 (Phase 2)**
- i18n, SEO, PWA, 부하 테스트, Feature flag, 캐싱 설계

**조직 표준 레벨 (Phase 3)**
- CI/CD, 환경 설정, 릴리스 노트 자동화 — 플러그인화 전에 조직 표준 합의 선행

---

## 3부. 실행 플랜

### 3.1 설계 원칙

- **새 skill 을 찍기보다 기존 skill 을 격상** 하는 것을 우선 고려
- 각 skill 은 **specflow 산출물(FS/TS/QA)과 명시적 계약** 을 가진다. 입력·출력 스키마를 문서화
- 모든 skill 은 `AUTHORING.md` 의 3-tier storage 규약 준수
- 최소 단위로 **ship 가능한 것부터** — 한 번에 모든 걸 설계하지 않는다

### 3.2 Phase 0 — 준비 (1주)

| 태스크 | 산출물 | 완료 기준 |
|---|---|---|
| 현재 skill 간 I/O 계약 문서화 | `plugins/{front,back}flow/CONTRACTS.md` | 각 skill 의 입력(어느 명세 섹션을 읽는지)·출력(파일·경로) 정리 |
| specflow 산출물 → 구현 skill 매핑표 | 같은 문서 | FS/TS/WF/UI/QA 각 섹션이 어느 impl/validate skill 의 입력인지 1:N 매핑 |
| 우선순위 투표 | `docs/plugin-gaps-vote.md` | 팀(or 본인) 사용 빈도·고통 지수로 top 5 확정 |

**Exit criteria**: Phase 1 에서 무엇을 먼저 만들지 확정됨.

### 3.3 Phase 1 — 고ROI 즉시 착수 (4–6주)

순서 권장 (앞 작업이 뒤 작업의 기반이 됨):

#### (1) `backflow:impl-error-codes` + `frontflow:impl-error-handling` — **공통 에러 계약**

- 입력: TS 의 "오류 처리" 섹션 + 도메인별 에러 케이스
- 출력:
  - 백: `src/errors/codes.ts` (enum + HTTP 매핑 + i18n 키)
  - 프론트: `src/errors/handler.ts` (code → 사용자 메시지 렌더)
- 완료 기준: 양쪽에서 같은 `ErrorCode` 문자열 상수 참조

#### (2) `backflow:impl-observability` — **로깅·트레이싱 표준**

- 입력: TS 의 "비기능 요구" 섹션
- 출력: structured logger 세팅, request/correlation ID 미들웨어, OpenTelemetry 초기화
- 완료 기준: `validate-api` 호출 시 로그·트레이스가 동시에 찍히는 E2E 확인

#### (3) `impl-api-integration` 격상 → **API 계약 동기화**

현재 frontflow 단일 skill 을 둘로 쪼갠다:
- `backflow:export-api-contract` — 라우트 → OpenAPI/tRPC 스키마 export
- `frontflow:sync-api-client` — 스키마 → TS 클라이언트·타입·MSW 핸들러 생성

- 완료 기준: 백 엔드포인트 추가 → 단일 명령으로 프론트 타입·목 서버 갱신

#### (4) `frontflow:impl-tracking` — **이벤트 트래킹**

- 입력: FS·WF 의 "사용자 이벤트" 표 (없으면 specflow 에 스키마 추가 선행)
- 출력: 이벤트 상수 모듈 + 각 컴포넌트 hook 삽입
- 완료 기준: 기획서 이벤트 목록과 코드 상수가 1:1 대조 가능

#### (5) `backflow:impl-file-upload` — **파일 업로드 표준**

- 입력: TS 의 "파일 처리" 섹션
- 출력: presigned URL 발급 컨트롤러, 리사이즈 파이프라인, 업로드 후 메타 기록 서비스
- 완료 기준: 이미지 1건 업로드 → 썸네일 3종 생성까지 자동

#### (6) `backflow:impl-webhook` — **Webhook 멱등성**

- 입력: TS 의 "외부 연동" 섹션 중 webhook 엔트리
- 출력: 서명 검증 미들웨어, idempotency-key 저장, 리플레이 차단
- 완료 기준: 같은 key 로 두 번 호출 시 두 번째는 no-op 응답

**Phase 1 Exit**: 위 6개 중 최소 4개가 이 레포에서 실 프로젝트에 한 번 이상 사용됨.

### 3.4 Phase 1.5 — dbflow (E2E 샌드박스 DB 오케스트레이션, 2–3주)

Phase 1 에서 만든 skill 들의 **실 동작 검증 수단**. velvetalk 에 이미 있는 `e2e-db` skill(1332줄)을 **독립 플러그인 `dbflow`** 로 승격.

#### 배치 근거
- Phase 1 의 (1)~(6) skill 이 있어야 **검증할 대상**이 생김
- Phase 2 의 `validate-load` · `impl-data-migration` 설계가 실 DB 기반으로 구체화되려면 이 파이프가 먼저 있어야 함
- backflow 하위가 아닌 **독립 플러그인** — "코드 생성" 이 아니라 "실 환경 오케스트레이션" 이므로 관심사 분리

#### 포함 skill
| Skill | 역할 |
|---|---|
| `dbflow:init` | `.e2e/config.yml` + `scenarios/` 스캐폴드, `.gitignore` 자동 append |
| `dbflow:snapshot` | 소스 DB → 샌드박스 DB 복제 (pg_dump \| pg_restore, 컨테이너 내부) |
| `dbflow:migrate` | 샌드박스에 마이그레이션 적용. `--fresh` 로 재스냅샷 가능 |
| `dbflow:up` / `dbflow:down` | 샌드박스 DB 에 연결된 API 서버 기동·종료 (PID 관리) |
| `dbflow:watch <tables>` | 지정 테이블의 before 스냅샷 저장 |
| `dbflow:diff [<tables>]` | watch 이후 변경(insert/update/delete) 표시 |
| `dbflow:run <scenario>` | 선언형 시나리오 YAML 실행 + 기대 DB delta 대조 |
| `dbflow:reset` / `dbflow:status` | 정리 / 상태 확인 |
| `dbflow:gen-scenarios` *(신규)* | specflow 의 QA 명세에서 `.e2e/scenarios/*.yml` 자동 생성 |

#### Safety invariants (변경 불가, 하드코드 유지)
- 소스 DB 에 쓰기 금지 (pg_dump 만, host whitelist 검증)
- 샌드박스 DB 이름은 반드시 `sandbox` 또는 `e2e` 포함. 위반 시 drop 거부
- 파괴적 작업(`snapshot`, `reset`, `--fresh`)은 기존 샌드박스 존재 시 확인 후 진행

#### 선행·병행 작업
1. **`plugins/AUTHORING.md` 에 Tier 0 (project-local) 정의 추가** — `.e2e/` 를 어느 tier 로 둘지 규약이 먼저 있어야 함
2. **`specflow:generate-qa` 포맷 확장** — QA 명세에 **E2E DB 시나리오 테이블** 섹션 추가 (API + precondition + expected delta). `dbflow:gen-scenarios` 의 입력 계약
3. **backflow 훅 연동**:
   - `backflow:impl-schema` 완료 후 "새 migration 생겼습니다. `dbflow migrate --fresh` 돌릴까요?" 제안
   - `backflow:validate-api` 후속 follow-up 으로 `dbflow:run` 추천
4. **ghflow 연동**: 시나리오 실패 시 chronicle `future_notes` 에 실패 요약·diff 자동 첨부

#### Phase 1 스코프 제한 (의도적)
- **대상 스택**: Postgres + Docker + Alembic(Python) + uv
- 일반화(Node/Prisma/MySQL, 비-Docker) 는 Phase 2 어댑터로 분리
- README 에 "현재 지원 스택" 명시

#### Exit criteria
- 최소 1개 프로젝트(velvetalk)에서 Phase 1 의 (1)~(6) skill 중 3개 이상을 `dbflow:run` 시나리오로 검증 성공
- `specflow:generate-qa` 출력 → `dbflow:gen-scenarios` → `dbflow:run` 일관 흐름 E2E 확인
- Tier 0 규약이 AUTHORING.md 에 확정됨

### 3.5 Phase 2 — 선택적 확장 (프로젝트 성격 따라, 4–8주)

| Skill 후보 | 플러그인 | 트리거 조건 |
|---|---|---|
| `impl-i18n` | frontflow | 다국어 요구사항 있는 프로젝트 |
| `impl-seo` | frontflow | 공개 웹 (랜딩·블로그·커머스) |
| `impl-feature-flags` | 공통 | Stacked PR 이 길어지는 프로젝트 |
| `impl-cache-policy` | backflow | 읽기 트래픽 ≫ 쓰기 |
| `impl-rate-limit` | backflow | 공개 API |
| `impl-audit-log` | backflow | 규제 산업 (금융·의료) |
| `validate-load` | backflow | 부하 예상 있는 endpoint 보유 |
| `validate-security` | backflow | 모든 외부 공개 서비스 (점진 확장) |
| `impl-e2e-playwright` | frontflow | QA 명세 복잡도 상위 10% |
| `impl-pwa` | frontflow | 모바일 우선, 오프라인 요구 |
| `impl-authz-policy` | backflow | 역할·권한 매트릭스 3개 이상 |
| `impl-data-migration` | backflow | 운영 중 스키마 변경 빈발 |

**선정 방식**: 프로젝트 킥오프 시 `meeting-prep` 결과에서 위 표를 체크리스트로 돌려 필요한 것만 우선 생성.

### 3.6 Phase 3 — 조직 표준 (진행 방식 먼저 합의, 8주+)

> 이 phase 는 **플러그인화 전에 조직 표준이 먼저 있어야** 한다. 표준 없이 skill 부터 만들면 팀별로 다르게 발산.

| 항목 | 사전 작업 (합의) | Skill 후보 |
|---|---|---|
| CI/CD 표준 | GitHub Actions workflow 레퍼런스 repo | `impl-ci-pipeline` |
| 환경 설정 표준 | `.env` 스키마·secrets 저장소 정책 | `impl-env-config` |
| 릴리스 노트 자동화 | CHANGELOG 포맷·버전 규칙 | `ghflow:release-notes` |
| Observability 대시보드 | 메트릭·SLI 목록 | `impl-dashboard` (IaC) |

### 3.7 specflow 측 연동 개선 (Phase 1 / 1.5 병행)

Phase 1 및 1.5 skill 들이 **specflow 산출물을 직접 읽어야** 하므로 다음을 병행:

- [ ] `generate-fs` 출력에 **이벤트 트래킹 테이블** 섹션 추가 (events.md 또는 FS 하위 섹션)
- [ ] `generate-ts` 출력에 **에러 코드 맵** 섹션 의무화 (domain-code-httpstatus-i18nKey)
- [ ] `generate-ts` 출력에 **비기능 요구** 의 관측성 요건(로그 포맷·대상) 명시
- [ ] `generate-ts` 출력에 **API 계약** 을 OpenAPI fragment 로 직접 첨부 (현재는 서술형)
- [ ] `generate-qa` 출력에 **E2E DB 시나리오 테이블** 섹션 추가 (API + precondition + expected DB delta) — `dbflow:gen-scenarios` 입력

이것이 없으면 impl / dbflow skill 들이 "해석" 에 의존해 계약이 느슨해짐.

### 3.8 타임라인 (제안)

```
Week 1       Phase 0    현황 문서화 + 우선순위 확정
Week 2-3     Phase 1    (1) 에러 계약 + specflow TS 포맷 변경
Week 3-4     Phase 1    (2) 로깅·트레이싱
Week 4-5     Phase 1    (3) API 계약 동기화 + specflow TS 의 OpenAPI fragment 도입
Week 5-6     Phase 1    (4) 이벤트 트래킹 + specflow FS 의 이벤트 테이블 도입
Week 6       Phase 1    (5) 파일 업로드
Week 7       Phase 1    (6) Webhook 멱등성
Week 8       Phase 1.5  AUTHORING.md Tier 0 규약 확정 + dbflow 포팅 착수
Week 8-9     Phase 1.5  dbflow 기본 명령 이식 (init/snapshot/migrate/up/down/watch/diff/run)
Week 9-10    Phase 1.5  specflow:generate-qa 포맷 확장 + dbflow:gen-scenarios + backflow 훅 연동
Week 10+     Phase 2    프로젝트 투입하면서 선택적으로 skill 확장
Week 14+     Phase 3    조직 표준 합의 후 skill 화
```

### 3.9 성공 지표

| 지표 | 현재 | 목표 (Phase 1 종료) | 목표 (Phase 1.5 종료) |
|---|---|---|---|
| 명세 → 구현 수기 번역 시간 (기능 1개 기준) | 측정 필요 | 50% 감소 | 50% 감소 유지 |
| front/back 타입 불일치로 인한 버그 (월) | 측정 필요 | 0건 지향 | 0건 지향 |
| 새 서비스 부트스트랩 (에러·로깅·업로드) 소요 | 1–2주 | 1–2일 | 1–2일 |
| Chronicle 기반 회고 가능 커밋 비율 | 현재 범위 | 유지 | 유지 |
| 실 DB 대상 E2E 회귀 검증 커버리지 | 0% | 0% | 주요 endpoint 50%+ |
| QA 명세 → dbflow 시나리오 자동 변환 성공률 | n/a | n/a | 80%+ (나머지는 수동 튜닝) |

### 3.10 리스크 및 대응

- **스킬 과적합**: 이 레포의 1–2개 프로젝트에만 맞게 skill 을 만들 위험. → 최소 2개 프로젝트에서 쓰인 후에만 "stable" 태그 부여
- **specflow 포맷 변경 파급**: TS/FS/QA 포맷 바뀌면 기존 명세 호환 깨짐. → `specflow:change-impact` 로 영향 분석, 구 포맷 수용 플래그 1회 릴리스 부여
- **외부 도구 lock-in**: Sentry·Amplitude 등 특정 벤더 의존. → skill 내부에서 어댑터 패턴, 기본 구현은 "noop + 콘솔" 로 두고 프로젝트별 어댑터 교체
- **dbflow 안전장치 희석**: 배포 후 사용자가 config 로 invariant 를 뚫으려 할 위험. → host whitelist, sandbox 네이밍 패턴은 **hardcoded**, config 는 *값*만 받음. README·SKILL.md 에 "변경 불가" 명시

### 3.11 즉시 다음 행동 (Phase 0 kickoff)

1. 이 문서의 2.5 우선순위에 본인·팀이 동의하는지 확정
2. 동의되면 `plugins/backflow/CONTRACTS.md`, `plugins/frontflow/CONTRACTS.md` 뼈대 작성
3. Phase 1 의 (1) 에러 계약 skill 설계 문서 작성 — 이 skill 이 specflow TS 포맷 변경을 동반하므로 가장 먼저 시작해야 영향이 누적되지 않음
4. Phase 1.5 병행 준비: velvetalk 의 `e2e-db` skill 을 **포팅 대상**으로 고정. 일반화 범위(Postgres + Docker + Alembic + uv 로 한정) 확정

---

## 부록 A — 플러그인 한눈에 보기

| 플러그인 | 역할 | 핵심 산출물 위치 | Storage Tier |
|---|---|---|---|
| `meeting-prep` | 기획·구현 갭 분석 + 회의 문서 | 세션 내 문서 | n/a |
| `specflow` | PRD → FS → WF → UI → TS → QA → 태스크 | `specs/` (프로젝트 root) | Tier 0 |
| `xreview` | 외부 LLM 교차 리뷰 | 세션 내 리뷰 결과 + `~/.hbrness/reviews/` | Tier 1 |
| `ghflow` | 이슈·브랜치·PR·리뷰·chronicle | GitHub + `~/.commit-chronicles/` | Tier 1 (+Tier 3) |
| `frontflow` | 프론트엔드 바텀업 구현 | `src/` (프로젝트별) | 프로젝트 코드 |
| `backflow` | 백엔드 바텀업 구현 | `src/` (프로젝트별) | 프로젝트 코드 |
| `dbflow` *(Phase 1.5 예정)* | E2E 샌드박스 DB 오케스트레이션 | `.e2e/` (프로젝트 root) | Tier 0 |

## 부록 B — 참고 문서

- `plugins/AUTHORING.md` — 4-tier storage convention (Tier 0 project-local, Tier 1 tool-agnostic, Tier 2 harness-placeholder, Tier 3 harness-gated)
- `docs/PROGRESS.md` — 프로젝트 전반 진행 기록 (로컬)
- `HANDOFF.md` — 세션 연속성
- 상위 지침: `~/.claude/CLAUDE.md` (Stacked PR 전략, 질문-분석 원칙)
- 레퍼런스 구현 (포팅 원본): `../velvetalk/backend/.claude/skills/e2e-db/` — 1332줄 Python CLI + 3개 reference doc
