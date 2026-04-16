---
name: decompose
description: 승인된 명세서에서 구현 태스크를 분해합니다. "태스크 분해", "작업 분류" 요청 시 사용.
argument-hint: [기술 명세 경로] [기능 명세 경로] [화면설계서 경로] [테스트 명세 경로]
tools: [file:read, search:grep, search:glob, file:write]
effort: max
---

# 태스크 분해 (P1)

## 컨텍스트: [conventions.md](../../context/conventions.md), [glossary.md](../../context/glossary.md), [team.md](../../context/team.md)

## 입력: TS(주), FS, UI, QA 명세서

## 분해 원칙

- **원자성**: 1 태스크 = 1 사람 = 1 PR
- **추적 가능성**: 모든 태스크에 source_refs 필수
- **완료 정의**: "~를 구현한다" X → "~가 동작한다" O

## 분해 전략

1단계: 컴포넌트별 그룹 (인프라/백엔드/프론트/ML/QA)
2단계: 원자 태스크로 분해 (API 1개 = 구현+테스트 2태스크)
3단계: 숨겨진 태스크 (마이그레이션 롤백, 환경 변수 등록, 모니터링, 목 서버, CI/CD)

## 출력

```yaml
tasks:
  - id: "TASK-001"
    title: "{제목}"
    type: backend | frontend | infra | ml | qa
    source_refs: ["{문서ID} > {섹션}"]
    description: "{작업 내용}"
    deliverable: "{산출물}"
    acceptance_criteria: ["{검증 기준}"]
```

## 경계: 담당자 지정(P4), 공수(P3), 순서(P2) 하지 않음
## 저장: specs/PLAN-{YYYY}-{NNN}-tasks.md
