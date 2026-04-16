# 전체 문서 ↔ 테스트 명세 교차 규칙

## critical
1. FS 모든 AC → QA TC 존재
2. FS 모든 BR → QA "위반 시" TC 존재
3. TS 모든 에러 코드 → QA TC 존재
4. TS 모든 외부 호출 장애 → QA TC 존재
5. TS 상태 전환 → QA TC 존재
7. QA 참조 ID가 FS/TS에 실존 (유령 참조 탐지)

## warning → critical
6. UI 상태 매트릭스 셀 → QA TC (에러/빈 누락 시 critical)

## warning
8. QA 필드명/에러코드가 TS와 일치
