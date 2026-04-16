---
name: reimpl-frontend
description: 구조적 문제가 있는 컴포넌트를 재구현합니다. "재구현", "다시 만들기" 요청 시 사용.
argument-hint: [재구현할 컴포넌트 경로] [피드백 또는 findings 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: max
---

# 프론트엔드 재구현 (FR2)

ultrathink

specflow R2와 동일한 선택적 보존 원칙을 따릅니다.
패치(FR1)로 해결할 수 없는 구조적 문제일 때 사용합니다.

## 입력

$ARGUMENTS 에서:
1. 재구현할 컴포넌트/페이지 경로
2. 피드백 또는 findings

## 사용 조건

- 컴포넌트의 전체 구조(레이아웃 방식, 상태 관리)가 잘못됨
- FR1 패치 후에도 동일 문제 반복
- Props 인터페이스 자체가 부적절하여 전면 재설계 필요

## 재구현 원칙

### 선택적 보존

1. **보존할 것 식별**
   - 검증 통과한 하위 컴포넌트의 import는 유지
   - 타입 정의가 올바르면 보존
   - Storybook 스토리 구조는 유지 (args만 업데이트)

2. **재작성할 것**
   - 컴포넌트 본체 (JSX + 스타일링)
   - 필요 시 Props 인터페이스 재설계

3. **영향 확인**
   - 이 컴포넌트를 import하는 상위 컴포넌트/페이지 Grep으로 탐색
   - Props 변경 시 상위에서의 사용법도 업데이트

## 출력

재구현된 파일 + 변경 로그:

```yaml
change_log:
  - component: "{컴포넌트명}"
    action: "reimplemented"
    preserved: ["타입 정의", "Storybook 구조", "하위 컴포넌트 import"]
    rewritten: ["JSX 레이아웃", "스타일링 방식"]
    upstream_impact: ["{영향받는 파일 목록}"]
```
