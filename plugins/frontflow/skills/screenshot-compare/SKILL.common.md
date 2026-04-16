---
name: screenshot-compare
description: 스크린샷 비교 기반 자동 시각 검증 (Phase 2 기능). 현재는 가이드만 제공.
argument-hint: [Storybook URL] [Figma 스크린샷 경로]
disable-model-invocation: true
tools: [file:read, file:write]
effort: low
---

# 스크린샷 비교 (FU4) — Phase 2

현재 이 스킬은 자동 스크린샷 비교의 설정 가이드를 제공합니다.
실제 자동 비교 기능은 Phase 2에서 구현 예정입니다.

## 현재 제공하는 것

### Chromatic 설정 가이드

```markdown
## Chromatic으로 시각 회귀 테스트 설정

1. 설치
   npm install --save-dev chromatic

2. package.json에 스크립트 추가
   "chromatic": "chromatic --project-token=YOUR_TOKEN"

3. CI에서 자동 실행
   PR마다 Storybook 스크린샷을 캡처하고
   이전 버전과 비교하여 시각적 변경을 감지

4. Figma 비교는 수동
   Chromatic의 스크린샷 + Figma 캡처를 나란히 비교
```

### Percy 설정 가이드

```markdown
## Percy로 시각 테스트

1. 설치
   npm install --save-dev @percy/cli @percy/storybook

2. 실행
   percy storybook http://localhost:6006

3. Percy 대시보드에서 diff 확인
```

## Phase 2 구현 계획

향후 이 스킬이 할 것:
1. Storybook을 headless로 실행
2. 각 스토리의 스크린샷 자동 캡처 (Playwright)
3. Figma API로 해당 컴포넌트 캡처
4. 픽셀 비교 → diff 이미지 생성
5. diff를 에이전트에 피드백 → FR1/FR2에 전달
