---
name: generate-stories
description: 컴포넌트에 대한 Storybook 스토리를 자동 생성합니다. "스토리 생성", "Storybook" 요청 시 사용.
argument-hint: [컴포넌트 파일 경로] [UI 명세서 경로 (선택)]
tools: [file:read, search:grep, search:glob, file:write]
effort: medium
---

# Storybook 스토리 생성 (FU3)

컴포넌트 파일을 읽고 UI 명세서의 상태 목록을 기반으로 스토리를 생성합니다.
F2/F3에서 자동 호출되지만, 독립 실행도 가능합니다.

## 입력

$ARGUMENTS 에서:
1. 컴포넌트 파일 경로 → Read (Props 타입 추출)
2. UI 명세서 경로 (선택) → 상태 목록 도출

UI 명세서가 없으면 Props 타입에서 상태를 추론합니다.

## 생성 규칙

### 파일 위치

frontend.md의 설정에 따라:
- co_location=true → 컴포넌트와 같은 디렉토리
- co_location=false → storybook_dir 하위

### 필수 스토리

```typescript
import type { Meta, StoryObj } from '@storybook/react'
import { {Component} } from './{Component}'

const meta: Meta<typeof {Component}> = {
  title: '{카테고리}/{Component}',
  component: {Component},
  tags: ['autodocs'],
  argTypes: {
    // Props에서 자동 도출
  },
}
export default meta
type Story = StoryObj<typeof {Component}>

// 1. 기본 상태 (필수)
export const Default: Story = {
  args: { /* 기본 props */ },
}

// 2. 모든 variant 조합 (해당 시)
export const AllVariants: Story = { ... }

// 3. 각 상태 (UI 명세서 기반)
export const Loading: Story = { ... }
export const Error: Story = { ... }
export const Disabled: Story = { ... }
export const Empty: Story = { ... }

// 4. 반응형 (필수)
export const Mobile: Story = {
  parameters: {
    viewport: { defaultViewport: 'mobile1' },
  },
  args: { /* 기본 props */ },
}

// 5. 경계 케이스 (해당 시)
export const LongText: Story = {
  args: { name: '매우 긴 이름이 들어갔을 때 말줄임 처리가 되는지 확인' },
}
```

### 목 데이터

TS API 응답 스키마를 기반으로 현실적인 목 데이터:
- 한국어 이름/텍스트 사용
- 날짜는 현실적인 값
- 각 상태별 데이터 변형

## 출력

생성된 .stories.tsx 파일을 Write로 저장합니다.
