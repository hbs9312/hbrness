---
name: validate-code
description: 생성된 프론트엔드 코드의 품질을 검증합니다. "코드 검증", "코드 리뷰" 요청 시 사용.
argument-hint: [검증할 파일 또는 디렉토리 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
---

# 코드 품질 검증 (FV1)

ultrathink

생성된 프론트엔드 코드가 프로젝트 컨벤션과 품질 기준을 충족하는지 검증합니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md)

## 입력

$ARGUMENTS 의 파일/디렉토리를 Read/Glob으로 읽으세요.

## ★ specflow V 스킬과의 차이 ★

specflow V 스킬은 `context: fork`로 완전 격리합니다.
FV1은 격리하지 않습니다. 이유:
- 코드 검증은 "어떤 컴포넌트를 어떤 맥락에서 만들었는지"를 알아야 정확
- "이 컴포넌트가 SpeakerCard인데 StatusIcon을 import하지 않았다"는
  맥락 없이는 판단 불가
- 단, 시각적 검증(FV2)은 사람이 하므로 격리 문제 없음

## 검증 항목

### 1. 컨벤션 준수 (critical)

```yaml
파일 위치:
  - 컴포넌트가 frontend.md의 component_dir 하위에 있는가
  - 페이지가 frontend.md의 page_dir 하위에 있는가
  - 훅이 hook_dir에 있는가

네이밍:
  - 파일명이 frontend.md의 naming 컨벤션(PascalCase 등)을 따르는가
  - export된 컴포넌트명이 파일명과 일치하는가

구조:
  - frontend.md의 component_pattern과 형태가 일치하는가
  - barrel_exports 설정에 따라 index.ts가 있는가
  - co_location 설정에 따라 테스트/스토리가 같은 폴더인가

임포트:
  - 절대 경로/앨리어스 컨벤션을 따르는가
  - 순환 의존이 없는가
```

### 2. 재사용성 (warning)

```yaml
중복 구현:
  - 기존 컴포넌트 레지스트리(또는 design_system_package)에
    이미 있는 것을 재구현하지 않았는가
  - 새 컴포넌트 내에서 기존 컴포넌트를 사용할 수 있었는데
    HTML로 직접 구현하지 않았는가

확장성:
  - Props에 className이 포함되어 있는가
  - ...rest props를 전달하는가
  - Props가 과도하게 optional이지 않은가
```

### 3. 토큰 준수 (critical)

```yaml
하드코딩 탐지:
  - 색상: #hex, rgb(), hsl() 직접 사용 여부
  - 크기: 숫자+px/rem 직접 사용 여부 (토큰 대신)
  - 폰트: font-size, font-weight 직접 지정 여부

방식별 확인:
  tailwind: 임의 값 [] 사용 최소화, 커스텀 유틸리티 사용 여부
  css-modules: var(--token) 참조 여부
  styled-components: theme 객체 참조 여부
```

### 4. 타입 안전성 (critical)

```yaml
- any 사용 = 0건
- as 타입 단언 최소화
- API 응답 타입이 TS 명세서 스키마와 일치하는가
- Props 인터페이스가 완전한가 (필수/선택 구분 적절)
- event handler 타입이 명시적인가
```

### 5. 접근성 기본 (warning)

```yaml
- 인터랙티브 요소에 aria-label 또는 접근 가능한 텍스트 존재
- img에 alt 속성
- button이 아닌 요소에 onClick 사용 시 role + tabIndex
- 포커스 관리가 필요한 곳에 구현되었는가
```

### 6. Storybook 커버리지 (warning)

```yaml
- 컴포넌트에 대응하는 .stories 파일이 존재하는가
- UI 명세서의 모든 상태가 스토리로 있는가
- 모바일 viewport 스토리가 있는가
```

## 출력

```yaml
검증 대상: {파일/디렉토리}
검증 유형: FV1 (코드 품질)

findings:
  - id: "FV1-001"
    severity: critical | warning | info
    file: "{파일 경로}"
    line: {라인 번호} (가능하면)
    issue: "{문제}"
    suggestion: "{수정 제안}"

summary:
  files_checked: {N}
  total_findings: {N}
  critical: {N}
  warning: {N}
  pass: {true | false}
```
