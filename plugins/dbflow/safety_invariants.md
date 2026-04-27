# dbflow Safety Invariants

> 이 문서는 **변경 불가 hardcode 보안 계약** 3종을 상세히 기술한다. 설계 doc (`docs/designs/phase-1.5-dbflow.md`) §0 핵심 invariant + §7 §A~§C 를 풀어 작성.
>
> `dbflow:validate-scenarios` (Phase 1.5.6) 는 이 3가지 invariant 를 §A~§C 로 검사한다.

---

## Invariant 1 — 소스 DB 쓰기 금지

### Why

source DB 는 팀 공유 개발 DB 또는 스테이징 DB 일 가능성이 높다. 실수로 source DB 를 drop / truncate / migrate 하면 팀 전체에 영향. sandbox 만 destructive 명령의 대상이어야 한다.

### How Enforced (실행 계약)

- **`pg_dump` wrapper 만 source URL 을 받는다.** `pg_dump` 는 read-only 덤프 명령이므로 source URL 사용이 안전.
- `psql`, `pg_restore`, `migrate` (마이그레이션 명령), fixture SQL 적용, API server 실행 등 그 외 **모든 명령은 sandbox URL 만 받는다.**
- `source.allowed_hosts` 는 source URL 의 host 가 승인된 목록 안에 있는지 검증하는 추가 방어선. 기본값: `[localhost, 127.0.0.1, postgres, db]`.

### validate-scenarios §A 검사

```
§A — 소스 DB 쓰기 금지:
  source_allowed_hosts:
    - source.allowed_hosts 가 비어있음 → critical
    - source URL 의 host 가 allowed_hosts 에 없음 → critical
  no_source_write_path (보조 lint):
    - scenarios / fixtures SQL 에 source URL host 가 직접 등장 → warning
    - (SKILL 본문 계약이 1차 보장 — grep 은 보조)
```

### 우회 시도 패턴 (모두 거부)

- config.yml 에 `source.url` 를 sandbox 로 설정하는 것 → allowed_hosts 가 sandbox host 를 차단
- `pg_restore` 에 source URL 을 직접 전달 → SKILL 본문 계약: sandbox URL 만 허용
- fixture SQL 에 source host 직접 기재 → §A 보조 lint 가 warning

### 위반 시 동작

- `source_allowed_hosts` critical → `dbflow:snapshot` 실행 즉시 중단 + 오류 메시지: "source URL 의 host 가 allowed_hosts 에 없습니다."
- `no_source_write_path` warning → `dbflow:validate-scenarios` 가 warning 출력 (실행 차단 아님)

---

## Invariant 2 — 샌드박스 DB 이름 검증

### Why

`sandbox.name` 이 임의 문자열이면 실수로 본 DB 이름을 지정해 데이터를 전부 날릴 수 있다. `sandbox` 또는 `e2e` 포함을 강제해 "이 DB 는 실험용" 이라는 의도를 이름에 박는다.

### How Enforced

- 모든 destructive 명령(`snapshot --fresh` / `reset` / `migrate --fresh`) 실행 전 `config.sandbox.name` 에 `sandbox` 또는 `e2e` 문자열이 포함되어 있는지 검사.
- **포함되지 않으면 즉시 실행 거부.** 설정을 바꾸도록 안내.
- `sandbox.connection` 이 명시된 경우에도 sandbox.name 검증은 항상 실행.

### validate-scenarios §B 검사

```
§B — 샌드박스 DB 이름:
  sandbox_name_pattern:
    - sandbox.name 에 'sandbox' 또는 'e2e' 미포함 → critical
      (drop / snapshot / reset 거부 사전 알림)
  destructive_target:
    - destructive 명령이 sandbox 외 DB 를 target → critical
      (SKILL 본문에서 sandbox URL 만 받도록 강제됨)
```

### 우회 시도 패턴 (모두 거부)

- `sandbox.name: myproject_db` (sandbox / e2e 미포함) → invariant 위반, destructive 명령 전부 거부
- `sandbox.name: e2e_sandbox` → 허용 (`e2e` 포함)
- `sandbox.name: project_sandbox_v2` → 허용 (`sandbox` 포함)

### 위반 시 동작

- `dbflow:reset` / `dbflow:snapshot --fresh` / `dbflow:migrate --fresh` 실행 시 이름 검사 선행
- 위반 시: "sandbox.name '<name>' 이 'sandbox' 또는 'e2e' 를 포함하지 않습니다. config.yml 을 확인하세요." + 실행 중단

---

## Invariant 3 — 파괴 작업 Confirm

### Why (XR-001 출처)

config 또는 flag 로 confirm 을 우회할 수 있으면 자동화 스크립트가 실수로 sandbox 를 날릴 수 있다. "현재 turn 에 사용자가 직접 명시 요청" 만이 유일한 합법적 예외.

### How Enforced

- `snapshot --fresh`, `reset`, `migrate --fresh` 는 **SKILL 본문 rule** 로 사용자 명시 confirm 필수.
- `config.yml` 에 `confirm.*` / `auto_confirm` 같은 키를 추가해도 **무시** — config 로 confirm 을 끄는 경로 존재 X.
- `--no-confirm` / `--yes` / `--force` flag 는 이 3가지 명령에서 **구현하지 않음** (flag 자체가 없음).
- **자동화 예외**: "현재 turn 에 사용자가 직접 destructive 명령을 요청했을 때" 만. SKILL 본문에 이 예외 명시. CI 스크립트 / 배치 실행 등에서는 예외 적용 X.

### validate-scenarios §C 검사

```
§C — Confirm bypass 금지 (XR-001):
  no_confirm_in_config:
    - .e2e/config.yml 에 'confirm.*' 또는 'auto_confirm' 키 등장 → critical
  no_force_flag:
    - 명령 history 에 --no-confirm / --yes / --force 가 destructive 명령에 사용 → critical
    - 자동화 예외 = "현재 turn 에 사용자가 직접 destructive 명령 요청" 만
```

### 우회 시도 패턴 (모두 거부)

| 시도 | 결과 |
|---|---|
| `config.yml` 에 `auto_confirm: true` 추가 | §C critical, config 키 무시 |
| `dbflow:reset --no-confirm` | flag 미구현, SKILL 이 거부 |
| `dbflow:snapshot --fresh --yes` | flag 미구현, SKILL 이 거부 |
| CI 파이프라인에서 자동 실행 | 예외 미해당 (현재 turn 사용자 요청 아님) — confirm 대기 또는 거부 |
| 현재 turn 에 "reset 해줘" 요청 | 자동화 예외 적용 — confirm 생략 허용 |

### 위반 시 동작

- `no_confirm_in_config` critical → `dbflow:validate-scenarios` 가 오류 출력: "config.yml 에 confirm bypass 키가 있습니다. 제거하세요."
- destructive 명령 실행 시 confirm 없이 진행하려 하면: "이 명령은 파괴적입니다. 계속하시겠습니까? (y/N)" 대기

---

## 3 Invariant 요약표

| # | 이름 | 핵심 룰 | 검사 위치 | 위반 시 |
|---|---|---|---|---|
| 1 | 소스 DB 쓰기 금지 | pg_dump 만 source URL | SKILL 본문 + §A | critical + 실행 중단 |
| 2 | 샌드박스 DB 이름 | sandbox.name 에 sandbox/e2e 포함 | SKILL 본문 + §B | critical + destructive 거부 |
| 3 | 파괴 작업 confirm | config/flag 우회 금지 | SKILL 본문 + §C | critical + 실행 대기 |

> 이 3가지는 Phase 1.5 전체에서 절대 변경 금지. 변경이 필요하다면 별도 설계 review + 전체 SKILL 파일 동기화 필요.
