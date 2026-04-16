---
name: plan-sprints
description: 태스크를 스프린트에 배치하고 담당자를 제안합니다. "스프린트 배치" 요청 시 사용.
argument-hint: [태스크 경로] [의존성 경로] [추정 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: max
---

# 스프린트 배치 (P4)

## 입력: P1+P2+P3 + team.md(전체)

## 배치 원칙
- critical path 우선 배치
- 용량 = Σ(가용% × velocity) × 80%
- 담당자: 역할 태그 매칭 (★ 제안일 뿐, 최종은 팀)
- 마일스톤: 릴리스 일정에 역산
- 버퍼: 마일스톤마다 1~2일 분산

## 출력: sprints, milestones, risk_assessment
## 저장: specs/PLAN-{YYYY}-{NNN}-sprints.md
