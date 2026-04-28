# Phase 2 — 보안 검증 Skill 설계

> **Generated**: 2026-04-28
> **Scope**: Phase 2 첫 번째 항목 — `backflow:validate-security` 신설
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.5
> **Depends on**: Phase 1 upload/webhook drift 지식, `validate-code`, `validate-api`

## 목표

외부에 노출되는 backend 서비스를 대상으로 **클린룸 보안 검증 리포트**를 생성한다.

기존 `backflow:validate-code` 의 보안 항목은 유지한다. `validate-code` 는 코드 품질 게이트 안에서 빠르게 SQL injection, secret logging, 입력 검증 누락을 잡고, `validate-security` 는 public route surface 와 TS 보안 요구사항을 기준으로 더 깊은 보안 검토를 수행한다.

### Non-goals

- 프로젝트 코드를 자동 패치하지 않는다. 리포트만 작성한다.
- SAST 제품 대체가 아니다. 의존성 CVE DB 조회, 바이너리 분석, 컨테이너 이미지 스캔은 범위 밖이다.
- 침투 테스트나 런타임 exploit 검증은 하지 않는다.
- 비공개 internal-only batch/worker 코드는 target 에 포함된 경우에만 보조적으로 본다.
- project secret 값을 `backend.md` 에 저장하지 않는다.

## Public Interface

```text
backflow:validate-security [target path] [TS path optional]
```

예:

```text
backflow:validate-security src/
backflow:validate-security src/modules/auth specs/TS-2026-001.md
```

## 입력

| 입력 | 필수 | 설명 |
|---|---:|---|
| target path | required | backend 파일 또는 디렉토리. public route surface, middleware, DTO/schema, service/repository/config 를 포함하는 범위 권장 |
| TS path | optional | 기술 명세서. 없으면 `specs/TS*.md`, `specs/TS/**/*.md` 를 자동 탐색 |
| `plugins/backflow/context/backend.md` | required | framework, structure, auth, api, file_upload, webhook, security_validation 기본값 |
| `.backflow/service-registry.md` | optional | route/controller/middleware inventory 가 있으면 정밀도 향상 |
| TS §3 API | optional | route/security 요구사항 대조 |
| TS §4 error map | optional | 보안 실패 응답 code 누락 대조 |
| TS §7 nonfunctional/security | optional | TLS, CORS, cookie, logging, rate policy 대조 |
| TS §9 upload | optional | upload 보안 drift 대조 |
| TS §10 webhook | optional | webhook 서명/idempotency 보안 drift 대조 |

## 출력

리포트는 project-local Tier 0 산출물이다.

```text
specs/reviews/{target-slug}-BV3-security-{YYYYMMDD-HHmmss}.md
```

`target-slug` 는 target path 를 repo 상대 경로로 만든 뒤 `/`, 공백, 확장자를 `-` 로 정규화한다.

### Report Shape

```yaml
검증 대상: "{target path}"
검증 유형: "BV3-security"
generated_at: "{ISO-8601}"
security_pass: true | false

route_inventory:
  public_routes_checked: {N}
  auth_bypass_routes: ["METHOD /path", ...]
  webhook_routes: ["METHOD /path", ...]
  upload_routes: ["METHOD /path", ...]

findings:
  - id: "BVS-001"
    severity: critical | warning | info
    category: authn-authz | input-output | secrets-sensitive-data | injection | transport-browser | file-upload-webhook | dependency-config
    file: "{파일 경로}"
    line: {라인 번호 또는 null}
    issue: "{문제}"
    evidence: "{코드/설정에서 확인한 근거}"
    suggestion: "{수정 제안}"

summary:
  files_checked: {N}
  routes_checked: {N}
  total_findings: {N}
  critical: {N}
  warning: {N}
  info: {N}
  security_pass: true | false
```

`security_pass=false` 조건:
- critical finding 이 1건 이상
- target 을 읽을 수 없거나 route surface 를 확인할 수 없는 상태인데 public service 로 설정된 경우

warning 만 있으면 `security_pass=true` 로 둘 수 있지만, 리포트 summary 에 residual risk 를 남긴다.

## Severity Taxonomy

| Severity | 기준 |
|---|---|
| critical | 인증 우회, 권한 우회, secret/token 노출, injection 가능성, session auth 의 CSRF 누락, webhook signature/idempotency race, upload path traversal 처럼 exploit 가능성이 직접적인 문제 |
| warning | 보안 정책 drift, 방어 심층성 부족, 운영 환경에서 위험해질 수 있는 debug/config, evidence 는 있으나 exploit 가능성이 context 에 따라 달라지는 문제 |
| info | 스캔 범위, 자동 탐색 한계, 사람이 확인하면 좋은 public route inventory 항목 |

모든 finding 은 evidence 를 가져야 한다. 코드 위치나 설정 근거 없이 추측만 있는 항목은 finding 이 아니라 `info` 또는 "검증 한계"에 기록한다.

## Rule Groups

### 1. Authentication and Authorization

- public route inventory 생성: method, path, handler, guard/middleware, declared security.
- `security_validation.auth_bypass_allowlist` 에 없는 public route 가 auth guard 없이 노출되면 critical.
- role/permission decorator 가 있으나 service/repository 에서 owner/tenant scope 를 강제하지 않으면 critical 또는 warning.
- user-controlled id 로 다른 사용자/tenant 리소스를 직접 조회하면 IDOR critical.
- webhook auth bypass 는 signature middleware/guard 가 route handler 전에 실행될 때만 허용.
- `@Public`, `skipAuth`, `permitAll`, `anonymous` 패턴이 allowlist 없이 쓰이면 critical.

### 2. Input and Output Safety

- public mutation endpoint 에 DTO/schema validation 이 없거나 global validation middleware 가 꺼져 있으면 critical.
- `repo.save(req.body)`, `Object.assign(entity, body)`, `update(id, body)` 같은 mass assignment 가 허용 필드 allowlist 없이 쓰이면 critical.
- response 에 password hash, token, refresh token, secret, API key, internal stack trace 가 노출되면 critical.
- unsafe deserialization, prototype pollution, YAML/XML parser unsafe mode 는 critical.
- TS §3 schema 와 DTO가 security-sensitive field 에서 불일치하면 critical, 일반 필드 drift 는 warning.

### 3. Secrets and Sensitive Data

- hardcoded private key, JWT secret, API key, OAuth secret, DB URL credential 은 critical.
- `process.env.SECRET || "dev-secret"` 같은 운영 도달 가능한 unsafe default 는 critical.
- password/token/authorization header/request body 전체 로깅은 critical.
- `.env`, credential JSON, pem/key 파일이 target 에 포함되어 있으면 critical.
- error handler 가 raw exception message/stack 을 production response 로 내보내면 critical.

### 4. Injection Risks

- SQL/NoSQL/raw query 문자열 보간 또는 concat 에 user input 이 들어가면 critical.
- shell command execution 에 user input 이 들어가고 allowlist/escaping 이 없으면 critical.
- filesystem path 가 user input 으로 조립되고 root normalization/containment check 가 없으면 path traversal critical.
- user supplied URL 을 fetch/request/axios 로 호출하면서 host allowlist 또는 private IP 차단이 없으면 SSRF critical.
- regex, template, HTML sanitizer 관련 ReDoS/XSS 위험은 backend response surface 에 따라 warning 또는 critical.

### 5. Transport and Browser-Facing Controls

- `Access-Control-Allow-Origin: *` 와 credentials 허용 조합은 critical.
- session/cookie auth 에서 state-changing route 가 CSRF 방어 없이 열려 있으면 critical.
- auth cookie 에 `HttpOnly`, `Secure`, `SameSite` 중 핵심 속성이 없으면 warning, production session auth 는 critical 로 올린다.
- TLS 검증 비활성화(`rejectUnauthorized:false`, insecure HTTP callback, self-signed trust all)가 production path 에 있으면 critical.
- security headers(helmet 등) 부재는 public browser-facing API 에서 warning.

### 6. File Upload and Webhook Security

`validate-code` §10/§11 의 Phase 1 drift 지식을 재사용한다.

파일 업로드:
- complete handler 가 client-reported `size_bytes`/`mime_type` 만 신뢰하고 server-side `head()` 재검증이 없으면 critical.
- storage path placeholder 가 user input 으로 직접 resolve 되고 path containment 가 없으면 critical.
- local passthrough 가 production 에서 열리거나 auth/owner check 없이 열리면 critical.
- mime wildcard, size limit drift, resize metadata drift 는 warning 또는 critical.

Webhook:
- raw body 보존이 없거나 signature 검증이 handler 후에 실행되면 critical.
- HMAC 비교가 timing-safe 가 아니면 critical.
- secret 이 env 이름이 아니라 값으로 하드코딩되면 critical.
- idempotency unique constraint / insert-on-conflict / request_hash 비교가 없으면 critical.
- duplicate delivery 를 error 로 처리해 sender retry storm 을 유발하면 warning.

### 7. Dependency and Config Red Flags

- validation middleware/pipe/schema enforcement disabled in production path 는 critical.
- debug mode, stack trace response, Swagger/admin console 가 public production path 에 열리면 warning 또는 critical.
- dangerous package patterns: `eval`, `vm.runIn*`, unsafe pickle/yaml loaders, XML entity expansion, deprecated body parser limits 없음.
- rate limiting 부재는 auth/login/password reset/webhook 에서 warning. TS §7/보안 요구사항에 rate limit 이 명시되었는데 없으면 critical.

## Cleanroom Agent

`backflow:validate-security` 는 dispatcher 이고, 실제 검증은 `backflow:validator-security` agent 가 수행한다.

격리 원칙:
- 구현 과정의 의도, 이전 agent 의 설명, 수정 이력을 모른다.
- target 파일, backend context, registry, TS 문서만 기준으로 판단한다.
- "의도적으로 public" 이라는 주장은 allowlist 또는 TS/API security 선언에 있어야 인정한다.
- findings 는 재현 가능한 evidence 를 포함해야 한다.

## `backend.md` Config

`security_validation` 은 scan scope 와 policy default 만 가진다. secret value, token, credential 은 절대 넣지 않는다.

예:

```yaml
security_validation:
  exposure: "public"
  public_route_allowlist: ["/health", "/metrics"]
  auth_bypass_allowlist: ["/health", "/docs", "/webhooks/**"]
  privileged_role_names: ["admin", "owner"]
  tenant_context_keys: ["tenant_id", "workspace_id", "organization_id"]
  sensitive_fields: ["password", "password_hash", "token", "refresh_token", "secret", "api_key"]
  session_auth_requires_csrf: true
  exclude_globs: ["node_modules/**", "dist/**", "coverage/**", ".git/**"]
```

## Integration

- canonical flow: `validate-code` / `validate-api` 이후, `validate-tests` 전 또는 release gate 전 실행 권장.
- public service 는 PR merge 전 `security_pass=true` 가 필요하다.
- 결과 리포트는 `patch-backend` 또는 수동 수정의 입력으로 사용한다.
