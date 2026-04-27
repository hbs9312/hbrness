---
name: scan-codebase
description: 기존 프로젝트의 서비스, 리포지토리, 미들웨어를 스캔하여 레지스트리를 생성합니다. "코드베이스 스캔", "기존 코드 파악" 요청 시 사용.
argument-hint: (인자 없음 — backend.md의 경로를 자동 참조)
tools: [file:read, search:grep, search:glob, file:write, shell(npm *), shell(npx *), shell(cat *)]
effort: medium
model: sonnet
---

# 코드베이스 스캔 (BU1)

기존 프로젝트에서 재사용 가능한 서비스, 리포지토리, 미들웨어, 유틸리티를 파악합니다.
B1~B6에서 "이미 있는 것을 새로 만들지 않도록" 방지하는 핵심 스킬입니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md)

## 스캔 대상

backend.md에서 경로를 읽어 스캔:

1. **엔티티 / 스키마** (`entity_dir`, `schema_path`)
   - 테이블/모델명
   - 필드 + 타입
   - 관계 (FK, 1:N, N:M)

2. **리포지토리** (`repository_dir`)
   - 리포지토리 클래스명
   - 공개 메서드 + 시그니처
   - 대상 엔티티

3. **서비스** (`service_dir`)
   - 서비스 클래스명
   - 공개 메서드 + 시그니처
   - 주입된 의존성

4. **컨트롤러** (`controller_dir`)
   - 엔드포인트 목록 (method + path)
   - 적용된 가드/미들웨어
   - 요청/응답 DTO

5. **미들웨어 / 가드** (`middleware_dir`)
   - 가드 클래스명 + 적용 대상
   - 전역 미들웨어 목록

6. **공유 유틸리티** (`util_dir`)
   - export된 함수/클래스 목록

## 출력

```yaml
# service-registry.md

existing_entities:
  - name: "User"
    table: "users"
    fields: ["id", "email", "name", "role", "created_at"]
    relations:
      - type: "1:N"
        target: "Workspace"
        field: "workspaces"

existing_repositories:
  - name: "UserRepository"
    path: "src/repositories/user.repository.ts"
    entity: "User"
    methods:
      - "findByEmail(email: string): Promise<User | null>"
      - "findByWorkspace(workspaceId: string): Promise<User[]>"

existing_services:
  - name: "AuthService"
    path: "src/services/auth.service.ts"
    dependencies: ["UserRepository", "JwtService"]
    methods:
      - "validateUser(email, password): Promise<User>"
      - "generateToken(user): Promise<string>"

existing_controllers:
  - name: "AuthController"
    path: "src/controllers/auth.controller.ts"
    endpoints:
      - "POST /api/v1/auth/login"
      - "POST /api/v1/auth/register"
    guards: ["LocalAuthGuard"]

existing_middleware:
  - name: "JwtAuthGuard"
    path: "src/guards/jwt-auth.guard.ts"
    applies_to: "글로벌 (제외: /auth/*)"

existing_utils:
  - name: "hashPassword"
    path: "src/common/crypto.ts"
  - name: "generateId"
    path: "src/common/id.ts"

existing_error_codes:
  - path: "src/common/error-codes.ts"
    codes: ["UNAUTHORIZED", "NOT_FOUND", "VALIDATION_ERROR"]

scan_summary:
  entities: {N}
  repositories: {N}
  services: {N}
  controllers: {N}
  endpoints: {N}
  scanned_at: "{timestamp}"
```

## 저장: `.backflow/service-registry.md`

## 갱신 시점
- backflow 워크플로우 시작 전 1회
- 새 서비스 추가 후 (Phase 완료 후)
