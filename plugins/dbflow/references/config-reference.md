# `.e2e/config.yml` reference (Phase 1.5 dbflow)

> velvetalk `e2e-db/references/config-reference.md` 의 hbrness 적응판. 본문은 Phase 1.5.2~1.5.3 에서 작성됨. 현재 stub.
>
> 원본 schema 와 1:1 호환 — Scenario B (velvetalk 마이그레이션) 를 위해.

## 8 섹션

(설계 doc §3 의 schema 그대로 — TODO: sub-phase 1.5.2~1.5.3 에서 본문)

- source — dev DB to clone from
- docker — Postgres container
- sandbox — target DB (이름 'sandbox' 또는 'e2e' 강제)
- migrate — schema 마이그레이션 명령 (자유)
- server — API 서버 기동
- auth — bearer / jwt_direct / none
- diff — ignore_columns / per_table / exclude_tables
- reports — JSON report 디렉토리

자세한 필드 정의는 후속 sub-phase 에서.
