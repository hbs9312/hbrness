---
name: extract-refs
description: 명세서에서 참조 ID를 추출하고 인덱스를 생성합니다. "참조 추출", "레지스트리" 요청 시 사용.
argument-hint: [문서 경로 또는 specs/ 디렉토리]
tools: [file:read, search:grep, search:glob, file:write]
effort: medium
model: sonnet
---

# 참조 ID 추출/매핑 (U1)

## 입력: 파일 또는 디렉토리 ($ARGUMENTS)
## 추출 패턴: US-NNN, BR-NNN, FR-NNN, AC-NNN, ADR-NNN, TC-NNN, TASK-NNN

## 출력

```yaml
reference_index:
  {ID}: { source: "{문서}", section: "{섹션}", text: "{내용}" }

cross_references:
  - from: "{문서} > {위치}"
    to: "{ID}"
    type: "implements" | "verifies"

orphan_references:
  - location: "{문서} > {위치}"
    references: "{ID}"
    issue: "정의되지 않음"

next_available_ids:
  {접두사}: "{다음 번호}"
```

## 저장: specs/registry.md
