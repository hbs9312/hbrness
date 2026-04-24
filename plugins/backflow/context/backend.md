# 백엔드 프로젝트 컨텍스트

모든 backflow 스킬이 참조하는 프로젝트 설정입니다.
프로젝트 초기화 시 1회 작성하고, 기술 스택 변경 시 갱신하세요.

## 프레임워크

```yaml
framework:
  name: ""               # NestJS | Express | Fastify | Spring Boot | Django | FastAPI
  version: ""            # 예: 10.x
  language: ""           # TypeScript | Java | Python | Go | Kotlin
  language_version: ""   # 예: 5.x
```

## 데이터베이스

```yaml
database:
  primary: ""            # PostgreSQL | MySQL | MongoDB | SQLite
  orm: ""                # Prisma | TypeORM | Drizzle | Sequelize | SQLAlchemy | GORM
  migration_tool: ""     # orm 내장 | knex | flyway | alembic
  naming_convention: ""  # snake_case | camelCase
  schema_path: ""        # 예: prisma/schema.prisma, src/entities/
```

## 디렉토리 구조

```yaml
structure:
  src_root: ""           # 예: src/
  controller_dir: ""     # 예: src/controllers 또는 src/modules/*/controllers
  service_dir: ""        # 예: src/services 또는 src/modules/*/services
  repository_dir: ""     # 예: src/repositories 또는 src/modules/*/repositories
  entity_dir: ""         # 예: src/entities 또는 src/modules/*/entities
  middleware_dir: ""     # 예: src/middleware
  dto_dir: ""            # 예: src/dto 또는 src/modules/*/dto
  util_dir: ""           # 예: src/common 또는 src/lib
  test_dir: ""           # 예: src/**/*.spec.ts 또는 tests/
  module_pattern: ""     # flat | feature-module | domain-driven
  naming: "kebab-case"   # 파일명 컨벤션
```

## 인증 / 인가

```yaml
auth:
  strategy: ""           # jwt | session | oauth2 | api-key
  guard_pattern: ""      # decorator | middleware | interceptor
  role_model: ""         # RBAC | ABAC | none
  token_location: ""     # Authorization header | cookie
```

## API 스타일

```yaml
api:
  style: ""              # REST | GraphQL | gRPC
  versioning: ""         # url-prefix(/api/v1) | header | none
  base_path: ""          # 예: /api/v1
  doc_tool: ""           # Swagger/OpenAPI | none
  request_validation: "" # class-validator | zod | joi | pydantic
  response_format: |
    // 프로젝트의 응답 래핑 패턴
    // 예:
    // { success: true, data: T }
    // { success: false, error: { code: string, message: string } }
```

## 에러 핸들링

```yaml
error_handling:
  strategy: ""           # exception-filter | error-middleware | global-handler
  error_class: ""        # 예: HttpException, AppError
  error_code_enum: ""    # 예: src/errors/codes.ts — 에러 코드 enum 파일 (impl-error-codes 출력)
  http_mapping_file: ""  # 예: src/errors/http-mapping.ts — code → HTTP status 매핑 파일
  i18n_enabled: true     # true: i18n JSON 생성 | false: 메시지 코드에 inline
  i18n_output_dir: ""    # 예: src/locales — errors.{lang}.json 출력 디렉토리 (i18n_enabled=true 시)
  languages: ["ko", "en"] # 생성할 i18n 언어 목록 (TS §에러 코드 맵 컬럼과 1:1)
  logging: ""            # winston | pino | bunyan | built-in
  pattern: |
    // 프로젝트의 에러 핸들링 패턴
```

## 테스트

```yaml
testing:
  runner: ""             # jest | vitest | pytest | JUnit
  unit_pattern: ""       # *.spec.ts | *.test.ts | test_*.py
  integration_pattern: ""# *.e2e-spec.ts | *.int.test.ts
  mock_strategy: ""      # jest.mock | sinon | testcontainers
  db_strategy: ""        # in-memory | testcontainers | sqlite | truncate
  coverage_target: ""    # 예: 80%
```

## 외부 서비스

```yaml
external_services:
  message_queue: ""      # none | Redis/BullMQ | RabbitMQ | SQS | Kafka
  cache: ""              # none | Redis | Memcached
  storage: ""            # none | S3 | GCS | local
  email: ""              # none | SendGrid | SES | Resend
  realtime: ""           # none | SSE | WebSocket | Socket.IO
```
