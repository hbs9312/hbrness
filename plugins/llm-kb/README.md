# llm-kb

도구 무관 **개인 LLM Wiki**. 사용자가 새로운 개념을 질문하면 Stop 훅이 그 흐름을 캡처해 백그라운드에서 판단·요약·저장하고, 다음에 같은 개념을 마주쳤을 때 즉시 꺼내볼 수 있게 한다.

## 핵심 원칙

- **Storage 중립**: `~/.hbrness/llm-kb/` 아래 단일 markdown 파일. claude·codex 어떤 하네스에서 만들었든 같은 위치에서 읽힌다 (Tier 1).
- **언어 강제 한국어**: 영어 개념도 한국어 설명 + 원어 병기. `lang: ko` 고정.
- **Fire-and-forget**: Stop 훅은 50ms 안에 백그라운드 워커를 띄우고 즉시 return. 메인 채팅 컨텍스트 비오염.
- **재귀 가드**: 워커가 spawn 한 sub-session 의 Stop 훅은 `LLM_KB_WORKER=1` env 와 `stop_hook_active` 플래그로 즉시 빠진다.
- **프로젝트 vs 글로벌 분류**: 워커가 판단해 글로벌 지식만 KB 에 저장하고, 프로젝트 한정 컨텍스트는 skip.

## 디렉토리 구조

```
~/.hbrness/llm-kb/
├── entries/             # 개별 개념 노트 (kebab-slug.md)
├── INDEX.md             # 도메인별 네비게이션
├── links.json           # 백링크/관련 개념 그래프
└── config.yaml          # 사용자 설정 (켜기/끄기, 도메인 화이트리스트 등)
```

## 슬래시 스킬

- `/kb-search <query>` — 키워드 검색
- `/kb-list [domain]` — 최근 / 도메인별 목록
- `/kb-save <개념명>` — 마지막 어시스턴트 응답을 강제로 저장 (자동 판정이 skip 한 경우)

## 훅

- **Claude Code**: `Stop` 훅에서 `kb-judge.py` 가 transcript 마지막 turn 을 정규화 → 사전필터 통과 → `kb-worker.py` 백그라운드 spawn.
- **Codex**: 동일 위치에 codex 형식의 Stop 등가 훅 등록. 워커는 동일.

## 비용 감각

L1 정규식 필터로 대부분 컷, L2 Haiku 판단까지 가도 한 번당 ~$0.0005. 일상 사용 기준 월 600원 수준.

## 미구현 (v1+)

- MCP 서버를 통한 cross-tool read 인터페이스
- 자동 백링크 생성 (그래프화)
- 임베딩 기반 시맨틱 검색
