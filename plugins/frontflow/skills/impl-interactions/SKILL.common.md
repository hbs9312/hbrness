---
name: impl-interactions
description: 상태 관리, 조건부 렌더링, 애니메이션을 구현합니다. API 연결 없이 시뮬레이션. "인터랙션 구현", "상태 관리" 요청 시 사용.
argument-hint: [기능 명세 경로] [UI 명세서 경로] [기술 명세 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 인터랙션 + 상태 관리 (F5)

ultrathink

정적 페이지(F4)에 상태 관리, 조건부 렌더링, 애니메이션을 추가합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md) — state_management

## 입력

$ARGUMENTS 에서:
1. **기능 명세서(FS)** → 비즈니스 룰 (조건부 렌더링 근거)
2. **UI 명세서(UI)** → 인터랙션 & 애니메이션 섹션
3. **기술 명세서(TS)** → 상태 enum (프론트엔드 상태 모델링)

와이어프레임(WF)의 상태 매트릭스도 참조 (specs/ 에서 자동 탐색).

## ★ 아직 API 호출 없음 ★

상태 변화를 setTimeout, 목 함수 등으로 시뮬레이션합니다.

```typescript
// F5에서의 상태 시뮬레이션
const handleEnroll = async () => {
  setStatus('processing')
  // ★ 실제 API 대신 시뮬레이션
  await new Promise(resolve => setTimeout(resolve, 2000))
  setStatus('ready')
}
```

이렇게 해야 인터랙션 자체의 정확성을 격리 검증할 수 있습니다.

## 구현 항목

### 1. 상태 설계

TS의 상태 enum → 프론트엔드 상태 타입:

```typescript
// TS의 embedding_status를 그대로 사용
type EmbeddingStatus = 'pending' | 'processing' | 'ready' | 'failed'

// 페이지 수준 상태
type PageState = 'idle' | 'loading' | 'error' | 'empty'
```

frontend.md의 `state_management` 설정에 따라:
- zustand → store 파일 생성
- useState → 커스텀 훅으로 래핑
- tanstack-query → queryKey/queryFn 구조 준비 (F6에서 연결)

### 2. 조건부 렌더링

FS의 비즈니스 룰을 조건으로 변환:

```typescript
// BR-001: 최대 50명 → 카운터 50이면 등록 버튼 비활성
<AddButton disabled={speakers.length >= MAX_SPEAKERS} />

// BR-005: Admin/Member만 등록 가능
{hasPermission && <AddButton />}
```

### 3. 폼 핸들링

frontend.md의 `form` 설정에 따라:
- react-hook-form → useForm + validation schema
- 입력 검증: FS의 BR에서 도출 (이름 중복, 길이 제한 등)

### 4. 애니메이션

UI 명세서의 인터랙션 섹션에서 정확히 반영:

```css
/* CSS transition 우선 — 단순한 것 */
.card-enter { 
  animation: fadeIn 200ms ease-out; 
}

/* 복잡한 것만 framer-motion 등 라이브러리 */
```

- duration, easing을 UI 명세 수치 그대로 사용
- 성능: transform, opacity만 애니메이트 (layout thrashing 방지)

### 5. 화면 전환

WF의 화면 전환 맵에 따른 라우트 이동:
- 정방향: router.push
- 뒤로가기: router.back 또는 명시적 경로
- 모달/바텀시트: 상태 기반 열기/닫기

## 트래킹 hook (Phase 1 (4) 연계)

`frontflow:impl-tracking` 가 선언한 이벤트(`@/tracking` 의 `TrackEvent`) 를 적절한 위치에서 호출:

- mutation `onSuccess` 안: `track(TrackEvent.X, {...})`
- form submit 후: `track(...)` (검증 통과 + mutation 성공 후)
- effect 시점: `useEffect(() => track(TrackEvent.PAGE_VIEW, {...}), [])`
- **error 처리**: handler.ts (Phase 1 (1)) 는 순수 함수 — track 호출 금지.
  **단일 지점 원칙** (Phase 1 (4) XR-005): error_shown 은 한 곳에서만 호출.
  우선순위: presentError wrapper > inline form.setError 직전 (decision.uiFlow !== 'silent' 일 때) > mutation onError.
  중복 호출 금지. silent / 자동 retry 성공 케이스는 호출 X.

`impl-tracking [Phase B]` 가 codemod proposal 로 위치를 제안. 사용자 확인 후 적용.
`track` import 는 `@/tracking` (barrel) 에서.

## 품질 자가 점검

- [ ] WF 상태 매트릭스의 모든 상태를 코드에서 재현 가능한가
- [ ] FS의 모든 BR이 조건부 렌더링으로 구현되었는가
- [ ] 애니메이션 duration/easing이 UI 명세와 정확히 일치하는가
- [ ] 실제 API 호출 코드 = 0건 (시뮬레이션만)
- [ ] 폼 검증이 FS BR과 일치하는가
- [ ] 이벤트 트래킹 hook 이 적절한 위치에 호출됨 (impl-tracking proposal 결과)
- [ ] error_shown hook 이 handler.ts 외부에서 호출됨 (mutation onError / presentError)
