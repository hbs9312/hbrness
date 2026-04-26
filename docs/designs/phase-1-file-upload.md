# Phase 1 (5) — 파일 업로드 Skill 설계

> **Generated**: 2026-04-27
> **Scope**: Phase 1 다섯 번째 항목 — `backflow:impl-file-upload` 신설 + `specflow:generate-ts` `§9 파일 처리` 부속섹션 의무화 + `backflow:validate-code` §10 drift 룰
> **Parent roadmap**: `docs/plugin-gaps-and-plan.md` §3.3 (5)
> **Companion designs**: phase-1-error-contract (1), phase-1-observability (2), phase-1-api-sync (3), phase-1-tracking (4)
>
> **Revision (2026-04-27, Task 0 codex review — 9 findings, 4 critical · 4 warning · 1 info)**:
> - **XR-001 (critical)**: `selected-storage.ts` drift 규칙 자기모순 해소 — SDK import / 직접 호출만 금지, 정적 `export { X as storage } from './Y'` 의 vendor 이름은 허용.
> - **XR-002 (critical)**: `impl-controllers` 와 `impl-integrations` 와의 책임 경계 명시 — impl-controllers 는 §9 의 upload operationId 를 **skip**, impl-integrations 의 StorageService 존재 시 **wrapper 우선** (재구현 금지).
> - **XR-003 (critical)**: local passthrough endpoint 보안 강화 — production 차단(`storage_vendor === '' && NODE_ENV !== 'production'` 만 등록), auth 강제, **query path 직접 사용 금지** — `file_id` 로 pending meta 조회해 server-side path 재계산.
> - **XR-004 (critical)**: `StorageAdapter.presignPut()` 인터페이스 확장 — `method` / `headers` / `fields` / `uploadMode: 'put' \| 'post' \| 'resumable'` 분기. complete 시 client `size_bytes` 신뢰 금지, `storage.head()` 로 server-side 재검증.
> - **XR-005 (warning)**: `callback_required=false` 모드는 **Phase 1 에서 금지**. Phase 2 에서 lazy head() polling 정책으로 도입.
> - **XR-006 (warning)**: `storage_path` placeholder grammar 명시 — reserved (`{file_id}`, `{ext}`, `{upload_kind}`) + custom (request body/path/auth-derived). 미해결 placeholder 는 generation-time critical.
> - **XR-007 (warning)**: 출력 path 가 `backend.md.structure.*` 에서 derive — NestJS module pattern 시 `uploads.module.ts` + DTO + 루트 모듈 등록까지 Writes 에 포함.
> - **XR-008 (warning)**: `metadata` jsonb canonical schema — `metadata.variants[variant] = { path, width, height, mime_type, size_bytes, status }`. ORM 별 표현 규칙 명시.
> - **XR-009 (info)**: 리사이즈 worker — variant 별 파일 또는 **central worker + preset registry** 둘 다 1급 패턴.

## 목표

Backend 에 **파일 업로드 표준 파이프** 도입 — presigned URL 발급 → 클라이언트 직접 업로드 → 완료 콜백 → server-side head() 재검증 → 메타 저장 → (옵션) 리사이즈 worker. 스토리지 벤더는 어댑터로 격리. impl-controllers / impl-integrations 와 책임 경계 명시.

### Non-goals

- Frontend 업로드 UI (드래그앤드롭, 진행률) — `frontflow:impl-composites` 가이드만
- 비디오 transcoding — Phase 2 (`backflow:impl-media-pipeline`)
- 청크 / resumable multipart upload (S3 multipart, GCS resumable 의 chunk-by-chunk) — `presignPut` 의 `uploadMode: 'resumable'` 만 노출, 실제 chunk 조립은 Phase 2
- CDN 배포 — Phase 2
- 파일 바이러스 스캔 — Phase 2 (`backflow:impl-file-scan`)
- 다중 스토리지 동시 송신 — Phase 2
- 파일 권한 매트릭스(ACL) — `impl-middleware` 인가 책임. 본 skill 은 메타에 owner_id 만
- `callback_required=false` lazy head polling — Phase 2

## 1. TS 포맷 변경 — `§9 파일 처리` 부속섹션 의무화

### 섹션 포맷

```markdown
# 9. 파일 처리

| upload_kind | mime_types | max_size_mb | storage_path | resize_variants | retention_days | related |
|---|---|---|---|---|---|---|
| profile_image | image/jpeg, image/png, image/webp | 5 | users/{user_id}/profile/{file_id}.{ext} | thumb_64, thumb_256 | 0 | US-002, AC-005 |
| document_attachment | application/pdf | 50 | docs/{doc_id}/{file_id}.pdf | (없음) | 365 | US-007 |
| audio_sample | audio/wav, audio/mpeg | 20 | speakers/{speaker_id}/samples/{file_id}.{ext} | (없음) | 90 | AC-009 |
```

### 섹션 규약

| 필드 | 필수 | 규칙 |
|---|---|---|
| `upload_kind` | required | snake_case 전역 유일. operationId prefix |
| `mime_types` | required | comma 구분 IANA MIME. wildcard 금지 |
| `max_size_mb` | required | 양의 정수 |
| `storage_path` | required | placeholder 사용. **placeholder grammar (XR-006)**: reserved (`{file_id}`, `{ext}`, `{upload_kind}`) 는 server 자동 채움. 그 외 (`{user_id}`, `{doc_id}` 등) 는 **custom placeholder** — 반드시 다음 중 한 곳에서 resolve 가능해야 함: ① presign 요청 body, ② 인증된 user (auth context), ③ url path param. 미해결 placeholder 검출 시 generation-time critical |
| `resize_variants` | optional | comma 구분 variant 이름. `backend.md.file_upload.resize_presets` 에 정의된 키만. "(없음)" 빈 값 허용 |
| `retention_days` | required | ≥ 0 정수. 0 = 영구. > 0 시 메타에 `expires_at` 채움 (cron 정리는 Phase 2) |
| `related` | optional | US/AC/BR |

### `specflow:generate-ts` 변경

- 프롬프트: "§9 파일 처리 — PRD 의 '업로드', '첨부', '이미지', '파일' 흡수"
- 자가 점검:
  - "§9 모든 행 mime_types · max_size_mb · storage_path · retention_days 필수"
  - "storage_path placeholder 가 reserved 또는 명시적 source 에서 resolve 가능"
  - "resize_variants 가 backend.md.file_upload.resize_presets 키와 매칭"
  - "upload_kind 마다 §3.2 OpenAPI fragment 에 `upload{UploadKindCamel}` operationId 존재"

### ts-rules 신규 룰 (warning grace)

```markdown
## 파일 처리 (warning — v1.x grace)
50. §9 섹션 존재 — 누락 시 warning + skill default 단일 `generic_file`
51. upload_kind snake_case + 전역 유일 — 위반 시 warning
52. mime_types wildcard (`*/*` 또는 `image/*`) — warning
53. max_size_mb 정수 + > 0 — 위반 시 warning
54. storage_path 에 `{file_id}` 포함 — 누락 시 warning ("충돌 위험")
55. retention_days 정수 + ≥ 0 — 위반 시 warning
56. resize_variants 가 backend.md.file_upload.resize_presets 키 — 미정의 시 warning
57. §9 의 upload_kind 마다 §3.2 fragment 에 `upload{Kind}` operationId — 누락 시 warning
```

## 2. `backflow:impl-file-upload` 스킬 계약

### 카드

| 항목 | 내용 |
|---|---|
| **Purpose** | TS §9 → presigned URL controller + 완료 콜백 (server-side head 재검증) + 메타 entity + (옵션) 리사이즈 worker + 스토리지 어댑터 (벤더 격리) |
| **Reads (specflow)** | `specs/TS/*` §9 (필수), §3.2 (operationId 검증), §4 (FILE_TOO_LARGE / MIME_NOT_ALLOWED / STORAGE_UNAVAILABLE / FILE_NOT_FOUND / FILE_INTEGRITY_MISMATCH 자동 추가 권고), §5 (메타 entity 의 owner FK) |
| **Reads (registry/config)** | `.backflow/task-file-map.md`(있으면), `.backflow/service-registry.md` (XR-002: 기존 StorageService 검출), `backend.md` (`file_upload.*` 신설, `structure.*` derive, `framework.*`, `database.orm`, `external_services.storage`) |
| **Writes** | controller / service / module(Nest) / DTO / meta entity / migration / storage adapter dir / resize worker (variant 별 또는 central) — 정확한 path 는 `backend.md.structure` 와 framework convention 에서 derive (XR-007). 항상 생성: `storage/types.ts`, `storage/local.ts`, `storage/selected-storage.ts`. vendor 명시 시 `storage/{vendor}.ts` 추가 |
| **Storage Tier** | N/A — project code |
| **Depends on** | `map-tasks`, `impl-schema`, `impl-error-codes`, `impl-services` 후. `impl-controllers` / `impl-integrations` 와 **책임 경계 (XR-002)**: 아래 §2.1 참조 |
| **Notes** | 벤더-중립 영역: controller / service / storage/types.ts / storage/local.ts / selected-storage.ts. 예외: `storage/{vendor}.ts` 의 SDK 사용 가능, `selected-storage.ts` 는 정적 re-export 의 vendor 이름은 허용 (XR-001 — SDK import / 직접 호출만 금지). callback_required 는 **항상 true** (Phase 1) |

### 2.1 선행 skill 책임 경계 (XR-002)

#### `impl-controllers` 와의 경계

- TS §9 의 upload_kind 마다 `upload{UploadKindCamel}` operationId 가 §3.2 fragment 에 존재
- `impl-controllers` 는 이 operationId 들을 **skip** (또는 stub 만 — 본문은 비워둠)
- 본 skill 이 그 자리에 실제 controller 핸들러 작성. 또는 별도 module/controller 생성 (NestJS module pattern 시 권장)
- `impl-controllers` SKILL prompt 갱신 (Task C 의 사촌 — 본 design 은 Task C 없으므로 backflow CONTRACTS.md 의 impl-controllers 카드 Notes 에 추가): "TS §9 upload operationId 는 impl-file-upload 가 처리 — 본 skill 은 stub/skip"

#### `impl-integrations` 와의 경계

- `external_services.storage` 가 명시된 프로젝트에서 `impl-integrations` 가 이미 `StorageService` 또는 `S3Service` 같은 추상을 만들었을 수 있음
- `.backflow/service-registry.md` 에서 그 존재를 검출하면:
  - **호환 시**: 본 skill 의 storage adapter 가 기존 service 를 wrapping (`storage/types.ts` 의 인터페이스를 충족하는 어댑터를 기존 service 위에 작성)
  - **비호환 시**: 사용자 confirm 후 wrapper 또는 신규 adapter 작성. 기존 service 는 보존 (직접 삭제 금지)
- `impl-integrations` SKILL prompt 갱신: "storage 추상은 impl-file-upload 의 StorageAdapter 인터페이스 충족 권고. 충족 시 impl-file-upload 가 wrapping"

### 2.2 실행 위치

```
impl-schema → impl-repositories → impl-error-codes → impl-observability
       │
       ▼
   impl-services → impl-controllers (upload operationId skip) → impl-middleware → impl-integrations
       │
       ▼
   impl-file-upload   ★ Phase 1 (5)
       │
       ▼
   export-api-contract   (file-upload controller 흡수)
       │
       ▼
   generate-tests
```

### 2.3 `backend.md` 신규 키

```yaml
file_upload:
  storage_vendor: ""              # "" (local only) | s3 | gcs | r2 | minio
  storage_bucket_env: "STORAGE_BUCKET"
  storage_endpoint_env: "STORAGE_ENDPOINT"
  storage_region_env: "STORAGE_REGION"
  storage_local_root_env: "STORAGE_LOCAL_ROOT"   # local adapter 만
  presigned_ttl_sec: 900          # 15분
  meta_table: "upload_meta"
  # path/file: structure.* + framework convention 에서 derive (XR-007)
  uploads_module_dir: "src/uploads"  # 기본값. NestJS 면 module/controller/service/dto 모두 이 안
  storage_subdir: "storage"          # uploads_module_dir 하위
  resize_subdir: "resize"
  selected_storage_filename: "selected-storage.ts"
  resize_worker_pattern: "central"   # central | per-variant (XR-009)
  resize_presets:
    thumb_64: { width: 64, height: 64, fit: "cover", format: "webp", quality: 80 }
    thumb_256: { width: 256, height: 256, fit: "cover", format: "webp", quality: 85 }
    card_512: { width: 512, height: 512, fit: "contain", format: "webp", quality: 85 }
  file_id_strategy: "uuid_v7"     # uuid_v4 | uuid_v7
  callback_required: true         # Phase 1: 항상 true 강제 (false 는 Phase 2)
  scan_on_complete: false         # Phase 2 hook
  metadata_schema_version: 1      # XR-008
```

### 2.4 StorageAdapter 인터페이스 (XR-004 확장)

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
  // server-side enforcement metadata (vendor 가 강제 가능한 한)
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

### 2.5 Controller 동작 (XR-003, XR-004 강화)

#### `POST /uploads/presign`

- body: `{ upload_kind, mime_type, size_bytes, ...customPlaceholderValues }`
- 검증:
  1. `upload_kind` 가 TS §9 에 존재
  2. `mime_type` 이 §9.mime_types 에 매칭
  3. `size_bytes` ≤ §9.max_size_mb * 1024 * 1024
  4. custom placeholder (예: `doc_id`) 들이 모두 제공되고 owner 권한 검증 (impl-middleware 가드 적용)
  5. server 가 `file_id` 발급 (uuid_v7) + `storage_path` resolve
- 메타 행 `status: pending` 생성
- 어댑터 `presignPut` 호출 → 결과 그대로 반환 (uploadMode/method/headers/fields 포함)
- 응답: `{ file_id, meta_id, upload: PresignPutResult, storage_path }`

#### `POST /uploads/{file_id}/complete`

- body: `{ etag? }` — **client 의 size_bytes / mime_type 을 신뢰하지 않음** (XR-004)
- server-side 검증:
  1. meta 행 조회 (`status: pending` 인지)
  2. **`storage.head(storage_path)` 호출** — 실제 size / contentType / etag 확인
  3. head 결과 `sizeBytes` 가 §9.max_size_mb 초과 또는 contentType 가 §9.mime_types 와 다르면 → `FILE_INTEGRITY_MISMATCH` 에러 + meta `status: failed` + storage.delete
  4. OK 시 meta `status: complete` + `completed_at` + `metadata.original = { path, size_bytes, mime_type }`
  5. variants 가 있으면 리사이즈 job enqueue (메타 `metadata.variants[variant] = { status: pending }`)
- 응답: `{ file_id, status: 'complete', urls: { original, ...(완료된 variants) } }`

#### `GET /uploads/{file_id}` — meta 조회 (presignGet 으로 download URL 생성). owner 권한은 middleware

#### `DELETE /uploads/{file_id}` — soft delete (meta `status: expired`) + `storage.delete()` 호출

#### Local passthrough (XR-003 제한)

- `storage_vendor === ''` **AND** `NODE_ENV !== 'production'` 시에만 route 등록
- endpoint: `POST /uploads/local-passthrough/{file_id}` — query path 사용 금지
- 동작: `file_id` 로 pending meta 조회 → server-side 에서 `storage_path` 재계산 → 그 path 에 multipart body 저장
- production 빌드 시 이 endpoint 자체가 컴파일 시 제외 (build-time conditional 또는 NODE_ENV 가드 — framework 별로 다름)

### 2.6 메타 entity canonical schema (XR-008)

핵심 필드:

| 필드 | 타입 | 비고 |
|---|---|---|
| `id` | UUID v7 | PK |
| `upload_kind` | text | indexed |
| `owner_id` | UUID? | indexed, nullable |
| `storage_path` | text | unique |
| `mime_type` | text | head() 결과로 채움 |
| `size_bytes` | bigint | head() 결과로 채움 |
| `status` | enum (`pending` / `complete` / `failed` / `expired`) | |
| `expires_at` | timestamptz? | retention_days > 0 시 |
| `metadata_schema_version` | int | 현재 1 (`backend.md.file_upload.metadata_schema_version`) |
| `metadata` | jsonb | canonical schema 아래 |
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

### 2.7 리사이즈 worker — 두 패턴 모두 지원 (XR-009)

`backend.md.file_upload.resize_worker_pattern`:

- **`central`** (default): 단일 worker `resize/processor.ts` (또는 framework 별) + preset registry 조회. variant 인자 받음
- **`per-variant`**: variant 마다 `resize/{variant}.processor.ts`

validate-code §10.4 가 두 패턴 모두 통과.

### 2.8 selected-storage.ts (XR-001 명료화)

```typescript
// vendor: "" 모드:
export { localAdapter as storage } from './local';

// vendor: "s3" 모드:
export { s3Adapter as storage } from './s3';
```

**이 파일은**:
- 정적 re-export 만 허용
- vendor 이름 (`s3Adapter`, `s3` path) 등장 OK
- SDK import (예: `import S3Client from '@aws-sdk/client-s3'`) 금지 → critical
- 런타임 if/switch 분기 금지 → critical
- 동적 import 금지 → critical

## 3. 동기화 메커니즘

```
TS §9 (source of truth)
TS §3.2 (operationId 검증)
TS §4 (FILE_* 권고)
       │
       ▼
   impl-file-upload
       │
       ▼
   controller + service + module + DTO + meta entity + storage adapters + resize worker
       │
       ▼
   export-api-contract (controller 흡수)
       │
       ▼
   sync-api-client (frontend 자동 클라이언트 + types)
       │
       ▼
   validate-code §10
```

### 기각한 대안

| 대안 | 기각 이유 |
|---|---|
| **(a) Server-side passthrough only** | 대용량 시 backend bandwidth 부담 |
| **(b) 청크 / resumable 본격 구현** | 복잡도 ↑. presignPut 의 mode 만 노출, chunk 조립은 Phase 2 |
| **(c) Vendor SDK 직접 호출** | 어댑터 패턴 표준 |
| **(d) 단일 generic upload (kind 무관)** | mime/size 제약 강제 못 함 |
| **(e) Client size_bytes / mime 신뢰** | 보안 위반. server head() 재검증 표준 (XR-004) |
| **(f) callback_required=false (Phase 1)** | pending 누적 + 상태 불일치. Phase 2 lazy head polling |
| **(g) Storage path query 직접 노출** | path traversal 위험 (XR-003) |

## 4. validate-code §10 drift 룰 (4 sub-rule)

```yaml
입력:
  ts_section: specs/TS-*.md §9 파일 처리
  service_registry: .backflow/service-registry.md
  uploads_dir: backend.md.file_upload.uploads_module_dir
  storage_dir: backend.md.file_upload.uploads_module_dir + "/" + storage_subdir
  selected_storage_file: storage_dir + "/" + backend.md.file_upload.selected_storage_filename
  vendor: backend.md.file_upload.storage_vendor
  resize_dir: uploads_dir + "/" + backend.md.file_upload.resize_subdir
  resize_presets: backend.md.file_upload.resize_presets
  metadata_schema_version: backend.md.file_upload.metadata_schema_version

§10.1 — TS §9 ↔ controller/service 일관성:
  upload_kind_in_controller:
    - TS §9 의 모든 upload_kind 가 controller 의 핸들러 분기/디렉토리/operationId 에 등장 → 누락 시 critical
  mime_validation:
    - controller / service / DTO 의 mime_type 검증 (allowedMimes / @IsIn / 데코레이터 / zod) 가 §9 의 mime_types 와 1:1 → 불일치 시 critical
  max_size_validation:
    - server 측 size 검증이 §9.max_size_mb * 1024 * 1024 와 일치 → 불일치 시 critical
  server_side_head_recheck:
    - complete handler 가 storage.head() 또는 동등한 호출로 size/mime 재검증 → 누락 시 critical (XR-004)
    - client 의 size_bytes / mime_type 만 사용해 status: complete 전이하는 코드 → critical
  storage_path_resolution:
    - storage_path 의 모든 placeholder 가 reserved (file_id/ext/upload_kind) 또는 명시된 source 에서 resolve → 미해결 시 critical (XR-006)
  related_error_codes:
    - TS §4 에 FILE_TOO_LARGE / MIME_NOT_ALLOWED / STORAGE_UNAVAILABLE / FILE_INTEGRITY_MISMATCH / FILE_NOT_FOUND 부재 → warning ("권고 추가")

§10.2 — Vendor 식별자 영역 검사:
  vendor_identifier_in_uploads:
    - controller / service / module / DTO / storage/types.ts / storage/local.ts 에
      vendor SDK import (`@aws-sdk/`, `@google-cloud/storage`, `aws-sdk`, `Minio`) 또는 vendor 직접 호출 등장 → critical
  selected_storage_static_export_only:
    - selected-storage.ts 가 단일 `export { X as storage } from './Y'` 외 형태 (런타임 if/switch / 다중 import / 동적 import / SDK direct import) → critical (XR-001)
    - vendor != "" 이면 X 가 vendor adapter 의 export 와 일치 → 불일치 시 critical
    - vendor == "" 이면 X 가 localAdapter → 불일치 시 critical
    - **selected-storage.ts 자체의 vendor 이름 (s3Adapter, gcsAdapter 등) 은 허용** — re-export 만 검사 (XR-001)
  storage_directory_exempt:
    - storage/{vendor}.ts 는 vendor 식별자 검사 제외 + info
  local_passthrough_guard:
    - storage_vendor != "" 일 때 local-passthrough route 가 등록되어 있으면 → critical (production 노출 위험)
    - storage_vendor == "" + NODE_ENV !== 'production' 가드가 없으면 → critical
    - local passthrough 가 query path 를 직접 사용 (file_id 기반 server-side 재계산 미사용) → critical (XR-003)

§10.3 — 메타 entity 일관성:
  meta_required_fields:
    - id / upload_kind / storage_path / mime_type / size_bytes / status / metadata_schema_version / metadata 모두 존재 → 누락 시 critical
  status_enum_match:
    - status enum 이 [pending, complete, failed, expired] → 추가/누락 시 warning
  retention_handling:
    - §9.retention_days > 0 인 upload_kind 가 있는데 expires_at 부재 → warning
  metadata_schema_version_field:
    - metadata 에 schema_version: 1 (또는 entity 별도 컬럼) 부재 → warning (XR-008)
  metadata_canonical_shape:
    - metadata.original = { path, size_bytes, mime_type } 패턴이 service 코드에서 사용 → 미사용 시 warning
    - variants 가 있는 upload_kind 의 metadata.variants[variant] = { path, width, height, mime_type, size_bytes, status } → 미사용 시 warning

§10.4 — 리사이즈 일관성 (central / per-variant 둘 다 지원):
  resize_handler_present:
    - §9 의 모든 resize_variants 에 대해:
      - resize_worker_pattern: per-variant 시 — resize/{variant}.processor.ts 존재 → 누락 시 warning
      - resize_worker_pattern: central 시 — central worker 의 preset key dispatch 분기에 variant 등장 → 누락 시 warning
  preset_lookup:
    - resize 코드에서 backend.md.file_upload.resize_presets 미정의 키 사용 → critical
  preset_consistency:
    - §9 의 모든 resize_variants 가 resize_presets 에 정의 → 누락 시 warning ("preset 추가 권고")
  enqueue_on_complete:
    - complete handler 가 variants 가 있는 upload_kind 에서 리사이즈 enqueue 호출 → 누락 시 warning

§10.5 — 선행 skill 책임 경계 (XR-002):
  controller_no_duplication:
    - impl-controllers 가 생성한 controller 에서 §9 의 upload operationId 가 stub/skip 이 아닌 본문 구현 → warning ("impl-file-upload 가 처리하므로 stub")
  storage_service_wrapper:
    - service-registry 에 StorageService 가 있는데 impl-file-upload 가 새 storage adapter 를 wrapping 없이 작성 → warning ("기존 service wrapper 권고")

예외:
  - TS §9 부재 (grace) + impl-file-upload 가 default `generic_file` 만 → §10 검사 skip + warning
  - vendor: "" + NODE_ENV: "production" 빌드 → local-passthrough route 부재가 정상 (위 critical 룰 통과)
  - external_services.storage 미정의 → impl-file-upload 가 local 만 + info
```

## 5. 마이그레이션

### 5.1 Scenario A — 신규
TS §9 작성 → 전체 생성. 마이그레이션 실행

### 5.2 Scenario B — 기존 ad-hoc 업로드
1. `--dry-run` grep: `multer`, `formidable`, `S3Client`, `GoogleCloudStorage`, `Buffer.pipe`
2. codemod 후보 + 추정 upload_kind
3. 사용자 승인 후 통합. 기존 라이브러리 import 는 보존

### 5.3 Scenario C — 기존 StorageService (impl-integrations 산출)
1. `service-registry.md` 에서 검출
2. 호환 시 wrapper 만 생성 (StorageAdapter 인터페이스 충족), 기존 service 보존
3. 비호환 시 사용자 confirm 후 wrapper 또는 신규 adapter

### 5.4 Scenario D — vendor 전환
storage_vendor 변경 → `impl-file-upload --regenerate-storage` (어댑터만 재생성, controller/service/meta 보존)

## 6. CONTRACTS.md 갱신

- `plugins/backflow/CONTRACTS.md`
  - 실행 순서: `impl-integrations` → **`impl-file-upload`** → `export-api-contract` → `generate-tests`
  - 스킬 카드 신설 (책임 경계 명시 — impl-controllers / impl-integrations 와의 관계)
  - 공통 레지스트리: `backend.md.file_upload.*`
  - specflow 역매핑: `TS §9 → impl-file-upload`, `TS §3.2 → impl-file-upload (operationId 검증)`, `TS §4 → impl-file-upload (FILE_* 권고)`, `TS §5 → impl-file-upload (owner FK)`
  - **impl-controllers 카드 Notes**: "TS §9 upload operationId 는 impl-file-upload 가 처리 — 본 skill 은 stub/skip"
  - **impl-integrations 카드 Notes**: "storage 추상은 impl-file-upload StorageAdapter 충족 권고"
- `plugins/specflow/skills/generate-ts/SKILL.common.md` — §9 추가 + 자가 점검 4항목
- `plugins/specflow/skills/generate-ts/template.md` — §9 섹션
- `plugins/specflow/skills/validate/rules/ts-rules.md` — 룰 50~57

## 7. Future work

- Phase 1 의 callback_required=false 모드 (lazy head polling) — Phase 2
- Cron retention 만료 처리 — Phase 2
- 청크 / resumable 본격 구현 (multipart, chunk 조립) — Phase 2
- 바이러스 스캔 hook — Phase 2
- Video transcoding — Phase 2
- CDN 배포 — Phase 2
- Multi-storage 동시 송신 — Phase 2
- Signed download URL 표준화 — Phase 2 (presignGet 이미 노출)
- Presign 사전 인가 정책 매트릭스 — Phase 2

## 8. 완료 기준 (Definition of Done)

### "ship"

- [ ] `specflow:generate-ts` §9 출력
- [ ] ts-rules 50~57
- [ ] `backflow:impl-file-upload` controller/service/module/DTO/meta/migration/storage(types+local+selected-storage) + (variants 시) resize 생성. 경로는 backend.md.structure 에서 derive
- [ ] `backend.md.file_upload.*` 신규 키
- [ ] StorageAdapter 인터페이스 — uploadMode/method/headers/fields 명시 (XR-004)
- [ ] complete 핸들러가 storage.head() 로 size/mime 재검증
- [ ] local passthrough 가 production 차단 + file_id 기반 path 재계산 (XR-003)
- [ ] selected-storage.ts 정적 re-export 만 (XR-001)
- [ ] backflow:validate-code §10 5 sub-rule (10.1~10.5)
- [ ] CONTRACTS 갱신 (impl-controllers / impl-integrations Notes 포함)
- [ ] 1개 실프로젝트 E2E (presign → upload → complete head 재검증 → variant 1개 리사이즈)

### "stable"

- 2개 이상 프로젝트 실사용
- vendor adapter 최소 2종 (s3 + gcs) 검증
- ts-rules / §10 grace → critical 승격
- Scenario A/B/C/D 마이그레이션 각각 1회

## 9. 다음 작업

1. **Task A** — `specflow:generate-ts` SKILL + template + ts-rules 50~57
2. **Task B** — `backflow:impl-file-upload` skill + `backend.md.file_upload` + `backflow/CONTRACTS.md` (impl-controllers / impl-integrations Notes 포함)
3. **Task D** — `backflow:validate-code` §10 (5 sub-rule)

Phase 1 (5) 전체 3 commit, 1주 소요.
