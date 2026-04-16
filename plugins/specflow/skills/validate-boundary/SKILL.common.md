---
name: validate-boundary
description: 문서가 자신의 영역 경계를 침범하지 않는지 검증합니다. "경계 검증" 요청 시 사용.
argument-hint: [검증할 문서 파일 경로]
disable-model-invocation: true
tools: [file:read, sub-agent]
---

# 경계 침범 검증 (V3) — 에이전트 디스패처

이 스킬은 클린룸 경계 검증 에이전트를 호출하는 디스패처입니다.
직접 검증을 수행하지 않습니다. 모든 판단은 격리된 에이전트가 합니다.

## 에이전트 호출

서브에이전트로 `specflow:validator-boundary` 에이전트를 호출합니다.

프롬프트 구성:

```
검증 공통 원칙: ${SKILL_DIR}/../../context/validation-common.md
문서 컨벤션: ${SKILL_DIR}/../../context/conventions.md
용어집: ${SKILL_DIR}/../../context/glossary.md
검증 대상: {$ARGUMENTS의 문서 절대 경로}
결과 저장: specs/reviews/{문서ID}-V3-{timestamp}.md
```

timestamp 형식: `YYYYMMDD-HHmmss`

## 결과 전달

에이전트가 반환한 summary를 그대로 출력합니다.
