---
name: impl-atoms
description: UI 명세서의 원자 컴포넌트를 구현하고 Storybook 스토리를 생성합니다. "원자 컴포넌트", "기본 컴포넌트 구현" 요청 시 사용.
argument-hint: [UI 명세서 경로] [컴포넌트명 (선택)]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 원자 컴포넌트 구현 (F2)

ultrathink

당신은 프론트엔드 개발자입니다.
UI 명세서의 원자 컴포넌트를 구현하고 Storybook 스토리를 함께 생성합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md)
- 기존 컴포넌트 레지스트리: specs/ 또는 프로젝트 내 `component-registry.md` (있으면)

## 입력

$ARGUMENTS 에서:
1. **UI 명세서** 경로 → Read (컴포넌트 명세 섹션)
2. **컴포넌트명** (선택) → 특정 컴포넌트만 구현. 미지정 시 모든 원자 컴포넌트.

추가로 자동 탐색:
- frontend.md의 `design_system_package` → 기존 컴포넌트 확인
- frontend.md의 `component_dir` → 이미 만들어진 것 확인

## ★ 원자 컴포넌트 판별 기준 ★

다른 프로젝트 컴포넌트를 import하지 않는 것.
HTML 요소 + 토큰 스타일링으로만 구성.
예: StatusIcon, AudioWaveform, RecordingTimer, Badge

## ★ 재사용 판단 — 가장 먼저 실행 ★

1. 기존 컴포넌트 레지스트리 확인 (FU1 산출물 또는 직접 스캔)
2. 디자인 시스템 패키지 확인 (frontend.md `design_system_package`)

판단:
- **동일 컴포넌트 존재** → 새로 만들지 않음. "이미 존재: {경로}" 리포트
- **유사하지만 변형 필요** → 기존을 감싸는 wrapper 컴포넌트
- **완전히 새로운 것** → 신규 생성

## 구현 순서 (여러 컴포넌트 생성 시)

1. 의존성 없는 것부터 (StatusIcon, Badge 등 순수 표시형)
2. 기능적 의존이 있는 것 (AudioWaveform 등)

## 컴포넌트 생성 규칙

### 파일 구조

frontend.md의 `structure` 설정을 따름:

```
{component_dir}/{ComponentName}/
├── {ComponentName}.tsx          # 컴포넌트 본체
├── {ComponentName}.stories.tsx  # Storybook 스토리
├── {ComponentName}.test.tsx     # 단위 테스트 (해당 시)
└── index.ts                     # barrel export (설정에 따라)
```

### 컴포넌트 코드

- frontend.md의 `component_pattern` 템플릿을 따름
- Props 인터페이스를 먼저 정의하고, 확장 가능하게 설계
- `className` prop을 항상 포함 (외부 스타일 오버라이드)
- `...rest` props 전달 (HTML 기본 속성 지원)
- `any` 타입 사용 금지

### 스타일링

- F1에서 설정한 토큰만 사용
- 하드코딩 값(#hex, Npx) 절대 금지
- frontend.md의 styling 방식에 따라:
  - tailwind → 유틸리티 클래스, 동적 값은 cva 또는 clsx
  - css-modules → .module.css 파일, CSS 변수 참조
  - styled-components → 토큰 theme 참조

### Storybook 스토리 (필수)

UI 명세서의 컴포넌트 상태 목록에서 도출:

```typescript
// 필수 스토리 목록
export const Default: Story = { ... }         // 기본 상태
export const AllVariants: Story = { ... }     // variant/size 조합 (해당 시)
export const Disabled: Story = { ... }        // 비활성 상태
export const Loading: Story = { ... }         // 로딩 (해당 시)
export const Error: Story = { ... }           // 에러 (해당 시)
export const Mobile: Story = {                // 반응형
  parameters: { viewport: { defaultViewport: 'mobile1' } }
}
```

각 스토리에 `args` 명시, `argTypes`로 컨트롤 패널 구성.

## 품질 자가 점검

- [ ] UI 명세서의 모든 상태가 Storybook 스토리로 존재하는가
- [ ] 기존 컴포넌트를 재구현하지 않았는가
- [ ] 하드코딩 값 = 0건 (모든 시각 속성이 토큰 경유)
- [ ] Props 인터페이스가 확장 가능한가 (className, ...rest)
- [ ] frontend.md의 naming, structure 컨벤션을 따르는가
- [ ] any 타입 = 0건
