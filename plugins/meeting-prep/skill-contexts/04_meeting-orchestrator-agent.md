# meeting-orchestrator 에이전트 생성 컨텍스트

> 이 문서는 skill-creator에게 전달하여 meeting-orchestrator 에이전트를 생성하기 위한 컨텍스트이다.

---

## 1. 에이전트 목적

사용자가 "회의 준비해줘"라고 요청하면 진입점이 되어, spec-scanner와 impl-scanner를 **서브에이전트로 병렬 실행**하고, 그 결과를 meeting-doc-gen 스킬에 넘겨 최종 회의 문서를 생성하는 **오케스트레이터**.

---

## 2. 왜 에이전트인가 (스킬이 아닌 이유)

| 비교 항목 | 스킬(SKILL.md) | 에이전트(AGENT.md) |
|-----------|---------------|-------------------|
| 서브에이전트 spawn | ❌ 불가 | ✅ 가능 |
| 병렬 실행 | ❌ 순차만 | ✅ 여러 서브에이전트 동시 실행 |
| 컨텍스트 분리 | ❌ 하나의 컨텍스트 공유 | ✅ 각 서브에이전트가 독립 컨텍스트 |
| 대규모 입력 처리 | ⚠️ 컨텍스트 윈도우 한계 | ✅ 분산 처리 |

기획서가 수십 개이고 프로젝트 코드가 수천 파일일 때, 하나의 컨텍스트에서 모두 분석하면 품질이 떨어진다. 서브에이전트로 분리하면 각각 독립적으로 깊이 있는 분석이 가능하다.

---

## 3. 에이전트 정의

### AGENT.md 프론트매터

```yaml
---
name: meeting-orchestrator
description: 기획서 분석과 구현 현황 파악을 병렬로 실행하고, 결과를 종합하여 회의 준비 문서를 생성합니다. "회의 준비", "미팅 안건 정리", "기획이랑 개발 상태 비교" 등을 요청할 때 사용하세요.
tools: Agent Read Write Bash Glob Grep
---
```

### 실행 플로우

```
사용자 요청
    │
    ▼
[1. 범위 확인]
    사용자에게 회의 주제/범위, 경로, 회의 유형 확인
    │
    ▼
[2. 서브에이전트 병렬 spawn]
    ┌─────────────────────────┬─────────────────────────┐
    │  Sub-Agent A            │  Sub-Agent B            │
    │  spec-scanner 스킬 실행  │  impl-scanner 스킬 실행  │
    │  → spec-analysis.md     │  → impl-analysis.md     │
    └────────────┬────────────┴────────────┬────────────┘
                 │                         │
                 ▼                         ▼
[3. 중간 결과 수집]
    두 analysis 파일을 읽어들임
    │
    ▼
[4. meeting-doc-gen 스킬 실행]
    두 분석 결과를 기반으로 고정 템플릿에 맞춰 최종 문서 생성
    │
    ▼
[5. 최종 문서 전달]
    meeting-prep/{주제}_{날짜}.md → 사용자에게 전달
```

---

## 4. 서브에이전트 프롬프트 설계

### Sub-Agent A: spec-scanner 실행

```
다음 디렉토리의 기획서를 분석해줘.

기획서 경로: {docs_path}
분석 범위: {scope}
출력 경로: {output_path}/spec-analysis.md

아래 스킬의 지침을 따라서 분석을 수행해:
- 스킬 경로: {plugin_path}/skills/spec-scanner/SKILL.md

반드시 지정된 중간 포맷에 맞춰 결과를 저장해.
```

### Sub-Agent B: impl-scanner 실행

```
다음 프로젝트들의 구현 현황을 분석해줘.

프로젝트 경로: {project_paths}
기획서 경로: {docs_path} (기획-구현 매핑용)
분석 범위: {scope}
출력 경로: {output_path}/impl-analysis.md

아래 스킬의 지침을 따라서 분석을 수행해:
- 스킬 경로: {plugin_path}/skills/impl-scanner/SKILL.md

반드시 지정된 중간 포맷에 맞춰 결과를 저장해.
```

---

## 5. 에이전트가 처리하는 교차 로직

서브에이전트들이 중간 포맷을 생성한 후, 오케스트레이터가 직접 수행하는 작업:

### 5.1 분석 결과 교차 대조
- spec-analysis의 불명확 항목과 impl-analysis의 미구현 항목을 교차 비교
- 기획 미확정 + 구현 일정 임박 = 🔴 긴급
- 기획 확정 + 미구현 = 🟡 중요
- 기획 미확정 + 백로그 = 🟢 참고

### 5.2 우선순위 산정
1. 개발 블로커 여부
2. 일정 긴급도
3. 영향 범위
4. 의사결정자 수

### 5.3 meeting-doc-gen 스킬로 문서 생성
- 교차 분석 결과와 두 중간 포맷을 meeting-doc-gen의 references/output-template.md 템플릿에 적용
- 최종 문서 생성 후 output_path에 저장

---

## 6. 에러 핸들링

| 상황 | 대응 |
|------|------|
| spec-scanner 서브에이전트 실패 | impl-scanner 결과만으로 부분 문서 생성, 기획 분석 실패 사유 명시 |
| impl-scanner 서브에이전트 실패 | spec-scanner 결과만으로 부분 문서 생성, 구현 분석 실패 사유 명시 |
| 둘 다 실패 | 사용자에게 오류 보고, 경로/권한 확인 요청 |
| 기획서 없음 (빈 디렉토리) | 사용자에게 알리고 impl-scanner만 실행 |
| 프로젝트 없음 | 사용자에게 알리고 spec-scanner만 실행 |
| 중간 포맷 파싱 실패 | 원본 분석 결과를 텍스트로 직접 참조하여 문서 생성 시도 |

---

## 7. 사용자 인터페이스 시나리오

### 기본 사용
```
사용자: "다음 회의 준비해줘"
에이전트: "회의 주제와 범위를 알려주세요. 기획서는 docs/에, 구현 코드는 backend/, frontend/에 있나요?"
사용자: "전체 점검이고, 그 경로 맞아"
에이전트: [spec-scanner, impl-scanner 병렬 실행] → [종합] → "회의 문서를 생성했습니다: meeting-prep/전체점검_2026-04-12.md"
```

### 특정 주제
```
사용자: "채팅 기능 관련 이슈 정리해줘"
에이전트: "채팅 기능 범위로 분석하겠습니다. 기획서와 코드 경로는 기본값(docs/, backend/, frontend/)으로 할까요?"
사용자: "응"
에이전트: [scope="채팅"으로 양쪽 스캐너 실행] → [종합] → "채팅 관련 회의 문서를 생성했습니다"
```

### 스캐너 단독 실행
```
사용자: "기획서에서 빠진 거 없는지 점검해줘"
→ spec-scanner 스킬이 직접 트리거됨 (에이전트 경유 안 함)
```

---

## 8. 플러그인 내 위치

```
meeting-prep/
├── .claude-plugin/
│   └── plugin.json
├── agents/
│   └── meeting-orchestrator/
│       └── AGENT.md              ← 이 에이전트
├── skills/
│   ├── spec-scanner/
│   │   └── SKILL.md
│   ├── impl-scanner/
│   │   └── SKILL.md
│   └── meeting-doc-gen/
│       ├── SKILL.md
│       └── references/
│           ├── output-template.md
│           └── inter-skill-protocol.md
└── README.md
```
