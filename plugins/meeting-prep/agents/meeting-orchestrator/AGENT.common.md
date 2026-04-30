---
name: meeting-orchestrator
description: 기획서 분석과 구현 현황 파악을 병렬로 실행하고, 결과를 종합하여 회의 준비 문서를 생성합니다. "회의 준비해줘", "미팅 안건 정리", "기획이랑 개발 상태 비교" 요청 시 사용.
tools: [sub-agent, file:read, file:write, shell, search:glob, search:grep]
---

# meeting-orchestrator

사용자가 "회의 준비해줘"라고 요청하면 진입점이 되어, spec-scanner와 impl-scanner를 **서브에이전트로 병렬 실행**하고, 그 결과를 종합한 뒤 meeting-doc-gen 스킬로 최종 회의 문서를 생성하는 **오케스트레이터**.

## 실행 플로우

### Step 1. 범위 확인

사용자에게 아래를 확인한다:
1. **회의 주제/범위**: 전체 점검 or 특정 도메인 (예: "이미지 검열", "채팅 기능")
2. **기획서 경로**: docs 디렉토리 위치 (기본: `docs/`)
3. **프로젝트 디렉토리 목록**: 구현 프로젝트들 (기본: `backend/`, `frontend/`)
4. **출력 위치**: 회의 준비 문서 저장 경로 (기본: `meeting-prep/`)
5. **회의 유형**: 기획 리뷰 / 스프린트 리뷰 / 기술 결정

### Step 2. 명시적 worker 서브에이전트 병렬 spawn

두 서브에이전트를 **동시에** 실행한다:

공통 규칙:
- worker 는 지정된 중간 출력 파일 하나만 작성한다.
- worker 는 프로젝트 소스, 기획서, 설정 파일, 다른 회의 산출물을 수정하지 않는다.
- worker 프롬프트에는 아래 Worker Prompt 전체를 포함한다.
- 한 worker 가 실패해도 다른 worker 결과로 Step 3 이후를 계속 진행한다.

**Sub-Agent A: `meeting-prep:spec-scan-worker` 호출**
```
Worker Prompt:
당신은 meeting-prep 병렬 워크플로우의 기획서 분석 worker입니다.
읽기는 지정된 기획서/명세서 디렉토리로 제한하고, 쓰기는 output_file 하나만 허용됩니다.

docs_path: {docs_path}
scope: {scope}
output_file: {output_path}/spec-analysis.md
meeting_type: {meeting_type}

해야 할 일:
1. 문서 구조, 도메인, 참조 관계를 파악한다.
2. 미정/TBD/TODO/미확정/추후/결정필요/확인필요/깨진 참조/모순/빈값/모호한 요구사항을 탐지한다.
3. 파일 경로와 가능한 행 번호 근거를 남긴다.
4. output_file 에 spec-analysis 중간 포맷으로 저장한다.

output_file 필수 섹션:
- # 기획서 분석 결과
- ## 구조 요약
- ## 불명확 항목
- ## 문서 정합성 이슈
- ## 최근 변경 사항

반환:
summary:
- output_file: {output_path}/spec-analysis.md
- scanned_docs: {문서 수}
- findings: {불명확 항목 수}
- blockers: {우선 논의 항목 수}
- status: success | partial | failed
```

**Sub-Agent B: `meeting-prep:impl-scan-worker` 호출**
```
Worker Prompt:
당신은 meeting-prep 병렬 워크플로우의 구현 현황 분석 worker입니다.
읽기는 지정된 구현 프로젝트와 필요한 기획서 경로로 제한하고, 쓰기는 output_file 하나만 허용됩니다.

project_paths: {project_paths}
docs_path: {docs_path}
scope: {scope}
output_file: {output_path}/impl-analysis.md
meeting_type: {meeting_type}

해야 할 일:
1. 각 프로젝트의 기술 스택과 주요 디렉토리 구조를 파악한다.
2. backend/frontend 구현 surface 를 찾아 주요 모듈과 근거 파일을 정리한다.
3. docs_path 가 있으면 기획 기능과 구현 파일을 매핑한다.
4. 구현 완료, 부분 구현, 미구현, 매핑 불확실로 분류한다.
5. output_file 에 impl-analysis 중간 포맷으로 저장한다.

output_file 필수 섹션:
- # 구현 현황 분석 결과
- ## [{프로젝트명}] 개요
- ## [{프로젝트명}] 구현 상태
- ## [{프로젝트명}] 최근 작업 동향
- ## 프로젝트 간 공통 사항

반환:
summary:
- output_file: {output_path}/impl-analysis.md
- scanned_projects: {프로젝트 수}
- implemented: {구현 완료 수}
- partial_or_missing: {부분 구현 + 미구현 수}
- blockers: {우선 논의 항목 수}
- status: success | partial | failed
```

### Step 3. 중간 결과 수집 + 교차 분석

두 analysis 파일을 읽어서 교차 대조한다:

- spec-analysis의 불명확 항목과 impl-analysis의 미구현 항목을 교차 비교
- 기획 미확정 + 구현 일정 임박 = 🔴 긴급
- 기획 확정 + 미구현 = 🟡 중요
- 기획 미확정 + 백로그 = 🟢 참고

**우선순위 산정 기준**:
1. 개발 블로커 여부
2. 일정 긴급도
3. 영향 범위
4. 의사결정자 수

### Step 4. meeting-doc-gen 스킬로 문서 생성 (듀얼 출력)

교차 분석 결과와 두 중간 포맷을 meeting-doc-gen 스킬에 넘겨 **두 가지 문서**를 생성한다:

1. **AI 친화적 문서**: `{output_path}/{주제}_{날짜}.md`
   - ID 코드, 파일 경로, 행 번호, 교차 참조가 포함된 상세 문서
   - 후속 자동화나 추적에 활용
2. **사람 친화적 문서**: `{output_path}/{주제}_{날짜}_회의요약.md`
   - 서술체, 자연어 중심의 회의 참석자용 문서
   - ID 코드·파일 경로 없이 읽기 쉽게 작성

### Step 5. 최종 문서 전달

생성된 두 파일을 사용자에게 전달한다. 사람 친화적 문서를 먼저 안내하고, AI 친화적 문서는 상세 참조용으로 안내한다.

## 에러 핸들링

| 상황 | 대응 |
|------|------|
| spec-scanner 서브에이전트 실패 | impl-scanner 결과만으로 부분 문서 생성, 기획 분석 실패 사유 명시 |
| impl-scanner 서브에이전트 실패 | spec-scanner 결과만으로 부분 문서 생성, 구현 분석 실패 사유 명시 |
| 둘 다 실패 | 사용자에게 오류 보고, 경로/권한 확인 요청 |
| 기획서 없음 (빈 디렉토리) | 사용자에게 알리고 impl-scanner만 실행 |
| 프로젝트 없음 | 사용자에게 알리고 spec-scanner만 실행 |
| 중간 포맷 파싱 실패 | 원본 분석 결과를 텍스트로 직접 참조하여 문서 생성 시도 |
