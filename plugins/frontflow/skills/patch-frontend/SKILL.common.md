---
name: patch-frontend
description: 검증 피드백을 반영하여 코드를 부분 수정합니다. "수정", "피드백 반영", "패치" 요청 시 사용.
argument-hint: [수정할 파일 경로] [피드백 내용 또는 findings 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: high
---

# 프론트엔드 패치 (FR1)

specflow R1과 동일한 최소 변경 원칙을 따릅니다.

## 입력

$ARGUMENTS 에서:
1. 수정할 파일 경로
2. 피드백 (FV findings 또는 사람의 텍스트 피드백)

## ★ 핵심 원칙: 최소 변경 ★

1. **피드백이 가리키는 부분만 수정**
   - "간격이 넓다" → 해당 gap/padding만 변경
   - "색상이 다르다" → 해당 토큰 참조만 변경

2. **다른 파일/컴포넌트는 건드리지 않음**
   - StatusIcon의 간격을 고치면서 SpeakerCard의 레이아웃을 건드리지 않음

3. **Storybook 스토리가 깨지지 않는지 확인**
   - Props 변경 시 스토리의 args도 업데이트

4. **변경 로그 작성**

```yaml
change_log:
  - file: "{파일 경로}"
    feedback: "{원본 피드백}"
    action: "modified"
    changes:
      - line: {N}
        before: "gap-3"
        after: "gap-1"
        reason: "StatusIcon-이름 간격 12px→4px (Figma 기준)"
```

## Edit 도구 사용

파일을 Read로 읽은 뒤, Edit 도구로 해당 부분만 수정합니다.
전체 파일을 Write로 재작성하지 마세요.
