---
name: analyze-deps
description: 태스크 간 의존성을 분석하고 실행 순서를 결정합니다. "의존성 분석" 요청 시 사용.
argument-hint: [태스크 목록 파일 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 의존성 분석 (P2)

## 입력: P1 태스크 목록 + 기술 명세서

## 의존성 유형
- hard: DB→API, API→프론트, 인프라→서비스 (반드시 선행)
- soft: ML→Worker, 백엔드→프론트 (목/스텁으로 우회 가능)
- none: 독립 컴포넌트, 테스트 코드

## 병렬화: soft dependency → 목/스텁 태스크 추가 생성

## 출력: dependency_graph, critical_path, parallel_groups, risk_bottlenecks
## 저장: specs/PLAN-{YYYY}-{NNN}-deps.md
