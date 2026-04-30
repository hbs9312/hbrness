---
name: validate
description: 단일 명세서 문서를 품질 기준에 따라 검증합니다. "검증", "리뷰", "체크" 요청 시 사용.
argument-hint: [검증할 문서 파일 경로]
disable-model-invocation: true
tools: [file:read, sub-agent]
---

# 단일 문서 검증 (V1) — 에이전트 디스패처

이 스킬은 클린룸 검증 에이전트를 호출하는 디스패처입니다.
직접 검증을 수행하지 않습니다. 모든 판단은 격리된 에이전트가 합니다.

## 실행 계약

- 이 스킬은 dispatcher 입니다. 직접 검증하지 않습니다.
- 반드시 지정된 검증 에이전트를 격리 컨텍스트로 호출합니다.
- 호출 프롬프트에는 아래 "프롬프트 구성" 값을 빠짐없이 포함합니다.
- 빌드 산출물이 참조 에이전트 정의를 포함하는 harness 에서는 해당 지침 전체도 호출 프롬프트에 포함합니다.
- 에이전트가 반환한 summary 를 수정하지 않고 그대로 출력합니다.

## 입력 처리

1. $ARGUMENTS 에서 문서 경로를 추출합니다
2. 문서 첫 10줄을 Read로 읽어 `문서 ID:` 필드에서 접두사를 파악합니다
3. 접두사에 따라 규칙 파일 경로를 결정합니다:

| 접두사 | 규칙 파일 |
|--------|----------|
| FS- | `${SKILL_DIR}/rules/fs-rules.md` |
| WF- | `${SKILL_DIR}/rules/wf-rules.md` |
| TS- | `${SKILL_DIR}/rules/ts-rules.md` |
| UI- | `${SKILL_DIR}/rules/ui-rules.md` |
| QA- | `${SKILL_DIR}/rules/qa-rules.md` |

## 에이전트 호출

서브에이전트로 `specflow:validator-single` 에이전트를 호출합니다.

프롬프트 구성:

```
검증 공통 원칙: ${SKILL_DIR}/../../context/validation-common.md
문서 컨벤션: ${SKILL_DIR}/../../context/conventions.md
검증 규칙: {위에서 결정한 규칙 파일의 절대 경로}
검증 대상: {$ARGUMENTS의 문서 절대 경로}
결과 저장: specs/reviews/{문서ID}-V1-{timestamp}.md
```

timestamp 형식: `YYYYMMDD-HHmmss`

## 결과 전달

에이전트가 반환한 summary를 그대로 출력합니다.
