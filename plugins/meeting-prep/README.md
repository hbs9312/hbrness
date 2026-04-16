# meeting-prep

기획서 분석과 구현 현황을 병렬 분석하여 회의 준비 문서를 자동 생성하는 Claude Code 플러그인.

## 설치

```bash
/plugin marketplace add hbs9312/meeting-prep
/plugin install meeting-prep@meeting-prep
```

또는 로컬에서 테스트:

```bash
claude --plugin-dir ./meeting-prep
```

## 포함 컴포넌트

### 스킬 (3개)

| 스킬 | 역할 | 단독 사용 |
|------|------|----------|
| `spec-scanner` | 기획서 구조 파악 + 불명확 항목 탐지 | O |
| `impl-scanner` | 구현 프로젝트 구조 + 현황 분석 | O |
| `meeting-doc-gen` | 중간 포맷 → 고정 템플릿 회의 문서 변환 | 중간 포맷 필요 |

### 에이전트 (1개)

| 에이전트 | 역할 |
|---------|------|
| `meeting-orchestrator` | 스캐너 2개를 병렬 실행, 결과 교차 분석, 최종 문서 생성 |

## 사용법

### 전체 회의 준비 (에이전트)

```
"다음 회의 준비해줘"
```

meeting-orchestrator가 기획서와 구현 코드를 병렬 분석하여 회의 문서를 생성합니다.

### 기획서 분석만 (스킬 단독)

```
"기획서에서 빠진 거 없는지 점검해줘"
```

### 구현 현황만 (스킬 단독)

```
"지금 백엔드 구현 현황 정리해줘"
```

### 문서 재생성 (스킬 단독)

```
"분석 결과 가지고 회의 문서만 다시 뽑아줘"
```

## 데이터 흐름

```
사용자 요청
    │
    ▼
meeting-orchestrator (에이전트)
    ├── spec-scanner (서브에이전트) → spec-analysis.md
    ├── impl-scanner (서브에이전트) → impl-analysis.md
    │
    ▼ 교차 분석
    │
    └── meeting-doc-gen (스킬) → {주제}_{날짜}.md
```

## 라이선스

MIT
