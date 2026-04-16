---
name: regenerate
description: 검증 findings가 구조적일 때 문서를 선택적으로 보존하며 재생성합니다. "재생성", "전면 수정" 요청 시 사용.
argument-hint: [원본 문서 경로] [findings 경로] [원본 입력 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: max
---

# 재생성 — 구조적 수정 (R2)

ultrathink

R1으로 해결 불가한 구조적 문제를 다룹니다.

## 컨텍스트: [conventions.md](../../context/conventions.md), [glossary.md](../../context/glossary.md)

## 입력: 원본 문서 + Findings + 원본 입력(PRD 등) ($ARGUMENTS 에서 3개 경로)

## ★ 핵심 원칙: 선택적 보존 ★

G처럼 백지 시작 아님. R1처럼 국소 수정도 아님.

### 3단계 프로세스

1. **건전 영역 식별**: findings 무관 섹션 → 원문 보존
2. **결함 섹션 재작성**: 원본 입력 참조, G 스킬 기준 적용
3. **통합**: 참조 ID 일관성, 보존↔재작성 연결

## ★ 컨텍스트 격리 ★

G 스킬 대화 이력 차단. 원본 입력(PRD 등)은 받음 — 구조 재설계에 필요.

## 출력

```yaml
change_log:
  - section: "{섹션명}"
    action: "restructured" | "preserved" | "adjusted"
    finding_ids: [...]
    description: "{변경 내용}"
```

## 저장
- 재생성 문서: 원본 위치 덮어쓰기
- change_log: specs/reviews/{문서ID}-R2-{timestamp}.md
