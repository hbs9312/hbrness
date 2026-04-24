# 기술 명세서 검증 규칙

## 구조 완전성 (critical)
1. 메타데이터 + FS/WF 참조
2. 필수 8개 섹션 (ADR, 아키텍처, API, **에러 코드 맵**, 데이터모델, 플로우, 비기능, 인프라)
3. 참조 문서 ID 유효성

## ADR 품질 (critical)
4. 동기/비동기, DB, 라이브러리, 인증, 메시지큐 결정에 ADR 존재
5. ADR 필수 필드: 맥락, 결정, 근거, 트레이드오프, 대안(최소 1), 재평가
6. 기각 대안에 구체적 사유

## API 설계 (critical)
7. 에러 응답에 AC/BR 번호 매핑
8. POST/PUT에 서버 측 검증 순서 명시
9. 에러 응답 완전성 (401, 403, 404, 400, 429, 413 해당 시)

## 데이터 모델 (critical)
10. BR → DB 제약 매핑 (UNIQUE 등 + BR 주석)
11. 인덱스 근거 (쿼리 패턴 커버)
12. FK 참조 대상 + 삭제 정책 명시

## 처리 흐름 (critical)
13. 모든 외부 호출에 타임아웃 + 재시도 + 최종 실패 정의
14. 비동기 완료 알림 메커니즘 명시
15. 상태 enum 일관성 (데이터모델 = API = 시퀀스)

## 비기능 (warning → critical)
16. 수치 명확성: "빠르게" → critical, "p95<2초" → OK
17. 보안: 암호화, TLS, 접근 제어 정의

## 인프라 (warning)
18. 환경 변수 목록
19. 모니터링 알림 최소 1개
20. 배포 체크리스트 존재
21. 롤백 절차

## 경계 (warning)
22. 비즈니스 침범: "사용자가 원하는", "비즈니스 목표", UX 카피, 사용자 감정

## 크로스 참조 정확성 (warning)
23. 위치 기반 대명사 탐지: ADR/API/데이터모델/처리흐름 본문에서 "위 {명사}", "상기 {명사}", "해당 {명사}" 등이 **다른 ADR/BR/AC/섹션**을 가리키는 경우 → 정확한 ID(`ADR-NNN`, `BR-NNN`, `AC-NNN`, 엔드포인트 경로, 테이블명) 사용 권고. `conventions.md#크로스-참조-규칙` 참조.
    - 예외: 같은 ADR/섹션 내부의 인접 bullet 목록을 "아래/위 항목"으로 가리키는 경우는 허용.

## 에러 코드 맵 (warning — v1.x grace period; v2.0 에 critical 승격 예정)
24. §에러 코드 맵 섹션 존재 — 누락 시 warning (grace). 누락 시 skill 은 기본 에러 코드 5종(AUTH/USER/VALIDATION/SYSTEM/NETWORK) 으로 임시 동작
25. code 전역 유일성 — 같은 code 가 여러 행에 등장하면 warning
26. code 네이밍: UPPER_SNAKE_CASE + 도메인 prefix — `NOT_FOUND` 처럼 도메인 없는 code 는 warning (`USER_NOT_FOUND` 권고)
27. domain 교차검증 — FS §도메인 정의에 없는 domain 을 사용하면 warning (`conventions.md` 의 domain snake_case 규약 참조)
28. http_status 허용 범위 — 400/401/403/404/409/422/429/500/502/503/504 외 값 사용 시 warning + 사용자 review 요청
29. i18n_key 패턴 — `errors.{domain}.{snake}` 패턴에 어긋나면 warning
30. API Error Responses 의 CODE 가 §에러 코드 맵에 없으면 warning ("orphan code")
31. §에러 코드 맵에 있으나 어떤 API 에서도 참조되지 않는 code — warning ("unused code"; 의도적 예약이면 주석 권고)
32. message_ko / message_en: 기술 용어 노출 금지 — "DB 연결 실패" 같은 내부 상태 단어 감지 시 warning ("사용자 대상 메시지로 완화 권고")
