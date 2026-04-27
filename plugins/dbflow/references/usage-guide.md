# dbflow Usage Guide (Phase 1.5)

> velvetalk `e2e-db/references/usage-guide.md` 의 hbrness 적응판. Phase 1.5.0~1.5.6 진행 중 점진 작성.

## 시작 (Scenario A — 신규 프로젝트)

1. `dbflow:init` — `.e2e/` 스캐폴드
2. `.e2e/config.yml` 사용자 작성 (allowed_hosts / sandbox.name / migrate.command)
3. `dbflow:snapshot` — source → sandbox 첫 복제
4. `dbflow:migrate` — sandbox 에 마이그레이션
5. `dbflow:up` — API 서버 기동
6. `specflow:generate-qa` 후 `dbflow:gen-scenarios` — `.e2e/scenarios/*.yml` 생성
7. `dbflow:run <scenario>` — 검증

## velvetalk 마이그레이션 (Scenario B)

`.e2e/config.yml` 그대로 호환. 시나리오 YAML 그대로. 단 단일 명령 `/e2e-db init` 대신 분리 명령 `/dbflow:init` 사용.

## 본문은 sub-phase 진행 중 점진 작성.
