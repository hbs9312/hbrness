---
name: state-matrix
description: 기능 명세서에서 화면별 상태 매트릭스를 자동 생성합니다. "상태 매트릭스" 요청 시 사용.
argument-hint: [기능 명세서 경로]
tools: [file:read, search:grep, search:glob, file:write]
effort: medium
---

# 상태 매트릭스 생성 (U2)

## 입력: FS ($ARGUMENTS)

## 생성: 각 화면 × 4상태 (정상/로딩/에러/빈)
- 정상: 주 기능 동작 상태
- 로딩: fetch, 업로드, 처리 중
- 에러: AC 에러 안내 시나리오
- 빈: 데이터 없는 초기 상태

## 출력

```yaml
matrix:
  - screen: "{화면명}"
    ref: "FS 4-N"
    states:
      normal: "{설명}"
      loading: "{설명}"
      error: "{설명}"
      empty: "{설명}"
    related_brs: ["{BR-NNN}"]
    related_acs: ["{AC-NNN}"]
```

## 저장: specs/state-matrix-{FS ID}.md
