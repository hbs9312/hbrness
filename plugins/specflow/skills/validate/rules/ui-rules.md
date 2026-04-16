# 화면설계서 검증 규칙

## 구조 완전성 (critical)
1. 메타데이터 + FS/WF 참조 + Figma 링크
2. 필수 5개 섹션 (토큰, 컴포넌트, 인터랙션, 반응형, 접근성)
3. WF 모든 UI 요소 ↔ 컴포넌트 매핑

## 디자인 토큰 (critical)
4. 하드코딩 값 탐지: #hex, Npx 직접 사용 → critical
5. 참조 토큰 존재 여부 (디자인 시스템 있을 때만)

## 컴포넌트 (critical)
6. 상태별 시각 변화 정의 (default/hover/pressed/disabled/focus/loading/error)
7. 내부 구성 명시
8. 터치 영역 44×44 명시

## 인터랙션 (warning)
9. duration 명시
10. easing 명시
11. 트리거 명시

## 반응형 (warning)
12. 최소 2개 브레이크포인트
13. 중간 브레이크포인트 동작 명확

## 접근성 (critical)
14. aria 속성
15. 포커스 순서
16. 장식 요소 aria-hidden
17. 색상 대비 WCAG AA

## 경계 (warning)
18. 비즈니스 로직 침범
19. 상태 관리 구현 침범
