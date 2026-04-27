---
name: patch-backend
description: 검증 피드백을 반영하여 코드를 부분 수정합니다. "수정", "피드백 반영", "패치" 요청 시 사용.
argument-hint: [수정할 파일 경로] [피드백 내용 또는 findings 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: high
model: sonnet
---

# 백엔드 패치 (BR1)

specflow R1, frontflow FR1과 동일한 최소 변경 원칙을 따릅니다.

## 입력

$ARGUMENTS 에서:
1. 수정할 파일 경로
2. 피드백 (BV findings 또는 사람의 텍스트 피드백)

## ★ 핵심 원칙: 최소 변경 ★

1. **피드백이 가리키는 부분만 수정**
   - "검증 순서가 다르다" → 해당 서비스 메서드의 검증 순서만 변경
   - "에러 코드가 없다" → 해당 에러 throw만 추가
   - "타입이 불일치" → 해당 DTO 필드만 변경

2. **다른 파일/계층은 건드리지 않음**
   - 서비스를 고치면서 컨트롤러를 건드리지 않음 (인터페이스 변경 시 제외)
   - 인터페이스 변경이 필요하면 영향 범위를 명시적으로 리포트

3. **테스트가 깨지지 않는지 확인**
   - 시그니처 변경 시 기존 테스트의 목(mock)도 업데이트

4. **변경 로그 작성**

```yaml
change_log:
  - file: "{파일 경로}"
    feedback: "{원본 피드백}"
    action: "modified"
    changes:
      - line: {N}
        before: "기존 코드"
        after: "수정된 코드"
        reason: "BR-001 검증이 쿼터 확인보다 앞에 있었음 → 순서 교정"
    side_effects:
      - file: "{영향받는 파일}" (있으면)
        change: "{변경 내용}"
```

## Edit 도구 사용

파일을 Read로 읽은 뒤, Edit 도구로 해당 부분만 수정합니다.
전체 파일을 Write로 재작성하지 마세요.
