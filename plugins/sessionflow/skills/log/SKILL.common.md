---
name: log
description: "코딩 에이전트 대화 기록을 찾아본다. sessionflow 훅이 Claude Code / Codex / Grok / Devin 의 transcript 를 비밀값을 가려 backend 에 모아 두는데, 이 스킬은 그 기록을 도구·PC 와 상관없이 같은 형식으로 목록·열람·검색하고, 훅이 없는 곳(웹 채팅 등)의 대화는 요약을 남긴다. 사용자가 '대화 기록', '로그 보여줘', '지난 세션', '예전에 뭐라고 했지', '어제 무슨 얘기했지', 'codex 랑 한 대화', '대화 검색', '대화 저장', '이 대화 남겨줘', '대화 기록이 안 모이는 것 같아', 'log', '/log' 등을 말하면 트리거. Usage: /log [list | show <session> | search <검색어> | save [제목] | status]"
model: sonnet
---

# Log Skill

sessionflow 훅은 turn 이 끝날 때마다·세션이 끝날 때 각 도구의 transcript 원본을 backend 의 `logs/<repo-key>/<tool>/<session>/` 에 올린다(비밀값은 가린 뒤). 이 스킬은 그 기록을 읽는다. 도구마다 형식이 다른 transcript 를 같은 형식으로 바꿔 보여주므로, 어느 도구에서 한 대화든 같은 방법으로 찾는다.

| 하는 일 | 명령 |
|---|---|
| 이 저장소의 세션 목록 (최근 것부터) | `list` |
| 세션 하나 열람 | `show <session>` |
| 대화 내용 검색 | `search <검색어>` |
| 훅이 없는 곳의 대화를 남기기 | `save [제목]` |
| 이 PC 의 수집이 잘 되는지 | `status` |

## 스크립트

이 문서에서 `LOG` 는 다음 명령을 뜻한다:

```bash
python3 "${SKILL_DIR}/../../scripts/sflog.py"
```

- `LOG list [--all-repos] [--tool claude|codex|grok|devin|manual] [--limit N]` — 세션 목록. 한 세션이 두 줄이다: `갱신시각 도구 session-id 브랜치 · host · segment 수 [· N세대] [· 진행 중]` (N세대: transcript 가 다시 쓰여 마지막 세대만 보인다) 과 그 아래 첫 사용자 말(제목).
- `LOG show <session> [--no-tools] [--full] [--out <파일>]` — session id 앞부분만 적어도 된다. 형식은 `### user` / `### assistant` 문단, 도구 호출은 `→ 이름: 입력`, 결과는 `← 결과`. 도구 입력은 300자, 결과는 500자에서 자른다(`--full` 이면 안 자른다). `--no-tools` 는 대화만.
- `LOG search <검색어> [--days N] [--regex] [--tool T] [--all-repos]` — 최근 N일(기본 30) 세션에서 찾는다. 세션마다 맞는 곳을 5개까지 앞뒤 80자로 보여준다. 대소문자는 가리지 않는다. 처음 찾을 때는 기간 안의 세션을 로컬 색인에 넣느라 오래 걸리고, 그다음부터는 바뀐 세션만 넣는다.
- `LOG save --title "<제목>" --file <파일>` — 파일 내용을 `manual` 기록으로 올린다. 비밀값은 스크립트가 가린다.
- `LOG status` — 이 PC 의 수집 현황: `BACKEND=`, `SESSIONS=`, `WAITING=`(아직 안 올린 세션과 양), `LAST_COLLECT=`, `FAILURES_24H=`(최근 실패 3줄), `AGE=`, `GITLEAKS=`.

list 의 `· 진행 중` 은 끝났다는 기록이 없는 세션이고, `· 끊김(추정)` 은 그런데 12시간 넘게 아무것도 올라오지 않은 세션이다 (터미널을 닫았거나 PC 가 꺼져 세션 끝 훅이 오지 못했다고 본다). 훅은 작은 turn 을 모아서(64KB 또는 5분) 올리므로 진행 중인 세션의 마지막 몇 turn 은 아직 안 보일 수 있다 — 세션이 끝나면 다 올라간다. show 끝에 `> 읽지 못한 레코드: …` 가 붙으면 도구가 transcript 형식을 바꿔 일부를 못 읽은 것이다 — 사용자에게 그대로 알린다.

기본 범위는 **현재 저장소**(origin remote 로 가린다)다. 다른 저장소의 기록이면 `--all-repos` 를 붙인다.

출력이 `LOG=off` 또는 `SAVE=off` 로 시작하면 backend 가 없는 PC 다. 사용자에게 `sfstate.py init --backend …` 로 backend 를 정해야 기록이 모인다고 한 줄로 알리고 멈춘다.

출력이 `LIST=failed (…)`·`SHOW=failed (…)`·`SEARCH=failed (…)`·`SAVE=failed (…)` 면 괄호 안 사유를 그대로 알리고 멈춘다. 사유에 `age.key` 가 나오면 암호화한 저장소의 키가 이 PC 에 없거나 다른 것이다 — 저장소를 만든 PC 의 `~/.hbrness/age.key` 를 같은 자리에 복사해야 읽을 수 있다.

## 인자

`$ARGUMENTS` 또는 사용자 요청에서 고른다.

- 비었거나 `list` → **list**
- `show <session>` 또는 사용자가 특정 세션을 보자고 함 → **show**
- `search <말>` 또는 "예전에 X 얘기했던 거", "어디서 Y 했더라" → **search**
- `save [제목]` 또는 "이 대화 남겨줘" → **save**
- `status` 또는 "기록이 안 모이는 것 같아", "수집 되고 있어?" → **status** — `LOG status` 출력을 보여주고, `FAILURES_24H` 가 0 이 아니면 마지막 실패 줄의 사유를 한 줄로 짚는다.

## list

```bash
LOG list
```

출력을 그대로 보여준다. 사용자가 "codex 로 한 것만", "다른 저장소 것도" 처럼 좁히거나 넓히면 `--tool`, `--all-repos`, `--limit` 을 붙인다.

## show

세션 기록은 수만 자가 넘기 쉽다. **화면에 바로 출력하지 말고 파일로 받은 뒤 필요한 부분만 읽는다.**

```bash
LOG show <session> --out "${TMPDIR:-/tmp}/sflog-<session>.md"
```

1. 출력 `SHOW=<파일> (<session> · 사용자 말 N개 · M자)` 로 크기를 본다.
2. 사용자가 물은 것에 맞춰 그 파일을 읽는다 — 전체 흐름이면 `### user` 줄 위주로 훑고, 특정 부분이면 grep 으로 위치를 찾아 그 근처만 읽는다. 대화만 필요하면 `--no-tools` 로 다시 받는다.
3. 요약하거나 물은 것에 답한다. 기록 원문을 길게 옮겨 붙이지 않는다.

`SHOW=none` 이면 이 저장소에 그런 세션이 없다 — `--all-repos` 로 다시 찾는다. `SHOW=ambiguous` 면 후보 목록이 나오니 사용자에게 고르게 하거나 id 를 길게 적어 다시 부른다.

## search

```bash
LOG search "<검색어>"
```

- 결과는 세션마다 `list` 와 같은 두 줄 + 맞은 곳 몇 줄이다. 맞은 세션이 많으면 상위 몇 개만 추려 보여준다.
- 더 자세히 보려면 그 세션을 **show** 로 연다.
- 못 찾으면 `--days 90`, `--all-repos`, 다른 표현 순으로 넓혀 본다. 여러 표현을 한 번에 찾으려면 `--regex` 로 `A|B` 를 쓴다.

## save

훅을 걸 수 없는 곳(웹 채팅, 훅을 지원하지 않는 도구)에서 한 대화를 남긴다. 이 스킬을 부른 지금 세션의 대화를 남기는 경우가 대부분이다. 훅이 도는 도구(Claude Code / Codex / Grok / Devin)의 세션은 이미 원본이 모이므로 save 할 필요가 없다 — 사용자가 그래도 원하면 요약 메모로 남긴다.

1. 대화를 아래 형식으로 정리해 임시 파일에 쓴다. 모델이 다시 쓴 기록이라 원본이 아니라는 점을 첫 줄에 밝힌다.

   ```markdown
   # <제목>

   > 요약 기록 (원문 아님) · 도구: <claude.ai 웹 / ChatGPT / …> · 날짜: <YYYY-MM-DD>

   ## 무엇을 했나
   ## 결정한 것
   ## 남은 일
   ## 원문 발췌
   (꼭 남겨야 할 문장·명령·코드만, 있으면)
   ```

2. 올린다.

   ```bash
   LOG save --title "<제목>" --file "${TMPDIR:-/tmp}/sflog-save.md"
   ```

3. `SAVED=<id>` 를 사용자에게 알린다. 나중에 `LOG show <id>` 로 볼 수 있다.

제목은 사용자가 준 것을 쓰고, 없으면 대화 주제로 한 줄을 짓는다.

## 가이드라인

- 기록에는 다른 세션의 diff·명령·에러가 들어 있다. 사용자가 물은 범위만 읽고 답한다.
- 비밀값은 업로드 때 가려져 `[REDACTED:<종류>]` 로 보인다. 원래 값을 추측하거나 되살리려 하지 않는다.
- save 파일에 토큰·비밀번호·자격증명을 적지 않는다 (스크립트가 가리긴 하지만 패턴에 안 걸리는 값도 있다).
- 진행 중인 세션(`· 진행 중`)은 마지막 turn 까지 올라와 있다. 지금 이 세션의 기록은 이번 turn 이 끝난 뒤에 올라간다.
