---
name: validate-api
description: 구현된 API가 기술 명세서의 계약과 일치하는지 검증합니다. "API 검증", "계약 검증", "스펙 대조" 요청 시 사용.
argument-hint: [기술 명세서 경로]
disable-model-invocation: true
tools: [file:read, sub-agent]
---

# API 계약 검증 (BV2) — 에이전트 디스패처

이 스킬은 클린룸 API 계약 검증 에이전트를 호출하는 디스패처입니다.
직접 검증을 수행하지 않습니다. 모든 판단은 격리된 에이전트가 합니다.

## 실행 계약

- 이 스킬은 dispatcher 입니다. 직접 검증하지 않습니다.
- 반드시 지정된 검증 에이전트를 격리 컨텍스트로 호출합니다.
- 호출 프롬프트에는 아래 "프롬프트 구성" 값을 빠짐없이 포함합니다.
- 빌드 산출물이 참조 에이전트 정의를 포함하는 harness 에서는 해당 지침 전체도 호출 프롬프트에 포함합니다.
- 에이전트가 반환한 summary 를 수정하지 않고 그대로 출력합니다.

## 에이전트 호출

서브에이전트로 `backflow:validator-api` 에이전트를 호출합니다.

프롬프트 구성:

```
기술 명세서: {$ARGUMENTS의 TS 절대 경로}
백엔드 프로젝트 컨텍스트: ${SKILL_DIR}/../../context/backend.md
결과 저장: specs/reviews/{TS문서ID}-BV2-{timestamp}.md
```

timestamp 형식: `YYYYMMDD-HHmmss`

## 결과 전달

에이전트가 반환한 summary를 그대로 출력합니다.

## dbflow 연계 (Phase 1.5)
API 검증 후 → 시나리오 기반 E2E 검증 (`dbflow:run`) 추가 권장. QA 명세 §5 기반.
