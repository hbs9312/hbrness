# impl-scanner 스킬 생성 컨텍스트

> 이 문서는 skill-creator에게 전달하여 impl-scanner 스킬을 생성하기 위한 컨텍스트이다.

---

## 1. 스킬 목적

구현 프로젝트 디렉토리를 스캔하여 **기술 스택과 구조를 파악**하고, **현재 구현 상황을 분석**한 뒤, 정해진 중간 포맷으로 결과를 출력하는 스킬.

이 스킬은 특정 기술 스택(Python/React 등)에 종속되지 않고, 어떤 프로젝트든 적응적으로 분석할 수 있어야 한다.

이 스킬의 출력은 meeting-doc-gen 스킬이 소비하므로, 반드시 정해진 중간 포맷을 준수해야 한다.

---

## 2. 트리거 조건

- 사용자가 "구현 현황 파악", "프로젝트 상태 분석", "코드 스캔" 등을 요청할 때
- meeting-doc-gen 스킬이 내부적으로 호출할 때
- 기획 대비 구현 진행률을 확인하고 싶을 때

---

## 3. 입력

| 항목 | 필수 | 기본값 | 설명 |
|------|------|--------|------|
| project_paths | Y | - | 프로젝트 디렉토리 경로 리스트 (예: `["backend/", "frontend/"]`) |
| docs_path | N | - | 기획서 경로 (기획-구현 매핑 시 필요) |
| scope | N | "전체" | 분석 범위 (전체 / 특정 도메인) |
| output_path | N | `meeting-prep/` | 분석 결과 저장 경로 |

---

## 4. 처리 단계

### 4.1 프로젝트 식별 (적응형)

각 프로젝트 디렉토리에 대해 기술 스택을 자동으로 식별한다:

**식별 전략**:
1. **설정 파일 기반 식별**:
   - `package.json` → Node.js/JavaScript/TypeScript 프로젝트
   - `requirements.txt`, `pyproject.toml`, `setup.py` → Python 프로젝트
   - `go.mod` → Go 프로젝트
   - `Cargo.toml` → Rust 프로젝트
   - `build.gradle`, `pom.xml` → Java 프로젝트
   - `*.csproj`, `*.sln` → .NET 프로젝트

2. **프레임워크 식별**:
   - package.json의 dependencies에서: react, vue, angular, next, nuxt, svelte 등
   - Python에서: fastapi, django, flask, sqlalchemy, alembic 등
   - 기타: spring boot, express, gin 등

3. **프로젝트 구조 패턴 식별**:
   - MVC, MVVM, FSD, Clean Architecture, Hexagonal 등
   - src/, app/, lib/, internal/ 등 디렉토리 패턴
   - 테스트 디렉토리: tests/, __tests__/, spec/ 등

### 4.2 구현 현황 분석

**범용 분석 (모든 프로젝트)**:
1. **디렉토리 트리**: 주요 폴더/파일 구조 (node_modules, __pycache__ 등 제외)
2. **git log**: 최근 20개 커밋 요약 (가능 시)
3. **파일 통계**: 파일 유형별 개수, 최근 수정된 파일

**백엔드 프로젝트 특화 분석**:
1. **API 엔드포인트 목록**: 라우터/컨트롤러 파일에서 추출
2. **DB 모델/스키마**: 모델 파일에서 엔티티 목록 추출
3. **마이그레이션**: 최근 마이그레이션 내역
4. **테스트 커버리지**: 테스트 파일 존재 여부 및 대상 기능

**프론트엔드 프로젝트 특화 분석**:
1. **페이지/라우트 목록**: 라우터 설정 또는 pages/ 디렉토리
2. **컴포넌트 구조**: 주요 UI 컴포넌트 목록
3. **상태 관리**: store 파일들
4. **API 연동**: API 클라이언트/훅 파일

### 4.3 기획-구현 매핑 (docs_path 제공 시)

기획서 도메인과 구현 코드 간의 매핑을 시도한다:

**매핑 전략**:
1. **키워드 매칭**: 기획서 도메인명 ↔ 코드 파일/폴더명
   - 예: 기획 "chat" → backend `endpoints/chats.py`, `services/chat_service.py`, frontend `features/chat-room/`
2. **API 엔드포인트 매칭**: 기획서에 정의된 기능 → 실제 API endpoint 존재 여부
3. **모델 매칭**: 기획서에 언급된 데이터 → 실제 DB 모델 존재 여부

**매핑 결과 분류**:
- ✅ 구현 완료: 기획 기능에 대응하는 코드가 존재하고 완성된 것으로 보임
- 🔧 부분 구현: 코드가 존재하지만 빈 파일, TODO 주석, 스텁 등
- ❌ 미구현: 기획에는 있으나 코드에 대응하는 것이 없음
- ❓ 매핑 불확실: 자동 매핑이 어려워 수동 확인 필요

---

## 5. 출력 포맷 (중간 포맷)

반드시 아래 구조를 준수한다. meeting-doc-gen이 이 포맷을 파싱하여 사용한다.

```markdown
# 구현 현황 분석 결과

> 분석일: {YYYY-MM-DD}
> 분석 대상: {프로젝트 목록, 쉼표 구분}
> 기획서 경로: {docs 경로 또는 "미제공"}

---

## [{프로젝트명}] 개요

### 기술 스택
- 언어: {언어}
- 프레임워크: {프레임워크}
- 주요 라이브러리: {라이브러리 목록}
- 아키텍처 패턴: {식별된 패턴}

### 디렉토리 구조
```
{주요 디렉토리 트리, 3레벨 깊이}
```

### 주요 모듈 목록
| 모듈/기능 | 경로 | 파일 수 | 설명 |
|----------|------|---------|------|

---

## [{프로젝트명}] 구현 상태

### 구현 완료
| # | 기능 | 관련 파일 | 근거 |
|---|------|----------|------|
| IMPL-001 | {기능명} | `{파일 경로}` | {구현 완료로 판단한 근거} |

### 부분 구현 / 진행 중
| # | 기능 | 관련 파일 | 현재 상태 | 남은 작업 추정 |
|---|------|----------|----------|--------------|
| IMPL-002 | {기능명} | `{파일 경로}` | {현재 상태 설명} | {추정} |

### 미구현 (기획서 대비)
| # | 기획 기능 | 기획서 경로 | 비고 |
|---|----------|-----------|------|
| IMPL-003 | {기능명} | `{기획서 파일}` | {참고 사항} |

### 매핑 불확실
| # | 기획 기능 | 후보 파일 | 불확실 이유 |
|---|----------|----------|-----------|

---

## [{프로젝트명}] 최근 작업 동향

### 최근 커밋 (2주간)
| 날짜 | 커밋 메시지 | 영향 파일 수 |
|------|-----------|-------------|

### 최근 스키마 변경 (해당 시)
| 날짜 | 변경 내용 |
|------|----------|

### 작업 추세
- {최근 집중적으로 작업 중인 영역 요약}
- {다음에 작업할 것으로 예상되는 영역}

(프로젝트별 반복)

---

## 프로젝트 간 공통 사항
- {프로젝트 간 연동 이슈}
- {API 스키마 불일치 등}
```

---

## 6. 실제 프로젝트 참고 사례

### Backend (Python FastAPI)
```
backend/app/
├── api/v1/endpoints/   # 22개 엔드포인트 파일
├── models/             # 22개 SQLAlchemy 모델
├── repositories/       # 20개 리포지토리
├── schemas/            # 15개 Pydantic 스키마
├── services/           # 비즈니스 로직 (LLM, OAuth, Storage 등)
├── db/migrations/      # 40+ Alembic 마이그레이션
└── tests/              # 15개 테스트 파일
```
- 식별 포인트: `requirements.txt`, `app/main.py` (FastAPI app 인스턴스), `alembic.ini`
- API 목록: endpoints 폴더의 파일명 = 도메인 (auth, chats, studio, admin 등)
- 구현 상태: wallet.py, notifications.py가 빈 파일 → 미구현 힌트

### Frontend (React + TypeScript + Vite)
```
frontend/src/
├── app/                # 레이아웃, 프로바이더
├── entities/           # 도메인 엔티티 (chat, content, viewer)
├── features/           # 기능 단위 (chat-room, auth, admin, studio)
└── ...
```
- 식별 포인트: `package.json` (react, vite), `tsconfig.json`
- FSD 패턴: entities/ → features/ → pages/ 계층
- 구현 상태: features/ 폴더 목록 = 구현된 기능 영역

### 기획-구현 매핑 예시
| 기획 도메인 | Backend | Frontend |
|------------|---------|----------|
| chat | endpoints/chats.py, services/chat_service.py | features/chat-room/ |
| studio | endpoints/studio.py, services/content_service.py | features/studio/ (있다면) |
| admin | endpoints/admin.py | features/admin/ |
| wallet | endpoints/wallet.py (빈 파일) | ❌ |

---

## 7. 주의사항

1. **node_modules, __pycache__, dist, build 등 제외**: 스캔 시 빌드 산출물/의존성 폴더 무시
2. **빈 파일 탐지**: 빈 파일, TODO만 있는 파일은 "부분 구현"이 아니라 "미구현"에 가까움
3. **git 가용성**: git이 사용 가능하지 않을 수도 있음. 불가능하면 파일 수정 시간 등 대안 활용
4. **대규모 프로젝트**: 파일이 수백~수천 개인 경우, 주요 디렉토리 위주로 분석하고 상세는 scope로 제한
5. **민감 정보**: .env, credentials 등의 파일 내용은 읽지 않음. 존재 여부만 기록
6. **범용성**: 어떤 언어/프레임워크든 기본적인 구조 파악은 가능해야 함. 알 수 없는 기술 스택은 "식별 불가"로 표시
