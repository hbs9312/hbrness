---
name: estimate
description: 태스크별 공수를 상대 포인트로 추정합니다. "공수 추정" 요청 시 사용.
argument-hint: [태스크 목록 경로] [의존성 분석 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 공수 추정 (P3)

## 입력: P1 태스크 + P2 의존성 + team.md(velocity_history)

## 추정: 상대 포인트 (S:1~2, M:3~5, L:8, XL:13)
## XL 초과: 태스크 분해 부족 → P1에 피드백
## confidence: high | medium | low → low는 스파이크 태스크 추가
## 리스크 팩터: 경험 없음(+1~2), 외부 의존(+1~2), 보안/성능(+2~3)
## 보정: team.md velocity_history 보정 계수 적용

## 출력: estimates(태스크별) + summary(총합, 스프린트 수)
## 저장: specs/PLAN-{YYYY}-{NNN}-estimates.md
