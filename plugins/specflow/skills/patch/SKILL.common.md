---
name: patch
description: 검증 findings를 반영하여 문서를 부분 수정합니다. "패치", "수정", "findings 반영" 요청 시 사용.
argument-hint: [원본 문서 경로] [findings 파일 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: high
model: sonnet
---

# 패치 — 부분 수정 (R1)

최소한의 변경으로 findings를 해소합니다.

## 컨텍스트: [conventions.md](../../context/conventions.md), [glossary.md](../../context/glossary.md)

## 입력: 원본 문서 + Findings 파일 ($ARGUMENTS 에서 2개 경로)

## ★ 핵심 원칙: 최소 변경 ★

1. findings location이 가리키는 부분만 변경
2. 수정하지 않는 부분은 원문 그대로 보존
3. 참조 ID 수 감소 금지, 대상 외 섹션 변경 금지
4. 수정 불필요 시 action: no_change + reason 명시

## ★ 컨텍스트 격리 ★

생성(G) 과정의 대화 이력은 받지 않습니다.
문서에 없는 맥락("의도적으로 뺐다")은 모릅니다.

## 출력

```yaml
change_log:
  - finding_id: "V1-001"
    location: "{위치}"
    action: "modified"
    before: |
      {원문}
    after: |
      {수정문}
    rationale: "{수정 이유}"

  - finding_id: "V1-002"
    action: "no_change"
    reason: "{수정 불필요 사유}"
```

change_log 작성 후 원본 파일을 Edit으로 수정.

## 저장
- 수정 문서: 원본 위치 덮어쓰기
- change_log: specs/reviews/{문서ID}-R1-{timestamp}.md
