# Figma ↔ 역추출 와이어프레임 교차 규칙

design-first 모드에서 extract-wf-from-figma로 생성된 WF를 검증합니다.
Figma 원본과 역추출된 WF 사이의 구조적 일관성을 확인합니다.

## critical

1. Figma 최상위 프레임 수 = WF 화면 수 (variant 프레임은 상태로 분류, 화면이 아님)
2. Figma 컴포넌트 variant 수 = WF 상태 매트릭스 열 수 (정상/에러/로딩/빈 상태 등)
3. WF에 디자인 속성 침범 없음 (hex 색상, px 간격 수치, 폰트명, 토큰명 = 0건)

## warning

4. Figma 레이어 계층 깊이와 WF 요소 중첩 깊이 일치
5. Figma 인터랙티브 요소(버튼, 입력, 토글) 전수가 WF에 표현됨
6. Figma에 없는 상태가 WF 상태 매트릭스에 추가된 경우 FS 근거 확인 (AC/BR 참조 존재)
