---
name: impl-pages
description: 컴포넌트를 조합하여 페이지를 조립합니다. 정적 구현 — API 호출 없음. "페이지 구현", "화면 조립" 요청 시 사용.
argument-hint: [와이어프레임 경로] [UI 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
model: sonnet
---

# 페이지 조립 — 정적 (F4)

ultrathink

F2/F3에서 만든 컴포넌트를 배치하여 페이지를 완성합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md) — page_dir, framework

## 입력

$ARGUMENTS 에서:
1. **와이어프레임(WF)** → 화면 전환 맵 (라우팅 설계)
2. **UI 명세서(UI)** → 반응형 규칙

F2/F3 컴포넌트가 프로젝트에 존재하는지 Glob으로 확인.

## ★ 정적 구현 원칙 ★

이 단계에서는 API를 호출하지 않습니다.

- 모든 데이터: 하드코딩된 목 데이터 (파일 상단 또는 별도 mock 파일)
- 모든 상태: 고정 (정상 상태로 렌더링)
- 목적: 레이아웃이 맞는지만 확인

```typescript
// ★ 이 단계의 페이지 모습
const MOCK_SPEAKERS: Speaker[] = [
  { speaker_id: 'spk_001', name: '김석', embedding_status: 'ready', ... },
  { speaker_id: 'spk_002', name: '이지은', embedding_status: 'processing', ... },
]

export default function SpeakerListPage() {
  return (
    <PageLayout title="화자 관리">
      <SpeakerCounter current={MOCK_SPEAKERS.length} max={50} />
      <SpeakerList speakers={MOCK_SPEAKERS} />
      <AddSpeakerButton />
    </PageLayout>
  )
}
```

## 라우팅

WF의 화면 전환 맵을 라우트 구조로 변환합니다.

framework별 분기:
- **Next.js App Router**: 디렉토리 구조로 라우팅
  ```
  app/settings/speakers/page.tsx       → 화자 목록
  app/settings/speakers/new/page.tsx   → 등록 플로우
  app/settings/speakers/layout.tsx     → 공통 레이아웃
  ```
- **React Router**: route 설정 파일 생성

## 페이지 레벨 레이아웃

- 헤더, 사이드바, 메인 영역 구성
- 반응형: UI 명세서의 브레이크포인트별 레이아웃 변화 적용
- 스크롤: 메인 영역만 스크롤, 헤더/사이드바 고정 (해당 시)

## 품질 자가 점검

- [ ] WF의 모든 화면에 대응하는 페이지 파일이 존재하는가
- [ ] F2/F3 컴포넌트를 import하여 사용하는가 (페이지에서 직접 스타일링 최소화)
- [ ] 라우팅이 WF 화면 전환 맵과 일치하는가
- [ ] 반응형: 모바일/데스크톱 양쪽에서 레이아웃이 성립하는가
- [ ] API 호출 코드 = 0건 (정적 목 데이터만)
