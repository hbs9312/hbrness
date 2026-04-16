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
