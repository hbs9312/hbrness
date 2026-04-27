# Scenario YAML reference (Phase 1.5 dbflow)

> velvetalk `e2e-db/references/scenario-reference.md` 의 hbrness 적응판. 본문은 Phase 1.5.5 에서 작성됨. 현재 stub.
>
> 원본 schema 와 1:1 호환 — multi-step / per-step auth / response interpolation / db_diff DSL.

## Top-level fields

(설계 doc §4 의 schema 그대로 — TODO: sub-phase 1.5.5)

- name (string), description, fixtures.sql_file, watch_tables, auth.login_as, steps[]

## steps[]

- request {method, path, query, headers, body}
- expect {status, response_contains, response_equals, db_diff}
- auth (per-step override)

## db_diff DSL

(설계 doc §4 의 표 그대로 — inserted_count / inserted_match / deleted_count / deleted_match / modified_count / modified_match {from, to} / unchanged)

## 변수 interpolation

`{steps.<step_name>.response.<json_path>}` — 다른 형식 금지

## 본문은 Phase 1.5.5 에서.
