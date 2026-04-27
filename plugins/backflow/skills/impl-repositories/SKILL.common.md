---
name: impl-repositories
description: 데이터 접근 계층(리포지토리)을 구현합니다. "리포지토리 생성", "데이터 접근 계층" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
model: sonnet
---

# 리포지토리 / 데이터 접근 계층 (B2)

ultrathink

당신은 백엔드 개발자입니다.
B1에서 생성한 스키마에 대한 데이터 접근 계층을 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — database, structure
- 기존 코드 레지스트리: `.backflow/service-registry.md` (있으면)
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면) — 이 스킬이 담당하는 파일 목록

## 입력

$ARGUMENTS 의 기술 명세서(TS) → Read.
데이터 모델 + 처리 흐름 섹션이 주 입력입니다.

추가로 자동 탐색:
- B1에서 생성한 스키마 파일 (엔티티 구조 확인)
- backend.md의 `repository_dir` → 기존 리포지토리 확인

## 태스크-파일 맵 준수

`.backflow/task-file-map.md`가 존재하면:
1. `impl_skill: impl-repositories` 항목만 필터
2. `action: create` → 해당 경로에 새 파일 생성
3. `action: modify` → 해당 경로의 기존 파일 수정
4. `responsibility.should` → 이 파일에서 구현할 범위
5. `responsibility.should_not` → 이 파일에서 하지 않을 것
6. 맵에 없는 파일은 생성하지 않음 (맵 누락이 의심되면 경고 출력)

맵이 없으면 기존 로직대로 독자 판단.

## ★ 재사용 판단 — 가장 먼저 실행 ★

1. 기존 리포지토리 스캔 (BU1 산출물 또는 직접 스캔)
2. 판단:
   - **동일 리포지토리 존재** → 메서드만 추가
   - **유사 패턴 존재** → 기존 베이스 클래스/패턴 따름
   - **완전히 새로운 것** → 신규 생성

## 리포지토리 생성 규칙

### 파일 구조

backend.md의 `structure` + `module_pattern` 설정을 따름:

```
# flat 패턴
{repository_dir}/{entity}.repository.ts

# feature-module 패턴
{src_root}/modules/{feature}/repositories/{entity}.repository.ts

# domain-driven 패턴
{src_root}/domain/{aggregate}/infrastructure/{entity}.repository.ts
```

### ORM별 구현 패턴

**Prisma**:
```typescript
// PrismaClient를 주입받아 사용
@Injectable()
export class SpeakerRepository {
  constructor(private readonly prisma: PrismaService) {}

  async findByWorkspace(workspaceId: string): Promise<Speaker[]> {
    return this.prisma.speaker.findMany({
      where: { workspace_id: workspaceId },
      orderBy: { created_at: 'desc' },
    })
  }
}
```

**TypeORM**:
```typescript
@Injectable()
export class SpeakerRepository extends Repository<Speaker> {
  // EntityManager 또는 DataSource 기반
}
```

### TS → 리포지토리 메서드 매핑

TS의 시퀀스 다이어그램에서 DB 접근 패턴을 추출:

```
TS 시퀀스                    →    리포지토리 메서드
────────────────────────────────────────────────────
"화자 목록 조회"              →    findByWorkspace(workspaceId)
"화자명 중복 확인 (BR-003)"   →    existsByNameInWorkspace(name, workspaceId)
"화자 등록"                   →    create(data)
"화자 상태 업데이트"           →    updateStatus(id, status)
"화자 삭제"                   →    softDelete(id) 또는 delete(id)
```

### 쿼리 최적화 원칙

1. **N+1 방지**: 관계 로드가 필요하면 명시적 join/include
2. **Select 최소화**: 필요한 필드만 select (목록 조회 시)
3. **페이지네이션**: 목록 조회에 cursor 또는 offset 기반 페이지네이션
4. **트랜잭션 경계**: 리포지토리는 단일 쿼리만, 트랜잭션은 서비스 계층에서

### 타입 안전성

- 입력/출력에 정확한 타입 사용 (any 금지)
- DTO ↔ Entity 변환이 필요하면 명시적 매핑
- nullable 필드는 `| null` 명시

## 품질 자가 점검

- [ ] TS 시퀀스의 모든 DB 접근이 리포지토리 메서드로 존재하는가
- [ ] N+1 쿼리 패턴 = 0건
- [ ] 리포지토리가 비즈니스 로직을 포함하지 않는가 (순수 데이터 접근만)
- [ ] 트랜잭션 코드가 리포지토리에 없는가 (서비스에서 관리)
- [ ] backend.md의 naming, structure 컨벤션을 따르는가
- [ ] any 타입 = 0건
