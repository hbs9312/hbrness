---
name: validate-visual
description: Storybook 기반 시각적 검증을 위한 리뷰 가이드를 생성합니다. "시각 검증", "Figma 비교", "디자인 QA" 요청 시 사용.
argument-hint: [컴포넌트 경로 또는 페이지 경로] [UI 명세서 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: medium
---

# 시각적 검증 (FV2)

에이전트는 렌더링 결과를 볼 수 없습니다.
이 스킬은 사람이 효과적으로 시각 검증할 수 있도록 리뷰 가이드를 생성합니다.

## 입력

$ARGUMENTS 에서:
1. 컴포넌트/페이지 파일 경로 → Read
2. UI 명세서 경로 → Read (해당 컴포넌트의 시각 명세)

## 역할

### 1. Storybook 커버리지 확인

컴포넌트의 .stories 파일을 Read로 읽고:
- UI 명세서의 모든 상태가 스토리로 존재하는지 확인
- 누락된 상태가 있으면 finding으로 리포트 (이건 에이전트가 판단 가능)

### 2. 리뷰 가이드 생성

UI 명세서의 컴포넌트 명세를 기반으로 사람이 확인할 체크리스트:

```markdown
## 📋 시각 리뷰 가이드: {컴포넌트명}

### Storybook에서 열기
Storybook URL: http://localhost:6006/?path=/story/{story-path}

### Figma와 비교할 포인트

**레이아웃:**
- [ ] 요소 배치 순서가 Figma와 일치하는가
- [ ] 요소 간 간격(gap)이 정확한가
- [ ] padding이 Figma와 동일한가
- [ ] 전체 크기/비율이 맞는가

**텍스트:**
- [ ] 폰트 크기가 맞는가
- [ ] 폰트 굵기가 맞는가
- [ ] 색상이 맞는가
- [ ] 말줄임 처리가 올바른가 (긴 텍스트 입력 시)

**상태별 확인:** (UI 명세서 기반)
- [ ] Default: {확인할 구체적 포인트}
- [ ] Hover: {확인할 구체적 포인트}
- [ ] Disabled: {확인할 구체적 포인트}
- [ ] Loading: {확인할 구체적 포인트}
- [ ] Error: {확인할 구체적 포인트}

**반응형:**
- [ ] 모바일 viewport(375px)에서 레이아웃 확인
- [ ] 태블릿/데스크톱에서 레이아웃 확인

### 응답 방법
- **승인**: "승인" → 다음 컴포넌트로
- **수정 필요**: 어떤 부분이 다른지 텍스트로 설명
  예: "StatusIcon과 이름 사이 간격이 Figma보다 넓음"
```

### 3. 피드백 구조화

사람의 피드백이 오면 FR 스킬에 전달할 수 있도록 구조화:

```yaml
visual_feedback:
  component: "{컴포넌트명}"
  issues:
    - type: "spacing"
      description: "StatusIcon과 이름 사이 gap이 8px → 4px로"
    - type: "color"
      description: "failed 상태 아이콘 색상이 red-400 → red-500으로"
```

## 향후 자동화 (Phase 2에서 FU4와 연동)

현재: 사람이 Storybook에서 확인
향후: Storybook 스크린샷 자동 캡처 → Figma 스크린샷과 픽셀 비교
→ diff 이미지를 에이전트에 피드백
