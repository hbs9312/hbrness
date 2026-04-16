---
name: revise
description: 사용자 피드백을 반영하여 기존 명세서를 수정합니다. "명세 수정", "피드백 반영", "스펙 고쳐줘", "명세서 변경" 요청 시 사용.
argument-hint: [명세서 경로] [피드백 내용]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 리바이즈 — 사용자 피드백 반영 (R3)

ultrathink

사용자의 자연어 피드백을 기존 명세서에 반영합니다.
R1(patch)은 검증 findings를, R2(regenerate)는 구조적 findings를 입력으로 받지만,
R3(revise)는 **사용자의 자연어 피드백**을 직접 입력으로 받습니다.

## 컨텍스트: [conventions.md](../../context/conventions.md), [glossary.md](../../context/glossary.md)

## 입력

$ARGUMENTS 에서 2가지를 추출합니다:
1. **명세서 경로** — 수정 대상 문서 (FS, WF, TS, UI, QA)
2. **피드백** — 사용자의 자연어 수정 요청

명세서를 Read로 읽고 문서 유형과 ID를 파악합니다.

## ★ 핵심 원칙: 피드백 범위 내 정밀 수정 ★

### 1. 피드백 분석

피드백을 다음으로 분류합니다:

| 분류 | 예시 | 처리 |
|------|------|------|
| **내용 수정** | "US-003 조건 변경해줘" | 해당 항목만 수정 |
| **항목 삭제** | "BR-005 필요 없어" | 삭제 + 참조 정리 |
| **명확화** | "AC-002가 모호해" | 구체적 표현으로 교체 |
| **구조 조정** | "섹션 순서 바꿔줘" | 섹션 이동, 내용 보존 |

### 2. 수정 규칙

1. 피드백이 언급한 부분**만** 변경 — 나머지는 원문 그대로 보존
2. 참조 ID 체계 유지 — ID 변경 시 문서 내 모든 참조도 함께 갱신
3. 항목 삭제 시 해당 ID를 참조하는 다른 항목에서도 참조 제거
4. 메타데이터 갱신 — 상태를 `In Review`로 변경, 작성일은 유지
5. 문서 경계 준수 — FS에 기술 결정을, TS에 비즈니스 정당성을 넣지 않음

### 3. 새 항목 추가 시

피드백이 새 항목 추가를 요구하면:
- 기존 ID 시퀀스의 **다음 번호**를 할당 (예: US-005 다음은 US-006)
- 추가된 항목이 다른 항목과 일관성을 유지하는지 확인
- 관련 섹션(AC, BR 등)에도 필요한 항목이 있으면 함께 추가

### 4. 모호한 피드백 처리

피드백의 의도가 불분명할 때:
- 가능한 해석을 changelog에 `interpretation` 필드로 기록
- 가장 보수적인(최소 변경) 해석으로 수정
- 사용자가 재확인할 수 있도록 변경 근거를 명시

## ★ 컨텍스트 격리 ★

G(생성) 과정의 대화 이력은 받지 않습니다.
문서에 기록된 내용만을 기준으로 판단합니다.

## 출력

```yaml
revision_log:
  document_id: "{문서ID}"
  feedback_summary: "{피드백 요약}"
  changes:
    - location: "{위치 — 섹션명 또는 참조ID}"
      type: "modified" | "added" | "deleted" | "moved" | "clarified"
      interpretation: "{모호한 경우 해석 근거}"
      before: |
        {원문 — 삭제/수정 시}
      after: |
        {수정문 — 추가/수정 시}
      rationale: "{변경 이유}"

  unchanged_note: "{수정하지 않은 피드백 항목이 있으면 이유 설명}"
```

revision_log 작성 후 원본 파일을 Edit으로 수정합니다.

## 저장

- 수정 문서: 원본 위치 덮어쓰기
- revision_log: specs/reviews/{문서ID}-R3-{timestamp}.md
