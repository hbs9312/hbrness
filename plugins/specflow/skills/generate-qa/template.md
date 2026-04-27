# 테스트 명세서 출력 템플릿

```yaml
문서 ID: QA-{YYYY}-{NNN}
기능 참조: {FS ID}
기술 참조: {TS ID}
UI 참조: {UI ID}
작성일: {YYYY-MM-DD}
상태: Draft

# 1. 기능 테스트 (AC 기반)
### TC-001: {제목}
- 참조: {AC/BR-NNN}
- 전제조건: {구체적}
- 입력: {구체적}
- 기대결과: {검증 가능}

# 2. 기술 테스트 (장애/경합)
### TC-00N: {장애 시나리오}
- 참조: {TS ID} > {섹션}
- 시나리오: {장애 유형}
- 기대결과: {처리}

# 3. UI 테스트 (상태 전환)
# 4. 비기능 테스트 (부하, 보안)
```

# 5. E2E DB 시나리오 (Phase 1.5)

| scenario_name | feature_ref | watch_tables | steps_summary | db_diff_summary | fixture_required |
|---|---|---|---|---|---|
| {snake_case 또는 한글} | {US/AC/BR} | {comma 구분 또는 all} | {METHOD /path → status (자연어 요약)} | {table.assertion: value (자연어 요약)} | {fixture 파일명 또는 (없음)} |

규칙:
- scenario_name: 전역 유일. dbflow:gen-scenarios 의 입력
- watch_tables: 변경 + unchanged 단언 대상. 명시적 권장 (all 지양)
- steps_summary: TS §3.2 OpenAPI fragment 의 path 와 매칭 가능해야 함. × N 으로 반복 표기
- db_diff_summary: 자연어. gen-scenarios 가 원본 db_diff DSL (inserted_count / inserted_match / modified_match {from, to} / deleted_match / unchanged) 로 변환
- fixture_required: cross-feature/edge state 만. in-feature 동작은 step chaining 으로 (fixture 로 우회 X)
