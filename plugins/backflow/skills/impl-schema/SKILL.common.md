---
name: impl-schema
description: 기술 명세서의 데이터 모델을 DB 스키마와 마이그레이션으로 구현합니다. "스키마 생성", "테이블 생성", "마이그레이션" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit, shell(npx *), shell(npm *), shell(cat *)]
effort: max
---

# DB 스키마 + 마이그레이션 (B1)

ultrathink

당신은 데이터베이스 엔지니어입니다.
기술 명세서(TS)의 데이터 모델 섹션을 DB 스키마로 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — database 섹션 필수
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면) — 이 스킬이 담당하는 파일 목록

## 입력

$ARGUMENTS 에서 기술 명세서(TS) 경로 → Read.
"데이터 모델" 섹션이 주 입력입니다.

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-schema` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 해당 경로의 기존 파일 수정
4. `responsibility.should` → 이 파일에서 구현할 범위
5. `responsibility.should_not` → 이 파일에서 하지 않을 것
6. 맵에 없는 파일은 생성하지 않음 (맵 누락이 의심되면 경고 출력)

맵이 없으면 기존 로직대로 독자 판단.

## ★ 기존 스키마 확인 — 가장 먼저 실행 ★

1. backend.md의 `schema_path`에서 기존 스키마 Read
2. 기존 테이블/엔티티 목록 확인
3. 판단:
   - **동일 테이블 존재** → 마이그레이션으로 컬럼 추가/변경만
   - **완전히 새로운 것** → 신규 생성

## ORM별 분기

backend.md의 `database.orm` 값에 따라 출력이 달라집니다:

### Prisma
- `schema.prisma`에 model 추가
- `npx prisma migrate dev --name {feature}` 명령 준비
- ★ 기존 model을 삭제/수정하지 않고 추가만

### TypeORM
- Entity 클래스 생성 (데코레이터 기반)
- Migration 파일 생성

### Drizzle
- 스키마 파일에 table 정의 추가
- `drizzle-kit generate` 명령 준비

### SQLAlchemy
- Model 클래스 생성
- Alembic revision 생성

## TS → 스키마 변환 규칙

### 1. 테이블/컬렉션 생성

TS 데이터 모델의 각 엔티티 → 테이블:

```
TS 데이터 모델          →    DB 스키마
────────────────────────────────────────
엔티티                  →    테이블
필드 + 타입             →    컬럼 + 타입
UNIQUE 제약 (BR-NNN)    →    UNIQUE 인덱스 + 주석
NOT NULL                →    NOT NULL 제약
기본값                  →    DEFAULT
```

### 2. 관계 + FK

```
TS 관계                 →    DB 관계
────────────────────────────────────────
1:N                     →    FK + ON DELETE 정책 (TS에 명시된 대로)
N:M                     →    조인 테이블
참조 무결성             →    FK 제약 + 인덱스
```

FK 삭제 정책은 TS에 명시된 것을 그대로 따름:
- CASCADE, SET NULL, RESTRICT 등
- TS에 명시 없으면 RESTRICT (안전 기본값) + warning 리포트

### 3. 인덱스

TS "인덱스 근거" 섹션의 쿼리 패턴 → 복합 인덱스:

```sql
-- TS: "workspace_id + created_at 기준 정렬 조회"
CREATE INDEX idx_speakers_workspace_created 
  ON speakers (workspace_id, created_at DESC);
```

### 4. Enum 타입

TS의 상태 enum → DB enum 또는 체크 제약:

```
-- TS: embedding_status: pending | processing | ready | failed
-- PostgreSQL
CREATE TYPE embedding_status AS ENUM ('pending', 'processing', 'ready', 'failed');
-- 또는 ORM enum 타입
```

### 5. 감사 필드 (공통)

모든 엔티티에 자동 추가 (TS에 명시 없어도):
- `created_at` TIMESTAMP NOT NULL DEFAULT NOW()
- `updated_at` TIMESTAMP NOT NULL DEFAULT NOW()
- 소프트 삭제가 TS에 명시되어 있으면 `deleted_at` TIMESTAMP NULL

## 마이그레이션 규칙

- 마이그레이션 이름: `{timestamp}_{feature}_{action}` (예: `20260412_speakers_create`)
- up/down 양방향 작성
- 데이터 파괴적 변경 시 2단계 마이그레이션:
  1. 새 컬럼 추가 (nullable)
  2. 데이터 마이그레이션 후 NOT NULL + 구 컬럼 삭제

## 품질 자가 점검

- [ ] TS 데이터 모델의 모든 엔티티가 스키마에 존재하는가
- [ ] TS의 모든 UNIQUE/NOT NULL/DEFAULT 제약이 반영되었는가
- [ ] FK 삭제 정책이 TS와 일치하는가 (명시 없으면 RESTRICT)
- [ ] 인덱스가 TS의 쿼리 패턴을 커버하는가
- [ ] 상태 enum이 TS 정의와 일치하는가
- [ ] 마이그레이션에 rollback(down)이 있는가
- [ ] 기존 스키마와 충돌 = 0건
- [ ] BR 주석이 제약 조건에 포함되었는가

## dbflow 연계 (Phase 1.5)
새 migration 생성 후 → `dbflow:migrate --fresh` 권장. sandbox DB 에 최신 schema 반영.
