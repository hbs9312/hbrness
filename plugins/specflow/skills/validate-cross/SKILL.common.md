---
name: validate-cross
description: 두 개 이상의 명세서 간 교차 일관성을 검증합니다. "교차 검증", "문서 간 일관성" 요청 시 사용.
argument-hint: [문서1 경로] [문서2 경로] [...추가]
disable-model-invocation: true
tools: [file:read, sub-agent]
---

# 교차 일관성 검증 (V2) — 에이전트 디스패처

이 스킬은 클린룸 교차 검증 에이전트를 호출하는 디스패처입니다.
직접 검증을 수행하지 않습니다. 모든 판단은 격리된 에이전트가 합니다.

## 입력 처리

1. $ARGUMENTS 에서 모든 문서 경로를 추출합니다
2. 각 문서의 첫 10줄을 Read로 읽어 ID 접두사를 파악합니다
3. 문서 쌍의 접두사 조합으로 규칙 파일을 결정합니다:

| 조합 | 규칙 파일 |
|------|----------|
| FS + TS | `${SKILL_DIR}/rules/fs-ts-rules.md` |
| FS + WF | `${SKILL_DIR}/rules/fs-wf-rules.md` |
| WF + UI | `${SKILL_DIR}/rules/wf-ui-rules.md` |
| Figma + WF | `${SKILL_DIR}/rules/figma-wf-rules.md` |
| 3개 이상 + QA | `${SKILL_DIR}/rules/all-qa-rules.md` |

해당하는 규칙 파일이 여러 개이면 모두 포함합니다.

## 에이전트 호출

서브에이전트로 `specflow:validator-cross` 에이전트를 호출합니다.

프롬프트 구성:

```
검증 공통 원칙: ${SKILL_DIR}/../../context/validation-common.md
문서 컨벤션: ${SKILL_DIR}/../../context/conventions.md
교차 검증 규칙:
  - {규칙 파일 1 절대 경로}
  - {규칙 파일 2 절대 경로} (해당 시)
검증 대상 문서:
  - {문서1 절대 경로}
  - {문서2 절대 경로}
  - {추가 문서 절대 경로} (해당 시)
결과 저장: specs/reviews/CROSS-{ID1}-{ID2}-{timestamp}.md
```

timestamp 형식: `YYYYMMDD-HHmmss`

## 결과 전달

에이전트가 반환한 summary를 그대로 출력합니다.
