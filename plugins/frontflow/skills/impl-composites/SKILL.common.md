---
name: impl-composites
description: 원자 컴포넌트를 조합하여 복합 컴포넌트를 구현합니다. "복합 컴포넌트", "카드 컴포넌트", "패널 구현" 요청 시 사용.
argument-hint: [UI 명세서 경로] [컴포넌트명 (선택)]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 복합 컴포넌트 조립 (F3)

ultrathink

원자 컴포넌트(F2)를 조합하여 비즈니스 도메인에 결합된 복합 컴포넌트를 만듭니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md)

## 입력

$ARGUMENTS 의 UI 명세서 → Read.
F2에서 생성한 원자 컴포넌트가 프로젝트에 존재하는지 확인.

## 복합 컴포넌트 판별 기준

- 원자 컴포넌트를 조합하여 만든 것
- 비즈니스 도메인과 결합됨
- 예: SpeakerCard = StatusIcon + 이름 + 상태텍스트 + MoreButton
      RecordingPanel = 가이드문장 + AudioWaveform + RecordingTimer + Button

## ★ 데이터 타입 연결 ★

specflow 기술 명세서(TS)의 API 응답 스키마를 기반으로 Props 타입을 설계합니다.

```typescript
// TS의 GET /speakers 응답 기반
interface Speaker {
  speaker_id: string
  name: string
  embedding_status: 'pending' | 'processing' | 'ready' | 'failed'
  created_at: string
  updated_at: string
}

// SpeakerCard의 props는 Speaker 타입에서 파생
interface SpeakerCardProps {
  speaker: Speaker
  onEdit?: (id: string) => void
  onDelete?: (id: string) => void
}
```

이 단계에서는 타입만 정의합니다. 실제 API 호출은 F6에서.

## ★ 레이아웃 정밀도 ★

Figma MCP 데이터가 있으면 Auto Layout 속성을 정확히 반영합니다:

- `layoutMode` → flex-direction
- `itemSpacing` → gap
- `paddingTop/Right/Bottom/Left` → padding
- `primaryAxisAlignItems` → justify-content
- `counterAxisAlignItems` → align-items
- `layoutSizingHorizontal/Vertical` → width/height (fixed/auto/100%)

Figma 데이터가 없으면 UI 명세서의 컴포넌트 구성을 최대한 따릅니다.

## Storybook 스토리

목 데이터로 모든 상태 재현:

```typescript
const mockSpeakerReady: Speaker = {
  speaker_id: 'spk_001',
  name: '김석',
  embedding_status: 'ready',
  created_at: '2026-04-01T00:00:00Z',
  updated_at: '2026-04-01T00:00:05Z',
}

export const Ready: Story = { args: { speaker: mockSpeakerReady } }
export const Processing: Story = { args: { speaker: { ...mockSpeakerReady, embedding_status: 'processing' } } }
export const Failed: Story = { args: { speaker: { ...mockSpeakerReady, embedding_status: 'failed' } } }

// 리스트 컴포넌트면 경계 케이스도
export const EmptyList: Story = { args: { speakers: [] } }
export const SingleItem: Story = { args: { speakers: [mockSpeakerReady] } }
export const FullList: Story = { args: { speakers: Array(50).fill(mockSpeakerReady) } }
```

## 품질 자가 점검

- [ ] F2 원자 컴포넌트를 import하여 사용하는가 (HTML 직접 사용 최소화)
- [ ] Props 타입이 TS API 응답 스키마와 정합하는가
- [ ] 레이아웃 방향, gap, padding이 Figma/UI 명세와 일치하는가
- [ ] Storybook에 모든 상태(ready/processing/failed/empty/full)가 있는가
- [ ] 하드코딩 값 = 0건
