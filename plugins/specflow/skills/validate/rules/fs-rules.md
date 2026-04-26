# 기능 명세서 검증 규칙

## 구조 완전성 (critical)
1. 메타데이터 필수 필드 존재 여부
2. 필수 6개 섹션 존재 (배경, US, BR, UI흐름, AC, 범위밖)
3. US → AC 매핑: 모든 US에 대응 AC 존재
4. BR → 에러 AC 매핑: 모든 BR 위반 시 동작 AC 존재

## 명확성 (warning → critical 승격 가능)
5. 모호 표현 탐지: "적절한", "빠르게", "다양한", "충분한" 등 → BR에서 발견 시 critical
6. 목표 지표 측정 가능성: 수치 + 측정 방법

## UI/UX 상태 커버리지 (critical)
7. 모든 화면에 정상/로딩/에러/빈 상태 4개 정의
8. 각 화면에 진입/이탈 경로 명시

## 범위 관리 (warning)
9. Out of Scope 섹션 존재 + 최소 1개 항목
10. 항목이 구체적 기능/동작으로 명시

## 경계 검증 (warning)
11. 기술 키워드 탐지: 테이블, 스키마, 인덱스, FK, 엔드포인트, POST/GET/DELETE, Cloud Run, GCS, S3, PostgreSQL, Redis, Pub/Sub, WebSocket 등 (glossary.md 예외)

## ID 규격 (info)
12. 참조 ID 형식 준수
13. 연번 순차성

## 크로스 참조 정확성 (warning)
14. 위치 기반 대명사 탐지: BR/AC/US 본문에서 "위 {명사}", "상기 {명사}", "해당 {명사}" 등이 **다른 BR/AC/US/섹션**을 가리키는 경우 → 정확한 ID(`BR-NNN`, `AC-NNN`, `US-NNN`) 사용 권고. `conventions.md#크로스-참조-규칙` 참조.
    - 예외: 같은 BR/AC 내부의 인접 bullet 목록을 "아래/위 항목"으로 가리키는 경우는 허용.

## 이벤트 트래킹 (warning — v1.x grace period)
15. §7 이벤트 트래킹 섹션 존재 — 누락 시 warning + skill 은 page_view / nav_click / error_shown 3종 default 로 동작
16. event_name snake_case + 전역 유일 — 위반 시 warning
17. event_name 예약어 충돌 — page_view / nav_click / error_shown 을 다른 의미로 재정의 시 warning
18. when (trigger) 가 모호 표현("적절히", "필요시") 포함 — warning
19. properties 에 PII 키 검출 — comma-split + nested-segment(`contact.email` 의 `email`) 파싱 후 email/phone/ssn/card_number/password/user_id 매칭 → warning
20. error_shown 이벤트가 정의되면 properties 에 error_code 필수 — 누락 시 warning (Phase 1 (1) ErrorCode 연계)
21. error_shown 의 where 컬럼이 handler.ts / errors/handler 를 가리키면 → warning ("순수 함수 원칙 위반 — 호출자로 이동")
