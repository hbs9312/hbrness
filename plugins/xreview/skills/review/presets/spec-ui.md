# UI Specification (UI) Review Preset

## Default Context

이 파일은 화면설계서(UI Specification)입니다. 와이어프레임(WF)과 디자인 토큰을 기반으로 한 구체적 UI 명세로, 프론트엔드 개발자가 이를 보고 컴포넌트·페이지를 구현합니다. 토큰화·재사용성·접근성·상태 커버리지가 핵심입니다.

## Review Perspective

### 1. 컴포넌트 커버리지 (Component Coverage)
- WF의 모든 UI 요소가 컴포넌트로 정의되는가
- 원자·복합·페이지 레벨 분류가 일관되는가
- 재사용 가능한 단위인지, 과분해/과통합되지 않았는가
- 변형(variant)과 크기(size) 체계가 정의되는가

### 2. 디자인 토큰 사용 (Design Tokens)
- 색상·간격·타이포·그림자·반경 등이 토큰으로 참조되는가
- 하드코딩된 값(예: `#FFFFFF`, `16px`)이 있는가
- 토큰 이름이 의미적(semantic)인가 (예: `color-primary` vs `color-blue`)
- 다크모드·테마 전환 고려

### 3. 상태 스타일링 (State Styling)
각 인터랙티브 요소에 대해:
- 기본(default) / 호버(hover) / 활성(active) / 포커스(focus)
- 비활성(disabled) / 로딩(loading) / 에러(error) / 성공(success)
- 선택(selected) / 확장(expanded) 등 컴포넌트별 필요 상태

### 4. 접근성 (Accessibility)
- 색 대비(WCAG AA 이상) 기준 충족
- 포커스 표시·키보드 탐색 흐름이 정의되는가
- aria-label·semantic HTML 권고가 있는가
- 텍스트 크기·줄 높이 가독성

### 5. 반응형 (Responsive)
- 브레이크포인트가 정의되고 각 브레이크포인트의 레이아웃이 명시되는가
- 유동 레이아웃(flex·grid) vs 고정 레이아웃 선택 근거
- 컨텐츠 오버플로·줄바꿈 처리

### 6. WF와의 정합성
- 와이어프레임의 의도·상태·상호작용이 UI 명세에 반영되는가
- 추가된 시각적 요소가 WF를 위반하지 않는가

### 7. 애니메이션·전이 (Motion)
- 전이 효과의 duration·easing·목적이 정의되는가
- 모션 감소(prefers-reduced-motion) 고려

## Severity Guidance

- **critical**: 접근성 표준 위반(대비·포커스), 주요 상태 누락, 컴포넌트 누락, WF 위반
- **warning**: 토큰 미사용 하드코딩, 반응형 미정의, 변형 체계 불명확
- **info**: 시각 개선 제안, 모션 권고, 토큰 네이밍 개선
