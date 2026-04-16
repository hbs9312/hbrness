---
name: reimpl-backend
description: 구조적 문제가 있는 코드를 재구현합니다. "재구현", "구조 변경", "리팩터링" 요청 시 사용.
argument-hint: [재구현 대상 파일/디렉토리] [피드백 내용 또는 findings 경로]
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 백엔드 재구현 (BR2)

패치(BR1)로 해결할 수 없는 구조적 문제를 재구현합니다.

## BR1 → BR2 에스컬레이션 기준

- 계층 경계 위반 (서비스에 HTTP 관심사, 컨트롤러에 비즈니스 로직)
- 순환 의존
- 트랜잭션 범위 오류
- 데이터 모델 구조 변경이 필요한 경우
- 패치 후 regression 발생

## 입력

$ARGUMENTS 에서:
1. 재구현 대상 파일/디렉토리
2. 피드백 (BV findings 또는 사람의 텍스트 피드백)

## 재구현 절차

1. **영향 분석**: 재구현 대상이 참조하는/참조되는 모든 파일 파악
2. **인터페이스 보존**: 가능하면 외부 인터페이스(메서드 시그니처)를 유지
3. **재작성**: 해당 Phase의 스킬(B1~B6) 규칙을 따라 재구현
4. **테스트 업데이트**: 기존 테스트를 새 구조에 맞게 수정
5. **변경 로그 작성**

```yaml
reimpl_log:
  target: "{파일/디렉토리}"
  reason: "{재구현 사유}"
  structural_changes:
    - type: "계층 분리"
      description: "컨트롤러의 비즈니스 로직을 서비스로 이동"
      files_affected: ["{파일 목록}"]
  interface_changes:
    - method: "SpeakerService.enroll"
      before: "enroll(dto, req)"
      after: "enroll(dto, context)"
      reason: "Request 객체 의존 제거"
  test_updates: ["{수정된 테스트 파일 목록}"]
```

## 재구현 후 검증

재구현 완료 후 해당 Phase의 검증을 재실행합니다:
- BV1 (코드 품질) — 항상
- BV2 (API 계약) — 컨트롤러 변경 시
- BV3 (테스트 품질) — 테스트 변경 시
