---
name: sync-tools
description: 구현 계획을 Linear, Notion 등에 동기화합니다. "도구 동기화" 요청 시 사용.
argument-hint: [스프린트 배치 파일 경로]
disable-model-invocation: true
tools: [file:read, search:grep, search:glob, file:write]
effort: high
model: sonnet
---

# 프로젝트 도구 동기화 (P5)

## 입력: P4 스프린트 배치 (승인 완료)

## ★ MCP 연결 확인 ★

이 스킬은 Linear 또는 Notion MCP 서버가 필요합니다.

실행 전 확인:
1. 환경 변수 설정 여부: `LINEAR_API_KEY`, `NOTION_API_KEY`
2. MCP 서버 연결 상태

MCP가 연결되어 있지 않으면 사용자에게 안내하세요:

"도구 동기화에는 Linear 또는 Notion MCP 연결이 필요합니다.
 아래 환경 변수를 설정한 후 다시 시도해주세요:
 - LINEAR_API_KEY: Linear 설정 > API > Personal API Keys
 - NOTION_API_KEY: notion.so/my-integrations 에서 생성
 
 MCP가 연결되지 않은 경우, sync_plan을 파일로 출력하여
 수동으로 이슈를 생성할 수 있습니다."

## ★ 사전 확인 필수 ★
1. sync_plan 출력 (dry-run) → 생성할 이슈 목록 표시
2. 사용자 확인 → "{N}건 생성합니다. 진행?" 
3. 확인 후 실행

## 도구별 매핑
- Linear: task→Issue, sprint→Cycle, milestone→Project
- Notion: 전체 계획→페이지, task→DB 항목

## 저장: specs/PLAN-{YYYY}-{NNN}-sync.md
