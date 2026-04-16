---
name: review
description: 외부 CLI 기반 LLM(codex 등)에게 작업물 리뷰를 위임하고 결과를 구조화하여 반환하는 스킬. 대상 파일 유형에 따라 기본 리뷰 관점(preset)을 자동 선택하며, 호출자가 `perspective`나 `context`를 명시하면 프리셋을 오버라이드합니다. 코드, 기능/기술/와이어프레임/UI/QA 명세서, 디자인 파일 등 다양한 산출물을 리뷰할 수 있습니다. 사용자가 "리뷰해줘", "코드 리뷰", "명세서 검토", "다른 모델로 리뷰", "/xreview:review" 등을 말하면 트리거하거나, 타 플러그인에서 Skill tool로 호출합니다.
---

# xreview:review

외부 CLI 기반 LLM에게 리뷰를 위임하는 공용 진입점입니다.
프리셋 기반 관점 제공 + 호출자 오버라이드 + `review-bridge` 에이전트 격리 실행으로 구성됩니다.

## 입력 파라미터

스킬 인자는 자유로운 자연어 또는 구조화된 키-값으로 전달받습니다. 아래 키를 추출하세요:

| 파라미터 | 필수 | 기본값 | 설명 |
|---------|------|--------|------|
| `target` | Y | - | 리뷰 대상 파일 경로 (콤마·공백 구분, glob 허용) |
| `preset` | N | 자동 감지 | 리뷰 프리셋 이름 |
| `context` | N | 프리셋 기본값 | 상황 설명 |
| `perspective` | N | 프리셋 기본값 | 리뷰 관점 |
| `cli_tool` | N | `codex` | 사용할 CLI 도구 |
| `cli_model` | N | - | 요청할 모델명 |
| `output_path` | N | - | 결과 저장 경로 |
| `extra_instructions` | N | - | 리뷰어에게 추가 전달할 지시사항 |

자연어 호출 예: `/xreview:review src/auth/*.ts --perspective "보안 관점에서만 검토"`
프로그래밍 호출 예: `Skill("xreview:review", "target=specs/fs-login.md preset=spec-fs")`

## 프리셋 목록

| 프리셋 | 용도 | 자동 감지 패턴 |
|--------|------|---------------|
| `code` | 구현 코드 리뷰 | `*.ts`, `*.tsx`, `*.js`, `*.jsx`, `*.py`, `*.go`, `*.java`, `*.rs`, `*.rb`, `*.kt`, `*.swift`, `*.cs` 등 |
| `spec-fs` | 기능 명세서 | 경로에 `fs-`, `feature-spec`, `기능명세` |
| `spec-ts` | 기술 명세서 | 경로에 `ts-`, `technical-spec`, `기술명세` |
| `spec-wf` | 와이어프레임 | 경로에 `wf-`, `wireframe`, `와이어` |
| `spec-ui` | 화면설계서 | 경로에 `ui-`, `ui-spec`, `화면설계` |
| `spec-qa` | 테스트 명세서 | 경로에 `qa-`, `test-spec`, `테스트명세` |
| `design` | 디자인 파일 | `*.fig`, `*.sketch`, `*.png`, `*.jpg`, Figma URL |
| `doc` | 일반 문서 | 기타 `*.md`, `*.txt` |

각 프리셋은 `presets/<name>.md` 파일로 정의되며, 다음 섹션을 가집니다:
- `## Default Context`
- `## Review Perspective`
- `## Severity Guidance`

## 오버라이드 규칙

| preset 지정 | perspective 지정 | 동작 |
|------------|-----------------|------|
| O | O | `perspective`가 프리셋 관점을 **완전히 대체** |
| O | X | 프리셋 관점 사용 |
| X | O | 자동 감지된 프리셋을 로드하고, `perspective`가 관점을 대체 |
| X | X | 자동 감지 + 프리셋 기본값 사용 |

- `context`가 명시되면 프리셋 컨텍스트 **앞에** 추가됩니다(우선).
- `extra_instructions`은 항상 최종 프롬프트 **뒤에** 추가됩니다.

## 실행 흐름

### Step 1: 입력 파싱

스킬 인자에서 위 파라미터를 추출합니다. 파일 경로가 여러 개이거나 glob이면 전부 수집합니다.

### Step 2: 프리셋 결정

1. `preset`이 명시되었으면 해당 프리셋 로드.
2. 미명시면 `target` 파일들을 검사하여 자동 감지:
   - 단일 파일: 해당 파일의 패턴으로 결정
   - 복수 파일: 가장 많이 매치되는 프리셋 선택. 동률이거나 혼합이면 `doc`으로 폴백하고 경고 로그
3. 감지 실패 시 `doc` 프리셋을 기본으로 사용하고 사용자에게 알림

### Step 3: 프리셋 로드

`${PLUGIN_ROOT}/skills/review/presets/<preset>.md`를 Read로 읽어
`## Default Context`, `## Review Perspective`, `## Severity Guidance` 섹션을 추출합니다.

### Step 4: 리뷰 요청 조립

에이전트에 전달할 파라미터를 아래 규칙으로 조립합니다:

```
final_context =
  (caller_context가 있으면: caller_context + "\n---\n") + preset.default_context

final_perspective =
  caller_perspective (있으면)
  또는
  preset.review_perspective + "\n\n" + preset.severity_guidance

final_extra_instructions = extra_instructions (있으면 그대로)
```

### Step 5: review-bridge 에이전트 스폰

아래 형식으로 서브에이전트를 호출합니다:

```
harness_spawn({
  description: "외부 LLM 리뷰 위임 (<preset>)",
  agent_ref: "xreview:review-bridge",
  prompt: `
files: <콤마로 구분된 파일 경로들>
context: <final_context>
perspective: <final_perspective>
cli_tool: <cli_tool, 기본 codex>
cli_model: <cli_model, 있으면>
output_path: <output_path, 있으면>
extra_instructions: <final_extra_instructions, 있으면>
`
})
```

에이전트는 격리된 상태에서:
1. 파일들을 읽고
2. 구조화된 리뷰 프롬프트를 구성하여
3. CLI 도구에 전달하고
4. 결과를 정규화하여 반환합니다.

### Step 6: 결과 반환

에이전트가 반환한 `summary`, `findings`, `verdict`, `counts`를 호출자에게 그대로 전달합니다.
결과 표시 시 다음 헤더를 추가합니다:

```
리뷰 완료
- CLI 도구: {tool}{ / 모델: {model} 있으면}
- 프리셋: {preset}
- 파일: {files_reviewed}
- 판정: {verdict}
- Findings: total {N} (critical {N}, warning {N}, info {N})
```

그 뒤에 `findings` 목록을 severity 순으로 출력합니다.

## 타 플러그인 연동 예시

### specflow에서 명세서 리뷰
```
Skill("xreview:review", "target=specs/fs-login.md preset=spec-fs context=로그인 기능 명세서 1차 초안 검증")
```

### backflow에서 구현 코드 + 명세서 일치성 리뷰
```
Skill("xreview:review", `
  target=src/auth/login.controller.ts,specs/ts-auth.md
  preset=code
  perspective=TS 문서의 API 계약과 컨트롤러 구현이 일치하는지 검증. 특히 에러 코드 매핑과 요청 스키마를 중점적으로 확인.
`)
```

### 직접 호출
```
/xreview:review src/payment/*.ts --perspective "결제 로직의 idempotency와 트랜잭션 경계 검증"
```

## CLI 도구 확장

현재는 `codex`만 공식 지원합니다. 다른 CLI 도구를 추가할 때:

1. `xreview:review-bridge` 에이전트의 "지원 CLI 도구" 섹션에 호출 패턴 추가
2. 이 스킬 문서의 `cli_tool` 가능 값 목록 업데이트
3. 필요 시 프리셋의 관점/포맷을 CLI 도구별로 분기

## 병렬 다중 CLI 리뷰 (Future Work)

여러 CLI 도구를 동시에 호출하여 결과를 집계하는 확장이 설계되어 있습니다.
현재 스킬은 단일 `cli_tool`만 지원하지만, 향후 `cli_tools`(복수), `aggregation`, `quorum` 등의 파라미터가 추가될 예정입니다.

관련 설계 문서: [`../../docs/parallel-review.md`](../../docs/parallel-review.md)

해당 문서는 다음을 다룹니다:
- 신규 `xreview:review-aggregator` 에이전트 구성
- `union` / `consensus` / `weighted` 집계 전략
- 판정(verdict) 합의 및 의견 불일치 표시 형식
- 구현 단계(Phase 1~4) 및 열린 질문들

**현재 단일 CLI 경로는 병렬 도입 이후에도 변경 없이 유지**됩니다.

## 에러 처리

| 상황 | 대응 |
|------|------|
| `target` 누락 | 사용자에게 리뷰 대상 파일을 물어봄 |
| `preset` 감지 실패 | `doc`으로 폴백 + 경고 출력 |
| `preset` 파일 없음 | 에러 메시지 후 중단 |
| `cli_tool` 미지원 | 지원 목록과 함께 에러 출력 |
| review-bridge 에이전트 실패 | 에이전트의 에러를 그대로 전달 |

## 금지 사항

- 리뷰 결과를 스킬 레벨에서 재해석·요약·필터링하지 마세요. review-bridge의 정규화된 출력을 보존합니다.
- 스킬이 직접 CLI 도구를 호출하지 마세요. 반드시 `xreview:review-bridge` 에이전트를 거칩니다(격리 보장).
- 리뷰 findings에 따른 자동 수정을 수행하지 마세요. 수정은 사용자가 명시적으로 요청한 뒤에만 진행합니다.
