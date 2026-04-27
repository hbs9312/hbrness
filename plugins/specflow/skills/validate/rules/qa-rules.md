# 테스트 명세서 검증 규칙

## 구조 완전성 (critical)
1. 메타데이터 + FS/TS 참조
2. 필수 4개 섹션 (기능, 기술, UI, 비기능 테스트)
3. TC 필수 필드: ID, 참조, 전제조건, 입력, 기대결과

## AC 커버리지 (critical)
4. FS 모든 AC에 대응 TC 존재
5. 모든 BR에 "위반 시" TC 존재

## 에러 코드 커버리지 (critical)
6. TS 모든 API 에러 코드에 대응 TC

## 장애 시나리오 (critical)
7. 외부 호출 장애 TC (타임아웃, 재시도, 최종 실패)
8. 동시성/경합 TC

## UI 커버리지 (warning → critical)
9. 상태 매트릭스 셀 TC → 에러/빈 상태 누락 시 critical

## 분포 (warning)
10. 정상:예외:경계값 ≈ 3:5:2
11. 경계값 TC 존재 (값-1, 값, 값+1)

## TC 품질 (warning)
12. 전제조건 재현 가능
13. 기대결과 자동 검증 가능
14. 고아 TC (참조 ID 없음) = 0

## 비기능 (warning)
15. 부하 테스트 최소 1개
16. 보안 테스트 최소 1개

## 크로스 참조 정확성 (warning)
17. 위치 기반 대명사 탐지: TC 본문(전제조건/입력/기대결과)에서 "위 {명사}", "상기 {명사}", "해당 {명사}" 등이 **다른 TC/AC/BR/엔드포인트**를 가리키는 경우 → 정확한 ID(`TC-NNN`, `AC-NNN`, `BR-NNN`, API 경로) 사용 권고. `conventions.md#크로스-참조-규칙` 참조.
    - 예외: 같은 TC 내부의 인접 bullet 목록을 "아래/위 항목"으로 가리키는 경우는 허용.

## E2E DB 시나리오 (warning — v1.x grace period)
18. §5 E2E DB 시나리오 섹션 존재 — DB 변화 있는 BR/AC 가진 프로젝트만 의무. 부재 시 정상
19. scenario_name 전역 유일 — 위반 시 warning
20. watch_tables 명시 — 누락 시 warning ("all 지양, 명시적 테이블 목록 권장")
21. fixture_required 가 in-feature 동작을 fixture 로 우회 → warning ("step chaining 권장")
22. steps_summary 의 path 가 TS §3.2 fragment 의 canonical path 와 매칭 — 불일치 시 warning
