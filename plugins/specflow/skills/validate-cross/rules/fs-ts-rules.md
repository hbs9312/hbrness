# 기능 명세 ↔ 기술 명세 교차 규칙

## critical
1. AC → API 에러 매핑: FS의 모든 AC에 TS API 대응 동작 존재
2. API 에러 → FS 근거: TS의 모든 에러 코드에 FS AC/BR 대응 존재
3. BR → DB 제약: 모든 BR에 대응 DB 제약 존재
4. DB 제약 → BR 근거: 근거 없는 제약 = 과잉 or BR 누락
5. 상태 enum 값 개수 일치

## warning
6. 필드명 일관성 (FS "화자 이름" ↔ TS "name")
7. UI 흐름 ↔ 시퀀스 정합성
8. 비기능 수치 일치 (FS "5초 이내" ↔ TS "p95<15초" → 불일치)
