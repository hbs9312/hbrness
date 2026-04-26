---
name: impl-file-upload
description: TS §9 파일 처리 → presigned URL controller + server-side head 재검증 + 메타 + storage adapter (벤더 격리). "파일 업로드", "이미지 업로드" 요청 시 사용.
argument-hint: [기술 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 파일 업로드 구현 (B-FILE)

ultrathink

당신은 백엔드 스토리지 엔지니어입니다.

TS §9 파일 처리 → presigned URL controller + 완료 콜백(server-side head 재검증) + 메타 entity + (옵션) 리사이즈 worker + 스토리지 어댑터(벤더 격리)를 구현합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [backend.md](../../context/backend.md) — `file_upload.*` 섹션 **필수**, `structure.*`, `framework.*`, `database.orm`, `external_services.storage`
- **태스크-파일 맵**: `.backflow/task-file-map.md` (있으면)
- **서비스 레지스트리**: `.backflow/service-registry.md` (StorageService 검출용)

## 입력

$ARGUMENTS 에서 기술 명세서(TS) 파일 경로를 추출하여 Read 로 읽으세요.

필수 입력:
1. **TS §9 파일 처리** — upload_kind / mime_types / max_size_mb / storage_path / resize_variants / retention_days
2. **TS §3.2 OpenAPI fragment** — operationId 검증 (`upload{UploadKindCamel}` 존재 확인)
3. **TS §4 에러 코드 맵** — FILE_TOO_LARGE / MIME_NOT_ALLOWED / STORAGE_UNAVAILABLE / FILE_INTEGRITY_MISMATCH / FILE_NOT_FOUND 자동 추가 권고
4. **TS §5 데이터 모델** — 메타 entity 의 owner FK 도출

## ★ 실행 위치 — impl-integrations 후, export-api-contract 전 ★

```
impl-integrations         ← TS §인프라, §외부 호출 (B3 stub 교체)
     │
     ▼
impl-file-upload          ← TS §9 + §3.2 + §4 + §5   ★ Phase 1 (5)
     │
     ▼
export-api-contract       ← TS §3.2 + §4 + 라우트(file-upload controller 포함)
```

## 선행 skill 책임 경계

### `impl-controllers` 와의 경계

- TS §9 의 upload_kind 마다 `upload{UploadKindCamel}` operationId 가 §3.2 fragment 에 존재
- `impl-controllers` 는 이 operationId 들을 **skip** (또는 stub 만 — 본문은 비워둠)
- 본 skill 이 그 자리에 실제 controller 핸들러 작성. NestJS 시 별도 UploadsModule/controller 생성 권장

### `impl-integrations` 와의 경계

- `.backflow/service-registry.md` 에서 기존 StorageService 검출
  - **호환 시**: 기존 service 위에 StorageAdapter 인터페이스를 충족하는 wrapper 작성 (재구현 금지)
  - **비호환 시**: 사용자 confirm 후 wrapper 또는 신규 adapter 작성. 기존 service 보존

## StorageAdapter 인터페이스

`backend.md.file_upload.storage_subdir` 하위의 `storage/types.ts` 에 생성:

```typescript
// storage/types.ts
export type UploadMode = 'put' | 'post' | 'resumable';

export interface PresignPutResult {
  uploadMode: UploadMode;             // 'put' (S3 PUT URL, GCS V4) | 'post' (S3 POST policy) | 'resumable' (GCS resumable)
  uploadUrl: string;
  method: 'PUT' | 'POST';             // uploadMode 와 일치
  headers?: Record<string, string>;   // PUT 시 Content-Type, signed headers 등
  fields?: Record<string, string>;    // POST policy 시 form field
  expiresAt: string;                  // ISO-8601
  enforcedContentType?: string;
  enforcedMaxSizeBytes?: number;
}

export interface PresignGetResult { url: string; expiresAt: string; }

export interface HeadResult { exists: boolean; sizeBytes?: number; contentType?: string; etag?: string; }

export interface StorageAdapter {
  presignPut(opts: { path: string; contentType: string; maxSizeBytes: number; ttlSec: number }): Promise<PresignPutResult>;
  presignGet(opts: { path: string; ttlSec: number }): Promise<PresignGetResult>;
  delete(path: string): Promise<void>;
  head(path: string): Promise<HeadResult>;
}
```

## Controller 동작

### `POST /uploads/presign`

- body: `{ upload_kind, mime_type, size_bytes, ...customPlaceholderValues }`
- 검증:
  1. `upload_kind` 가 TS §9 에 존재
  2. `mime_type` 이 §9.mime_types 에 매칭
  3. `size_bytes` ≤ §9.max_size_mb * 1024 * 1024
  4. custom placeholder 들이 모두 제공되고 owner 권한 검증 (impl-middleware 가드 적용)
  5. server 가 `file_id` 발급 (`backend.md.file_upload.file_id_strategy` — uuid_v7) + `storage_path` resolve
- 메타 행 `status: pending` 생성
- 어댑터 `presignPut` 호출 → 결과 그대로 반환 (uploadMode/method/headers/fields 포함)
- 응답: `{ file_id, meta_id, upload: PresignPutResult, storage_path }`

### `POST /uploads/{file_id}/complete`

- body: `{ etag? }` — **client 의 size_bytes / mime_type 신뢰 금지**
- server-side 검증:
  1. meta 행 조회 (`status: pending` 인지)
  2. **`storage.head(storage_path)` 호출** — 실제 size / contentType / etag 확인
  3. head 결과 `sizeBytes` 가 §9.max_size_mb 초과 또는 contentType 이 §9.mime_types 와 다르면 → `FILE_INTEGRITY_MISMATCH` 에러 + meta `status: failed` + storage.delete
  4. OK 시 meta `status: complete` + `completed_at` + `metadata.original = { path, size_bytes, mime_type }`
  5. variants 가 있으면 리사이즈 job enqueue (메타 `metadata.variants[variant] = { status: pending }`)
- 응답: `{ file_id, status: 'complete', urls: { original, ...(완료된 variants) } }`

### `GET /uploads/{file_id}`

- meta 조회 + `presignGet` 으로 download URL 생성. owner 권한은 middleware 가드

### `DELETE /uploads/{file_id}`

- soft delete (meta `status: expired`) + `storage.delete()` 호출

### Local passthrough (보안 제한)

- `storage_vendor === ''` **AND** `NODE_ENV !== 'production'` 시에만 route 등록
- endpoint: `POST /uploads/local-passthrough/{file_id}` — **query path 직접 사용 금지**
- 동작: `file_id` 로 pending meta 조회 → server-side 에서 `storage_path` 재계산 → 그 path 에 multipart body 저장
- production 빌드 시 이 endpoint 제외 (build-time conditional 또는 NODE_ENV 가드)

## 메타 entity canonical schema

핵심 필드:

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | UUID v7 | PK |
| `upload_kind` | text | indexed |
| `owner_id` | UUID? | indexed, nullable — §5 에서 FK 도출 |
| `storage_path` | text | unique |
| `mime_type` | text | head() 결과로 채움 |
| `size_bytes` | bigint | head() 결과로 채움 |
| `status` | enum (`pending` / `complete` / `failed` / `expired`) | |
| `expires_at` | timestamptz? | retention_days > 0 시 |
| `metadata_schema_version` | int | `backend.md.file_upload.metadata_schema_version` |
| `metadata` | jsonb | canonical schema |
| `created_at`, `updated_at`, `completed_at?` | timestamptz | |

`metadata` jsonb canonical schema (v1):

```json
{
  "schema_version": 1,
  "original": {
    "path": "users/.../{file_id}.jpg",
    "size_bytes": 123456,
    "mime_type": "image/jpeg",
    "etag": "..."
  },
  "variants": {
    "thumb_64": {
      "path": "users/.../{file_id}_thumb_64.webp",
      "width": 64,
      "height": 64,
      "mime_type": "image/webp",
      "size_bytes": 1234,
      "status": "complete"
    }
  }
}
```

ORM 별 표현:
- **Prisma**: `metadata Json` + Zod 또는 type 어셈블
- **TypeORM**: `@Column('jsonb') metadata: UploadMetadata` (인터페이스)
- **Drizzle**: `jsonb('metadata').$type<UploadMetadata>()`
- **SQLAlchemy**: `Column(JSONB)` + Pydantic 모델 분리

## selected-storage.ts (정적 re-export 만)

```typescript
// vendor: "" 모드:
export { localAdapter as storage } from './local';

// vendor: "s3" 모드:
export { s3Adapter as storage } from './s3';
```

**이 파일은**:
- 정적 re-export 만 허용. vendor 이름 (`s3Adapter`, `s3` path) 등장 OK
- SDK import (예: `import S3Client from '@aws-sdk/client-s3'`) 금지 → critical
- 런타임 if/switch 분기 금지 → critical
- 동적 import 금지 → critical

## 리사이즈 worker — 두 패턴 모두 지원

`backend.md.file_upload.resize_worker_pattern`:

- **`central`** (default): 단일 worker `resize/processor.ts` + preset registry 조회. variant 인자 받음
- **`per-variant`**: variant 마다 `resize/{variant}.processor.ts`

validate-code §10.4 가 두 패턴 모두 통과.

## 출력 파일

경로는 `backend.md.structure` 와 framework convention 에서 derive:

- `{uploads_module_dir}/uploads.controller.ts` (또는 framework module 패턴)
- `{uploads_module_dir}/uploads.service.ts`
- `{uploads_module_dir}/uploads.module.ts` (NestJS 시)
- `{uploads_module_dir}/dto/*.dto.ts`
- `{uploads_module_dir}/{storage_subdir}/types.ts` — StorageAdapter 인터페이스
- `{uploads_module_dir}/{storage_subdir}/local.ts` — 항상 생성
- `{uploads_module_dir}/{storage_subdir}/{selected_storage_filename}` — 정적 re-export
- `{uploads_module_dir}/{storage_subdir}/{vendor}.ts` — vendor 명시 시 추가
- `{uploads_module_dir}/{resize_subdir}/processor.ts` — central 패턴 시
- `{uploads_module_dir}/{resize_subdir}/{variant}.processor.ts` — per-variant 패턴 시
- 마이그레이션 파일 (ORM 별)

## Vendor 어댑터 매트릭스

| vendor | first-class | 어댑터 파일 |
|---|---|---|
| `""` (local) | 항상 생성 | `storage/local.ts` |
| `s3` | first-class | `storage/s3.ts` |
| `gcs` | first-class | `storage/gcs.ts` |
| `r2` | first-class | `storage/r2.ts` |
| `minio` | first-class | `storage/minio.ts` |

vendor SDK 는 `storage/{vendor}.ts` 에서만 import. 그 외 파일에서 vendor SDK 직접 import 금지.

## 마이그레이션 시나리오

### Scenario A — 신규
TS §9 작성 → 전체 생성. 마이그레이션 실행.

### Scenario B — 기존 ad-hoc 업로드
1. `--dry-run` grep: `multer`, `formidable`, `S3Client`, `GoogleCloudStorage`, `Buffer.pipe`
2. codemod 후보 + 추정 upload_kind
3. 사용자 승인 후 통합. 기존 라이브러리 import 보존

### Scenario C — 기존 StorageService (impl-integrations 산출)
1. `service-registry.md` 에서 검출
2. 호환 시 wrapper 만 생성 (StorageAdapter 인터페이스 충족), 기존 service 보존
3. 비호환 시 사용자 confirm 후 wrapper 또는 신규 adapter

### Scenario D — vendor 전환
storage_vendor 변경 → `impl-file-upload --regenerate-storage` (어댑터만 재생성, controller/service/meta 보존)

## 품질 자가 점검

- [ ] TS §9 의 모든 upload_kind 가 controller 핸들러/operationId 에 등장
- [ ] complete handler 가 storage.head() 로 size/mime 재검증 (client size_bytes 신뢰 X)
- [ ] local passthrough 가 production 차단 + file_id 기반 server-side path 재계산
- [ ] selected-storage.ts 가 정적 re-export 만 (SDK import / 런타임 분기 금지)
- [ ] controller/service/DTO 에 vendor SDK import 0건 (storage/{vendor}.ts 만 허용)
- [ ] 메타 entity 에 필수 8필드 (id/upload_kind/storage_path/mime_type/size_bytes/status/metadata_schema_version/metadata) 존재
- [ ] metadata.original / variants canonical schema 적용
- [ ] resize_variants 가 있는 upload_kind 에서 complete handler 가 리사이즈 enqueue 호출
- [ ] callback_required 가 항상 true (Phase 1 — false 는 Phase 2)
