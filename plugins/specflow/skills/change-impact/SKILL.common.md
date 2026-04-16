---
name: change-impact
description: 문서 변경 시 영향받는 다른 문서를 분석합니다. "영향 분석", "변경 전파" 요청 시 사용.
argument-hint: [변경 대상 문서 경로] [변경 내용 설명]
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 변경 영향 분석 (U3)

## 입력: 변경 대상 문서 + 변경 내용 ($ARGUMENTS)
## 추가: specs/registry.md (있으면), 없으면 Grep 스캔

## 분석
1. 변경 대상 참조 ID 식별
2. 해당 ID 참조하는 모든 문서/위치 Grep 탐색
3. 각 참조 지점에서 변경 필요 여부 판단
4. 변경 불필요한 참조도 이유와 함께 표시

## 출력

```yaml
change_source:
  document: "{문서}"
  item: "{ID}"
  change: "{변경 내용}"

impact:
  - document: "{문서}"
    items:
      - location: "{위치}"
        action_needed: "{필요한 변경}"

no_impact:
  - document: "{문서}"
    reason: "{영향 없는 이유}"
```

## 저장: specs/reviews/impact-{ID}-{timestamp}.md
