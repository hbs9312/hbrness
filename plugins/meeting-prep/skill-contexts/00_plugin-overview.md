# meeting-prep 플러그인 종합 개요

> 이 문서는 3개 스킬을 하나의 플러그인으로 묶기 위한 종합 안내서이다.

---

## 1. 플러그인 정보

| 항목 | 값 |
|------|---|
| 이름 | meeting-prep |
| 설명 | 기획서 분석과 구현 현황 파악을 병렬로 실행하고, 종합하여 회의 준비 문서를 자동 생성하는 플러그인 |
| 스킬 수 | 3개 |
| 에이전트 수 | 1개 |
| 주 사용자 | 개발팀 리드, PM, 기획자 |

---

## 2. 포함 컴포넌트

### 스킬 (3개)
| # | 스킬 | 역할 | 단독 사용 | 에이전트 경유 |
|---|------|------|----------|-------------|
| 1 | spec-scanner | 기획서 구조 파악 + 불명확 항목 탐지 | ✅ 가능 | ✅ 서브에이전트로 실행 |
| 2 | impl-scanner | 구현 프로젝트 구조 + 현황 분석 | ✅ 가능 | ✅ 서브에이전트로 실행 |
| 3 | meeting-doc-gen | 중간 포맷 → 고정 템플릿 회의 문서 변환 | ⚠️ 중간 포맷 필요 | ✅ 에이전트가 결과 종합 후 호출 |

### 에이전트 (1개)
| # | 에이전트 | 역할 |
|---|---------|------|
| 4 | meeting-orchestrator | 진입점. 스캐너 2개를 서브에이전트로 병렬 실행, 결과 교차 분석, meeting-doc-gen 호출 |

### 사용 시나리오별 트리거
- "회의 준비해줘" → **meeting-orchestrator** 에이전트 (전체 파이프라인)
- "기획서에서 빠진 거 없는지 점검해줘" → **spec-scanner** 스킬 단독
- "지금 백엔드 구현 현황 정리해줘" → **impl-scanner** 스킬 단독
- "분석 결과 가지고 회의 문서만 다시 뽑아줘" → **meeting-doc-gen** 스킬 단독

---

## 3. 데이터 흐름

```
                          meeting-orchestrator (에이전트)
                         ┌────────────────────────────────┐
                         │                                │
                         │  [1] 사용자 확인                │
                         │          │                     │
                         │          ▼                     │
                         │  [2] 서브에이전트 병렬 spawn     │
    ┌──────────────┐     │     ┌─────┴─────┐             │
    │ spec-scanner │◄────┼─────┤           ├─────►┌──────────────┐
    │   (스킬)     │     │     │           │      │ impl-scanner │
    └──────┬───────┘     │     └───────────┘      │   (스킬)     │
           │             │                        └──────┬───────┘
           ▼             │                               ▼
    spec-analysis.md     │                     impl-analysis.md
           │             │                               │
           └──────┐      │      ┌────────────────────────┘
                  ▼      │      ▼
                  [3] 교차 분석 (에이전트)
                         │
                         ▼
                  [4] meeting-doc-gen (스킬)
                         │
                         ▼
                  최종 회의 문서
                         │
                         └────────────────────────────────┘
```

### 중간 포맷 = 컴포넌트 간 계약

스캐너 스킬이 변경되더라도 중간 포맷만 유지되면 나머지 컴포넌트는 수정 없이 동작한다.

| 중간 포맷 | 생산자 | 소비자 | 저장 위치 |
|----------|--------|--------|----------|
| spec-analysis.md | spec-scanner (서브에이전트) | meeting-orchestrator → meeting-doc-gen | `{output_path}/spec-analysis.md` |
| impl-analysis.md | impl-scanner (서브에이전트) | meeting-orchestrator → meeting-doc-gen | `{output_path}/impl-analysis.md` |

중간 포맷의 상세 스키마는 각 스킬 컨텍스트 문서의 "출력 포맷" 섹션 참조.

---

## 4. 플러그인 디렉토리 구조

```
meeting-prep/
├── .claude-plugin/
│   └── plugin.json                    # 플러그인 매니페스트
├── agents/
│   └── meeting-orchestrator/
│       └── AGENT.md                   # 오케스트레이터 에이전트
├── skills/
│   ├── spec-scanner/
│   │   └── SKILL.md                   # 기획서 분석 스킬
│   ├── impl-scanner/
│   │   └── SKILL.md                   # 구현 현황 분석 스킬
│   └── meeting-doc-gen/
│       ├── SKILL.md                   # 회의 문서 생성 스킬
│       └── references/
│           ├── output-template.md     # 최종 출력 고정 템플릿
│           └── inter-skill-protocol.md  # 중간 포맷 정의서
└── README.md
```

---

## 5. 스킬 생성 순서

skill-creator에게 전달할 때 아래 순서로 진행하는 것을 권장한다:

### Phase 1: 스캐너 스킬 (독립적, 병렬 가능)
1. **spec-scanner** → 컨텍스트: `01_spec-scanner.md`
2. **impl-scanner** → 컨텍스트: `02_impl-scanner.md`

각 스캐너를 단독으로 테스트하여 중간 포맷이 올바르게 생성되는지 확인.

### Phase 2: 문서 생성 스킬
3. **meeting-doc-gen** → 컨텍스트: `03_meeting-doc-gen.md`

Phase 1의 스캐너 출력(중간 포맷)을 입력으로 사용하여 테스트.

### Phase 3: 오케스트레이터 에이전트
4. **meeting-orchestrator** → 컨텍스트: `04_meeting-orchestrator-agent.md`

Phase 1~2의 스킬들을 서브에이전트로 엮어 전체 파이프라인 테스트.

### Phase 4: 플러그인 패키징
5. 스킬 3개 + 에이전트 1개를 meeting-prep 플러그인으로 묶기
6. plugin.json 작성, README 추가

---

## 6. 테스트 시나리오

### 시나리오 1: 전체 스캔
```
"다음 주 개발 회의 준비해줘. docs/ 에 기획서가 있고 backend/, frontend/ 에 구현 코드가 있어."
```
→ 전체 기획서 스캔 + 전체 구현 현황 → 종합 회의 문서

### 시나리오 2: 특정 주제
```
"이미지 검열 관련해서 회의 안건 정리해줘."
```
→ 이미지 관련 기획서만 집중 스캔 + 관련 구현 확인 → 주제 특화 회의 문서

### 시나리오 3: 스캐너 단독
```
"기획서에서 아직 결정 안 된 항목 전부 뽑아줘."
```
→ spec-scanner만 실행 → spec-analysis.md 출력

### 시나리오 4: 스프린트 리뷰
```
"이번 스프린트에서 뭘 했고, 다음에 뭘 해야 하는지 정리해줘."
```
→ impl-scanner 중심 + 기획 갭 분석 → 스프린트 리뷰 형태 문서

---

## 7. 컨텍스트 문서 목록

| 파일 | 대상 | 용도 |
|------|------|------|
| `00_plugin-overview.md` (본 문서) | 플러그인 전체 | 종합 설계 안내 |
| `01_spec-scanner.md` | spec-scanner 스킬 | skill-creator 전달용 |
| `02_impl-scanner.md` | impl-scanner 스킬 | skill-creator 전달용 |
| `03_meeting-doc-gen.md` | meeting-doc-gen 스킬 | skill-creator 전달용 |
| `04_meeting-orchestrator-agent.md` | meeting-orchestrator 에이전트 | skill-creator 전달용 |

추가 참고:
| 파일 | 용도 |
|------|------|
| `../plugin-design.md` | 플로우 다이어그램, 중간 포맷 원본 정의 |
| `../skill-context.md` | 프로젝트 분석 원본 (기획서/코드 구조 분석 결과) |
