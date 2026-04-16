# 병렬 다중 CLI 리뷰 설계 (Future Work)

> **상태**: 설계 단계 (미구현)
> **목적**: 여러 CLI 기반 LLM(codex, gemini, 자체 claude 등)에 동시에 리뷰를 위임하고 결과를 집계하여 단일 모델 편향을 완화하는 기능
> **현재 스킬과의 관계**: 기존 `xreview:review` 스킬의 확장. 기존 단일 CLI 경로는 보존하면서 병렬 경로를 추가 구성

---

## 1. 동기 (Motivation)

단일 LLM 기반 리뷰는 다음 한계를 가집니다:

1. **모델별 blind spot**: 각 모델이 놓치는 패턴이 다름 (예: GPT는 보안, Claude는 설계, Gemini는 성능에 강점)
2. **판정 신뢰도**: 단일 모델의 "critical" 판정은 false positive 가능
3. **벤더 의존성**: 특정 프로바이더 장애/정책 변경에 취약
4. **A/B 검증**: 새 모델 도입 시 기존 모델과의 품질 비교 필요

**복수 reviewer의 합의(consensus)** 를 활용하면 위 문제를 완화할 수 있습니다:
- 공통으로 발견된 finding은 높은 신뢰도
- 단일 reviewer만 발견한 finding은 낮은 신뢰도지만 탐색 가치 있음
- 판정 불일치 자체가 논의 필요성을 드러냄

---

## 2. 사용 시나리오

| 시나리오 | 설명 |
|----------|------|
| 보안 민감 코드 | 결제·인증 로직을 2개 이상 모델에서 교차 검증 |
| 릴리스 승인 게이트 | 모든 reviewer가 `pass` 또는 N-of-M이 `pass`일 때만 통과 |
| 모델 A/B 테스트 | 신규 모델 도입 평가를 위해 기존 모델과 동일 대상 동시 리뷰 |
| 명세서 품질 게이트 | PM 문서의 모호함 탐지에 여러 관점 동시 적용 |
| 레거시 리뷰 위탁 | 코드는 Codex, 문서는 Claude, 디자인은 Gemini 등 도구별 특화 분리 |

---

## 3. 인터페이스 제안

### 3.1 스킬 호출 (확장된 파라미터)

기존 `cli_tool` (단일)에 더해 `cli_tools` (복수)와 집계 전략을 추가합니다.

| 파라미터 | 설명 | 예시 |
|---------|------|------|
| `cli_tools` | 병렬 실행할 도구 목록 (콤마 구분) | `codex,gemini,claude-code` |
| `cli_models` | 도구:모델 매핑 | `codex:gpt-5.4,gemini:pro,claude-code:opus` |
| `aggregation` | 결과 집계 전략 | `union` / `consensus` / `weighted` (기본: `union`) |
| `quorum` | 합의 정족수 | `all` / `majority` / `N-of-M` (기본: `majority`) |
| `on_partial_failure` | 일부 CLI 실패 시 동작 | `continue` / `abort` / `retry` (기본: `continue`) |
| `per_tool_timeout` | 도구별 타임아웃(초) | `300` (기본: 300) |

### 3.2 호출 예시

```bash
# 기본 병렬 (집계는 union)
/xreview:review src/auth/*.ts --cli_tools codex,gemini

# 합의 기반 + 2-of-3 정족수
/xreview:review specs/fs-login.md \
  --cli_tools codex,gemini,claude-code \
  --aggregation consensus \
  --quorum 2-of-3

# 도구별 모델 지정 + 부분 실패 시 중단
/xreview:review src/payment/*.ts \
  --cli_models "codex:gpt-5.4,gemini:pro" \
  --aggregation weighted \
  --on_partial_failure abort
```

### 3.3 프로그래밍 호출

```
Skill("xreview:review", `
  target=src/auth/login.ts
  cli_tools=codex,gemini
  aggregation=consensus
  quorum=majority
  perspective=보안 취약점에 집중
`)
```

---

## 4. 아키텍처

### 4.1 에이전트 구성

```
┌─────────────────────────┐
│  xreview:review 스킬    │
│  - 프리셋 결정           │
│  - 병렬/단일 라우팅       │
└──────────┬──────────────┘
           │
           ├── (단일 CLI) → xreview:review-bridge  (기존 경로)
           │
           └── (복수 CLI) → xreview:review-aggregator (신규)
                                    │
                                    ├─ parallel spawn ─┐
                                    │                   │
                     ┌──────────────┼──────────────┐    │
                     ▼              ▼              ▼    │
              review-bridge   review-bridge   review-bridge
              (codex)         (gemini)        (claude-code)
                     │              │              │
                     └──────────────┴──────────────┘
                                    │
                                    ▼
                         정규화된 개별 결과 N개
                                    │
                                    ▼
                     review-aggregator가 병합
                                    │
                                    ▼
                         집계된 단일 결과 반환
```

### 4.2 신규 에이전트: `xreview:review-aggregator`

**역할**: N개의 `review-bridge`를 병렬 스폰하고, 결과를 집계 전략에 따라 병합.

**입력** (스킬로부터):
- `files`, `context`, `perspective`, `extra_instructions` (공통)
- `cli_tools`: 각 도구의 이름
- `cli_models`: 각 도구별 모델 (선택)
- `aggregation`: 집계 전략
- `quorum`: 합의 정족수
- `on_partial_failure`: 부분 실패 동작

**흐름**:
1. `cli_tools` 각각에 대해 `Agent(subagent_type="xreview:review-bridge", ...)` 병렬 호출
2. 모든 결과 수집 (또는 `abort` 조건 감지 시 중단)
3. 집계 전략 적용
4. 단일 `aggregated_review` 반환

**격리 보장**: 집계 에이전트 자체도 격리 컨텍스트. 개별 review-bridge는 현재와 동일하게 동작하므로 기존 격리 원칙 유지.

### 4.3 기존 `review-bridge` 변경 사항

거의 없음. 다만 다음 두 가지를 확인:
- `output_path`가 병렬 상황에서 충돌하지 않도록 스킬/aggregator가 도구별 suffix 부여 (예: `review.md` → `review.codex.md`, `review.gemini.md`)
- 임시 프롬프트 파일 경로도 도구별로 분리 (`/tmp/xreview-prompt-{timestamp}-{tool}.md`)

---

## 5. 집계 전략 (Aggregation Strategies)

### 5.1 `union`

모든 reviewer의 findings를 합집합. 중복 제거만 수행.

**중복 판단 기준** (아래 3개 모두 만족 시 중복으로 간주):
- `location`이 동일 파일 & ±3 라인 이내
- severity가 동일 (또는 한 단계 차이)
- `issue` 텍스트 유사도 70% 이상 (간단히는 Jaccard, 정교하게는 임베딩 비교 — 초기엔 텍스트 기반으로)

중복된 finding은 `reported_by` 배열에 모든 reviewer 이름 포함.

### 5.2 `consensus`

`quorum` 이상의 reviewer가 공통으로 보고한 finding만 포함.

- `quorum=all`: 모든 reviewer가 보고한 것만
- `quorum=majority`: 과반
- `quorum=N-of-M`: 명시적 수치 (예: `2-of-3`)

장점: 신뢰도 높음
단점: 각 reviewer의 고유 발견 누락

### 5.3 `weighted`

- 합의 수에 따라 `confidence` 가중치 부여
- 모든 finding 포함하되, 단일 reviewer 발견은 `confidence: low`, 과반 발견은 `confidence: high`
- severity 승격 규칙: 과반이 critical로 판정하면 critical 유지, 소수만 critical이면 warning으로 강등 (옵션)

### 5.4 판정(verdict) 집계

reviewer별 판정을 종합하여 `consensus_verdict` 결정:

| 규칙 | 결과 |
|------|------|
| 전원 `pass` | `pass` |
| `reject` 1개 이상 (보수적 모드) | `reject` |
| `quorum` 이상이 `pass` | `pass` |
| `quorum` 이상이 `reject` | `reject` |
| 그 외 | `needs-attention` |

**보수적 모드**(`strict_verdict: true`, 기본): 한 명이라도 reject면 reject.
**투표 모드**(`strict_verdict: false`): quorum 기반.

---

## 6. 출력 포맷

### 6.1 집계 결과 (`aggregated_review`)

```yaml
aggregated_review:
  target:
    files: ["..."]
    preset: "code"
    perspective: "..."

  strategy:
    aggregation: "consensus"
    quorum: "2-of-3"
    strict_verdict: true

  reviewers:
    - tool: "codex"
      model: "gpt-5.4"
      status: "ok"              # ok | failed | timeout
      verdict: "needs-attention"
      counts: { total: 5, critical: 1, warning: 3, info: 1 }
      duration_sec: 42
    - tool: "gemini"
      model: "pro"
      status: "ok"
      verdict: "pass"
      counts: { total: 2, critical: 0, warning: 0, info: 2 }
      duration_sec: 38
    - tool: "claude-code"
      model: "opus"
      status: "failed"
      error: "authentication required"
      duration_sec: 1

  consensus:
    verdict: "needs-attention"
    agreement_rate: 0.50          # 판정 일치율
    disagreement_points:          # 의견 불일치 항목
      - location: "src/auth/login.ts:78"
        issue: "..."
        verdicts:
          codex: "critical"
          gemini: "info"

  findings:
    - id: "XR-AGG-001"
      severity: "critical"
      reported_by: ["codex", "gemini"]
      consensus_score: "2/2"       # 성공한 reviewer 중 보고 수
      confidence: "high"
      location: "src/auth/login.ts:42"
      issue: "..."
      evidence:
        codex: "..."
        gemini: "..."
      suggestion: "..."             # 통합/대표 제안

    - id: "XR-AGG-002"
      severity: "warning"
      reported_by: ["codex"]
      consensus_score: "1/2"
      confidence: "low"
      location: "..."
      issue: "..."
      suggestion: "..."

  counts:
    total: 7
    by_consensus:
      unanimous: 1               # 전원 보고
      majority: 3                # 과반 보고
      minority: 3                # 단독 보고
    by_severity:
      critical: 1
      warning: 4
      info: 2

  warnings:
    - "claude-code reviewer failed: authentication required"
```

### 6.2 사용자 표시 시 포맷

```
병렬 리뷰 완료 (2/3 성공)
────────────────────────────────────────
대상: src/auth/login.ts
전략: consensus (quorum=2-of-3, strict_verdict=on)

Reviewer 결과:
  ✅ codex (gpt-5.4)       → needs-attention (5 findings, 42s)
  ✅ gemini (pro)          → pass           (2 findings, 38s)
  ❌ claude-code (opus)    → failed (auth required)

합의 판정: needs-attention (일치율 50%)

Findings (신뢰도 순):
  [high] XR-AGG-001 critical — src/auth/login.ts:42
    보고: codex, gemini (2/2)
    ...

  [low] XR-AGG-002 warning — src/auth/login.ts:156
    보고: codex (1/2)
    ...

의견 불일치:
  • src/auth/login.ts:78 — codex: critical vs gemini: info
```

---

## 7. 구현 단계 (Phased Rollout)

### Phase 1: 병렬 호출 (MVP)

**목표**: 집계 없이 병렬 실행만

- `cli_tools` 파라미터 수용
- 스킬이 N개 `review-bridge`를 병렬 스폰
- 결과를 순서대로 나열해서 반환 (병합 없음)
- 판정·findings 모두 reviewer별로 분리 표시

**산출물**: 사용자가 여러 모델 결과를 나란히 비교 가능

### Phase 2: 기본 집계

**목표**: `union` 전략 + 판정 합의

- `xreview:review-aggregator` 에이전트 도입
- 중복 제거(텍스트 기반) 구현
- `reported_by` 배열, `consensus_score` 기록
- `verdict` 집계(strict 모드)

**산출물**: 합치된 단일 findings 목록 + 집계 판정

### Phase 3: 고급 집계

**목표**: `consensus`·`weighted` 전략, 의미 기반 중복 제거

- `quorum` 파라미터 지원
- 임베딩 기반 유사도 (또는 LLM 기반 중복 판별 에이전트)
- severity 가중치·승격/강등 규칙
- 의견 불일치 섹션 명시

**산출물**: 신뢰도 기반 정제된 리뷰

### Phase 4: 정책·운영

**목표**: CI/CD 통합, 비용 최적화

- 프리셋별 권장 reviewer 구성 (예: `spec-fs` → claude+codex, `code` → codex+gemini)
- 비용/토큰 예측 및 사전 경고
- 결과 캐싱 (동일 대상 재리뷰 시)
- 실패 시 자동 재시도 정책
- GitHub Actions/ghflow 연동 (PR에 집계 리뷰 주석)

---

## 8. 열린 질문 (Open Questions)

결정이 필요한 사항:

1. **비용 제어**: 3개 모델 병렬 = 3배 비용. 기본값을 병렬로 할지, 명시 호출 시에만 병렬인지?
   → 초안: **명시 시에만 병렬** (`--cli_tools` 지정 시). 기본은 단일(`codex`)

2. **중복 판별 정확도**: 텍스트 유사도 기반은 false negative 많음. 임베딩/LLM 판별은 비용 추가.
   → 초안: Phase 2는 텍스트 기반, Phase 3에서 LLM 기반 옵션 추가

3. **부분 실패 기본값**: 리뷰어 1/3 실패 시 진행할지 중단할지?
   → 초안: **continue** 기본. 로그로 실패 명시. 중요 리뷰는 `--on_partial_failure abort` 명시

4. **도구별 특화 프리셋**: 예를 들어 "gemini는 성능 리뷰에만 강하니까 `perspective`에 성능만 주입" 같은 자동 최적화?
   → 초안: Phase 4 정책 단계에서 검토. 초기엔 모든 reviewer에 동일 프리셋

5. **순서 보장**: 사용자 표시 시 reviewer 순서를 고정할지 응답 순서대로 할지?
   → 초안: **입력 순서**대로 표시 (재현성 확보)

6. **스트리밍 vs 일괄**: 빠른 reviewer 결과를 먼저 보여줄지 (stream), 전체 완료 후 일괄 표시할지?
   → 초안: Phase 1은 일괄. Phase 4에서 스트리밍 옵션

7. **Claude Code 자체를 reviewer로 사용 가능?**: 메인 세션과 다른 격리된 Claude 인스턴스를 CLI로 호출.
   → 초안: `claude-code` CLI가 `--prompt`·stdin 지원하면 가능. Phase 2에서 프로토타입

---

## 9. 요약

- **현재**: `xreview:review` → `xreview:review-bridge` → 단일 CLI (codex)
- **확장 후**: `xreview:review` → (병렬 여부 분기) → `xreview:review-aggregator` → N × `xreview:review-bridge` → 집계 결과
- **기존 단일 경로는 변경 없이 유지**되며, 병렬은 **명시 호출(`cli_tools` 지정)** 시에만 활성화
- **구현 우선순위**: Phase 1(병렬 나열) → Phase 2(union 집계) → Phase 3(consensus/weighted) → Phase 4(정책·CI)

이 설계는 신규 기능 추가이며, 기존 스킬/에이전트의 파괴적 변경을 수반하지 않습니다.
