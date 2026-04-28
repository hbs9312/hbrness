---
name: validate-security
description: 외부 공개 백엔드 서비스의 보안 취약점을 클린룸 에이전트로 검증하고 durable security review report를 생성합니다. "보안 검증", "security review", "취약점 점검", "SQLi/CSRF/IDOR 점검", "public API 보안 리뷰" 요청 시 사용.
argument-hint: [검증할 파일 또는 디렉토리 경로] [기술 명세서 경로 optional]
disable-model-invocation: true
tools: [file:read, sub-agent]
effort: high
---

# 보안 검증 (BV3-security) — 에이전트 디스패처

ultrathink

이 스킬은 클린룸 보안 검증 에이전트를 호출하는 디스패처입니다.
직접 검증을 수행하지 않습니다. 모든 판단과 report 작성은 격리된 에이전트가 합니다.

기존 `backflow:validate-code` 의 기본 보안 검사는 유지합니다. 이 스킬은 외부 공개 서비스 기준의 심층 보안 검토와 durable report 생성을 담당합니다.

## 입력

명령 형식:

```text
backflow:validate-security [target path] [TS path optional]
```

- 첫 번째 인자: 검증할 backend 파일 또는 디렉토리
- 두 번째 인자: 기술 명세서(TS) 경로. 없으면 에이전트가 `specs/TS*.md`, `specs/TS/**/*.md` 를 자동 탐색합니다.

target path 가 없으면 사용자에게 target path 를 요청하고 중단하세요.

## 에이전트 호출

서브에이전트로 `backflow:validator-security` 에이전트를 호출합니다.

프롬프트 구성:

```text
검증 대상: {$ARGUMENTS 첫 번째 target 의 절대 경로}
기술 명세서: {$ARGUMENTS 두 번째 TS 절대 경로 또는 "자동 탐색"}
백엔드 프로젝트 컨텍스트: ${SKILL_DIR}/../../context/backend.md
서비스 레지스트리: <project-root>/.backflow/service-registry.md (있으면)
결과 저장: specs/reviews/{target-slug}-BV3-security-{timestamp}.md
```

규칙:
- `timestamp` 형식: `YYYYMMDD-HHmmss`
- `target-slug`: target 을 repo 상대 경로로 만든 뒤 `/`, 공백, 확장자를 `-` 로 정규화
- 리포트는 project-local Tier 0 산출물입니다.

## 에이전트 요구사항

에이전트는 다음 입력만 기준으로 판단합니다:

1. target backend files/directories
2. `backend.md`
3. `.backflow/service-registry.md` (있으면)
4. TS §3 API, §4 error map, §7 nonfunctional/security, §9 upload, §10 webhook (있으면)

검증 범위:
- authentication / authorization
- input / output safety
- secrets / sensitive data
- injection risks
- transport / browser-facing controls
- file upload / webhook security
- dependency / config red flags

## 결과 전달

에이전트가 반환한 summary 블록을 그대로 출력합니다.
코드 수정 제안은 report 에만 남기고, 이 스킬이 project code 를 직접 patch 하지 않습니다.

## 후속 처리

- `security_pass=false` 이면 `patch-backend` 또는 수동 수정의 입력으로 report 를 사용합니다.
- warning 만 있는 경우에도 public service 는 배포 전 사람이 residual risk 를 확인해야 합니다.
