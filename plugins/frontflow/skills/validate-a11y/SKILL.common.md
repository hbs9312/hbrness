---
name: validate-a11y
description: 접근성 요구사항을 검증합니다. "접근성 검증", "a11y 체크" 요청 시 사용.
argument-hint: [컴포넌트 또는 페이지 경로] [UI 명세서 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write, shell(npx axe*), shell(npx storybook*)]
effort: high
---

# 접근성 검증 (FV3)

UI 명세서의 접근성 요구사항 vs 구현 코드를 비교 검증합니다.

## 입력

$ARGUMENTS 에서:
1. 구현 코드 경로 → Read
2. UI 명세서 경로 → Read (접근성 섹션)

## 검증 항목

### 1. UI 명세서 대조 (critical)

UI 명세서의 접근성 요구사항을 하나씩 코드에서 확인:

```yaml
명세: 녹음 버튼 aria-label="녹음 시작" / "녹음 중지"
코드에서 확인: aria-label이 상태에 따라 동적으로 변경되는가

명세: 파형 시각화 aria-hidden="true"
코드에서 확인: 해당 요소에 aria-hidden 존재 여부

명세: 포커스 순서: 이름 입력 → 다음 버튼
코드에서 확인: tabIndex 또는 DOM 순서가 일치하는가

명세: 최소 터치 영역 44×44px
코드에서 확인: 버튼/링크의 min-width, min-height 또는 padding
```

### 2. 코드 정적 분석 (warning)

명세서에 없더라도 기본적인 접근성 패턴:

```yaml
- img에 alt 속성 존재
- 폼 요소에 label 연결 (htmlFor 또는 aria-labelledby)
- 색상만으로 정보 전달하지 않음 (아이콘 + 텍스트 병용)
- 모달 열림 시 포커스 트랩 구현
- ESC 키로 모달/다이얼로그 닫기
- 로딩 상태에 aria-live="polite" 또는 role="status"
```

### 3. 도구 기반 자동 검증 (해당 시)

프로젝트에 axe-core가 설치되어 있으면 자동 실행을 시도합니다:

```bash
# axe-core가 있는지 확인
npx axe --version 2>/dev/null
```

사용 가능하면:
- Storybook이 실행 중인지 확인
- axe-core로 각 스토리 URL 스캔
- 결과를 파싱하여 findings에 반영

사용 불가능하면 사용자에게 수동 검증 안내:

```markdown
## 추가 접근성 검증 권장

axe-core가 설치되어 있지 않아 자동 검증을 수행할 수 없습니다.
아래 방법으로 수동 검증을 권장합니다:

1. **Storybook a11y addon**: 설치되어 있다면
   Storybook에서 Accessibility 탭 확인

2. **axe DevTools**: 브라우저 확장 프로그램으로 페이지 스캔
   https://www.deque.com/axe/devtools/

3. **키보드 네비게이션 테스트**: Tab 키로 전체 페이지 이동
```

## 출력

```yaml
검증 유형: FV3 (접근성)

findings:
  - id: "FV3-001"
    severity: critical
    file: "{파일}"
    spec_requirement: "{UI 명세서 요구사항 원문}"
    implementation: "{현재 코드 상태}"
    issue: "{불일치 내용}"
    suggestion: "{수정 제안}"

summary:
  spec_requirements_checked: {N}
  matched: {N}
  mismatched: {N}
  pass: {true | false}
```
