---
name: extend
description: 새 PRD/요구사항을 기존 명세서에 추가합니다. "기능 추가", "명세 확장", "스펙에 추가", "새 요구사항 반영" 요청 시 사용.
argument-hint: [기존 명세서 경로] [새 요구사항 — PRD 경로 또는 자연어]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write, file:edit]
effort: max
---

# 확장 — 새 범위 추가 (R4)

ultrathink

기존 명세서에 새로운 기능/요구사항을 추가합니다.
R3(revise)가 기존 내용의 수정이라면, R4(extend)는 **새 범위의 추가**입니다.

## 컨텍스트: [conventions.md](../../context/conventions.md), [glossary.md](../../context/glossary.md)

## 입력

$ARGUMENTS 에서 2가지를 추출합니다:
1. **기존 명세서 경로** — 확장 대상 문서 (FS, WF, TS, UI, QA)
2. **새 요구사항** — PRD 파일 경로 또는 자연어 요구사항

기존 명세서를 Read로 읽고 문서 유형, ID, 현재 참조 ID 범위를 파악합니다.

## ★ 핵심 원칙: 기존 보존 + 새 범위 병합 ★

### 1. 현황 분석

기존 문서에서 추출:
- 마지막 참조 ID 번호 (예: US-007이 마지막이면 새 항목은 US-008부터)
- 기존 섹션 구조와 목차
- 기존 항목 간 관계 (참조 그래프)

### 2. 새 요구사항 분석

새 요구사항에서 추출:
- 추가할 사용자 스토리, 비즈니스 룰, 수용 기준 등
- 기존 항목과의 관계 (의존, 확장, 독립)
- 기존 항목 중 수정이 필요한 것 (새 기능이 기존 흐름에 영향)

### 3. 병합 전략

#### 문서 유형별 처리

**FS (기능 명세서)**:
- 새 US/BR/AC를 기존 시퀀스 이어서 추가
- UI/UX 흐름에 새 화면/경로 추가
- 범위 밖(Out of Scope) 섹션에서 이번에 포함되는 항목 이동
- 기존 US와 새 US 간 의존 관계 명시

**WF (와이어프레임)**:
- 새 화면을 기존 화면 목록에 추가
- 화면 전환 맵에 새 경로 추가 (기존 화면 → 새 화면, 새 화면 → 기존 화면)
- 상태 매트릭스에 새 화면 행 추가

**TS (기술 명세서)**:
- 새 API 엔드포인트 추가
- 데이터 모델에 새 필드/테이블 추가 (기존 모델 수정 포함)
- 새 ADR 추가 (기존 ADR 번호 이어서)
- 시퀀스 다이어그램에 새 흐름 추가

**UI (화면설계서)**:
- 새 화면의 컴포넌트 명세 추가
- 기존 화면에 새 요소 추가 시 해당 화면 섹션 수정

**QA (테스트 명세서)**:
- 새 TC를 기존 시퀀스 이어서 추가
- 새 기능과 기존 기능의 통합 TC 추가
- 회귀 TC 섹션에 기존 기능 영향 TC 추가

### 4. 일관성 보장

- 새 항목의 참조 ID가 기존 범위와 겹치지 않는지 검증
- 새 항목에서 기존 항목을 참조할 때 올바른 ID 사용
- 기존 항목 중 새 기능으로 인해 수정이 필요한 것 함께 갱신
- 메타데이터 갱신: 상태를 `In Review`로 변경

### 5. 변경하지 않는 것

- 새 요구사항과 무관한 기존 항목은 원문 그대로 보존
- 기존 ID 번호 재배정 금지
- 기존 섹션 구조 변경 금지 (새 섹션은 기존 구조 뒤에 추가)

## ★ 컨텍스트 격리 ★

G(생성) 과정의 대화 이력은 받지 않습니다.
문서에 기록된 내용과 새 요구사항만을 기준으로 판단합니다.

## 출력

```yaml
extension_log:
  document_id: "{문서ID}"
  requirement_summary: "{새 요구사항 요약}"
  id_range:
    before: "{기존 마지막 ID — 예: US-007}"
    after: "{확장 후 마지막 ID — 예: US-012}"

  additions:
    - location: "{추가 위치 — 섹션명}"
      items: ["{추가된 참조 ID 목록}"]
      description: "{추가 내용 요약}"

  modifications:
    - location: "{수정 위치}"
      item: "{수정된 참조 ID}"
      reason: "{새 요구사항으로 인해 수정이 필요한 이유}"
      before: |
        {원문}
      after: |
        {수정문}

  downstream_hint: |
    이 확장으로 인해 하위 문서에 incremental generation이 필요합니다.
    오케스트레이터는 change-impact 분석 후 해당 문서들에 대해
    incremental 모드로 generate 스킬을 실행해야 합니다.
```

extension_log 작성 후 원본 파일을 Edit으로 수정합니다.

## 저장

- 수정 문서: 원본 위치 덮어쓰기
- extension_log: specs/reviews/{문서ID}-R4-{timestamp}.md
