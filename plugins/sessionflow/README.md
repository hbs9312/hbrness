# sessionflow

세션 간 컨텍스트를 보존·재개하기 위한 스킬 모음. followup 과 handoff 는 **경로가 아니라 저장소(origin remote)를 기준**으로 저장하고 Terraform backend 처럼 원격 저장소(S3 API)와 동기화하므로, 다른 도구(Claude / Codex / Grok / Devin)는 물론 **다른 PC** 에서도 같은 내용을 이어 작업할 수 있습니다. `phase-run` 은 여기서 한 발 더 나아가, 페이즈 경계마다 컨텍스트를 비우고 새 세션이 핸드오프를 읽어 자동으로 이어받게 합니다.

## 스킬

| 스킬 | 트리거 | 역할 | 범위 |
|---|---|---|---|
| `followup` | `/followup [list\|-m\|-o] [메시지]` | 현재 세션에서 발견한 **후속 조치** 항목을 `followups/` 디렉토리(항목별 상세 파일 + 생성되는 `INDEX.md`)에 누적 기록. TODO·결정 보류·아이디어·발견된 이슈. 기본 동작은 merge. `list` 는 현황만. | 저장소 단위 (워크트리·세션·PC 무관) |
| `followup-clear` | `/followup-clear [-y]` | 누적된 followup 을 한 번에 비움. `followups/` 디렉토리 삭제(다른 PC 에도 반영) + 양쪽 `MEMORY.md` 의 `## Followups` 섹션 제거. | 저장소 단위 |
| `handoff` | `/handoff [load\|-m\|-o] [메시지]` | 현재 세션의 **in-flight 컨텍스트** (편집중 파일·마지막 명령·실패한 에러·다음 한 줄) 를 `handoffs/<branch>.md` 로 직렬화. 다음 세션이 즉시 이어받을 수 있게. `load` 는 다른 PC 에서 남긴 핸드오프를 불러온다. | 저장소 + 브랜치 단위 |
| `handoff-clear` | `/handoff-clear [-y] [--all]` | 현재 브랜치의 핸드오프 삭제(다른 PC 에도 반영) + `MEMORY.md` 의 해당 라인 정리. `--all` 로 저장소 전체 핸드오프 일괄 정리. | 저장소 + 브랜치 단위 (또는 `--all` 시 저장소 전체) |
| `phase-run` | `/phase-run [continue\|pause\|resume\|stop\|status\|reset] \| <계획>` | 작업을 페이즈로 분해해, 각 페이즈가 끝나면 자기 pane 에 `/clear` + `/phase-run continue` 를 자동 주입 → 새 세션이 `HANDOFF.md` 를 읽고 다음 페이즈를 이어받게 한다. 컨텍스트 누적을 경계마다 리셋. 자동 커밋은 하지 않음. | 워크트리 단위 (PC 로컬, 동기화 안 함) |
| `phase-loop` | `/phase-loop [continue\|pause\|resume\|stop\|status\|reset] \| <구현 계획>` | `phase-run` 엔진 위에 각 페이즈 경계마다 **구현 → xreview 리뷰 N라운드 → 커밋 → push → PR → 핸드오프** 를 끼워 넣어, 모든 페이즈(=PR 단위)가 끝날 때까지 자동 반복하는 루프. 개인=브랜치 직접, 팀=워크트리+스택 PR. 커밋은 모드별(팀=무인 / 개인=확인). | 워크트리 단위 (PC 로컬, phase-run 과 분리된 `phase-loop` 상태 네임스페이스, HANDOFF 는 공유) |

### phase-run 동작 개요

```
/phase-run <계획>
  └ 페이즈 분해 → 1회 확인 → init → Phase 1 작업
  └ 완료: HANDOFF.md 작성·검증 → advance → (DELAY초 후) detached injector 가 자기 pane 에
           /clear + /phase-run continue 주입
[새(비워진) 세션] /phase-run continue → HANDOFF.md 읽고 Phase 2 … cursor>total 이면 종료
```

- **자기 pane 주입**: `$TMUX_PANE`(이 프로세스가 사는 pane)을 1순위로 사용 — `tmux display-message`(사용자가 보는 pane)는 여러 세션 환경에서 엉뚱한 세션을 clear 할 수 있어 쓰지 않음.
- **무인이되 멈출 수 있음**: 경계마다 차단형 확인은 없지만, `/phase-run pause` 한 줄로 예약된 자동 전진을 취소할 수 있음(`resume` 으로 재개).
- **상태**: `~/.hbrness/sessionflow/<project-key>/[worktrees/<wt>/]phases/` (`state.env` + `phases.tsv` + `hooks/` + `gates.tsv`), 로직은 전부 `scripts/phaseflow.sh`.
- **Codex**: clear 기본 `/new` + CSI-u Enter 제출. 버전이 다르면 `init --clear-cmd` 로 override.

### phase-run stage + hook (커스텀 워크플로우)

페이즈 경계 리셋 엔진은 그대로 두고, **각 페이즈 안에서 밟을 "상태(stage)" 들을 정의하고 stage 마다 훅을 붙일 수 있다.** 기본값은 stage 하나(`work`)·훅 없음이라 위 흐름과 100% 동일하며, 필요할 때만 켠다.

- **stage**: 한 페이즈가 *한 turn 안에서* 순서대로 밟는 단계. `/clear` 는 stage 마다가 아니라 페이즈 경계에서만.
- **shell 훅**: 엔진이 직접 실행. 게이트면 `exit≠0` 시 `advance` 거부(테스트·린트·타입체크 통과 강제).
- **prompt 훅**: 그 stage 에서 LLM 이 읽어 수행할 지침(예: xreview, CHANGELOG 갱신).
- **게이트**: `--gates auto`(shell 훅 있는 stage) 또는 명시. `advance` 가 현재 페이즈의 게이트 통과를 확인, 미실행/실패면 거부(`--force` 우회).
- **선언**: `hooks.spec`(아래 포맷)을 `HANDOFF.md` 와 같은 디렉토리에 두고 `load-hooks` 로 적용. 페이즈별 override(`[stage@N]`)도 가능. 한 줄짜리는 `set-hook`.

```
# hooks.spec — phase-run / phase-loop 공용 훅 선언
stages: work, verify, ship          # (선택) STAGES 재정의
gates:  verify                      # (선택) auto | 토큰 목록

[work].prompt
구현. HANDOFF 의 Next Action 부터.
[end]

[verify].shell
npm run typecheck && npm test       # 게이트: 실패하면 advance 거부
[end]

[ship@2].shell                      # Phase 2 전용 override
echo deploy-staging
[end]
```

블록은 정확히 `[end]` 로 닫고 `#` 주석·빈 줄은 무시. 잘못된 stage·미닫힘 블록은 **원자적으로 거부**(기존 스토어 보존). 훅 정의는 디스크(Tier 1)에 박혀 `/clear` 후 fresh 세션도 본다 — 비밀값은 적지 말 것(Codex 도 같은 파일을 읽음). 바로 쓸 수 있는 프리셋은 `skills/phase-run/examples/*.hooks.spec` 참고.

### phase-loop 동작 개요

```
/phase-loop <구현 계획>
  └ 모드 추정→확인 → 페이즈(=PR 단위) 분해→1회 확인
  └ 개인: 그 자리에서 init → Phase 1
  └ 팀:   워크트리+첫 브랜치 생성 → PHASES.md 스테이징 → "cd 후 /phase-loop start" 안내 후 멈춤(수동 부트스트랩)
[각 페이즈] (이미 이번 브랜치 위) 구현 → xreview N라운드(깨끗하면 조기종료) → 커밋(팀=무인/개인=확인) → push → PR(stack base) → [팀] 다음 페이즈 stacked 브랜치 cut → HANDOFF 작성 → advance
  └ advance → (DELAY초 후) /clear + /phase-loop continue 자동 주입 → 새 세션이 다음 페이즈
[모든 페이즈 완료] 종료 보고(생성된 PR·미해결 followup)
```

- **엔진 재사용**: 상태머신·tmux 주입은 `phase-run` 의 `scripts/phaseflow.sh` 를 그대로 쓰되, `PHASEFLOW_STATE_DIR_NAME=phase-loop` 로 상태를 분리한다(HANDOFF.md 경로는 워크트리 단위라 공유). 보조 로직(모드 감지·워크트리 생성·리뷰 워크트리·경로·forward)은 `skills/phase-loop/scripts/loop.sh`.
- **stage 머신 위에서**: 한 페이즈의 파이프라인은 stage 프리셋(`skills/phase-loop/phase-loop.hooks.spec`)으로 표현된다 — `implement → xreview → verify → commit → ship → cut → handoff`. init 때 `pf load-hooks` 로 로드하고, 각 stage 를 `pf run-hooks` 로 밟는다. `verify` 는 커밋 전 **기계적 게이트**(기본 `true`, 프로젝트 검증으로 교체 시 통과해야 advance). 프리셋 없이 §1~§9 를 직접 따라도 동작은 동일.
- **모드별 자동화**: 팀(워크트리+PR)은 PR 이 리뷰 게이트라 무인, 개인(브랜치 직접)은 커밋 전 확인. `--auto`/`--confirm` 로 override.
- **스택 PR (각 페이즈 = 독립 PR)**: 같은 워크트리에서 브랜치만 페이즈마다 직전 브랜치 HEAD 에서 분기 → PR base 를 직전 브랜치로. 다음 페이즈 브랜치는 **완료 프로토콜에서 미리 cut**(워킹트리를 그 위로 옮긴 뒤 clear)하므로 fresh 세션은 이미 자기 PR 브랜치 위에서 깨어난다. 첫 페이즈만 워크트리 생성 시 잘린다. bottom-up 머지·rebase 캐스케이드는 **루프 밖**(사람/도구) 책임.
- **루프 중 PR 피드백**: 루프 워크트리는 이번 페이즈 브랜치를 잡고 있으므로 체크아웃을 갈아타지 않는다. 이전 PR 의 피드백은 `loop.sh review-worktree --branch <PR브랜치>` 로 만든(있으면 재사용) **리뷰 전용 워크트리**에서 별도 세션으로 처리하고, 루프가 도는 동안엔 **append-only 커밋**만 한다(rebase 는 pause 후 또는 루프 종료 후). 루프가 쥔 브랜치·dirty 워크트리는 스크립트가 거부한다.
- **상태**: `~/.hbrness/sessionflow/<project-key>/[worktrees/<wt>/]phase-loop/` + 계획은 같은 디렉토리의 `PHASES.md`.

## followup vs handoff — 언제 무엇을 쓰는가

| | `followup` | `handoff` |
|---|---|---|
| 시나리오 | "이 버그 발견했는데 이번엔 못 고치겠다 — 나중에 처리해야 됨" | "지금 빌드 에러 잡는 중인데 컨텍스트 길어져서 끊김 — 새 세션에서 그대로 이어가야 함" |
| 누가 읽나 | 다음 세션 시작 시점, 또는 백로그 정리 시점 | 바로 다음 세션 — 그 자리에서 작업 재개 |
| 수명 | 항목별로 Resolved 처리하며 영속 누적 | 작업 재개 후 보통 삭제 |
| 저장 | `followups/<slug>.md` (1 디렉토리 per 저장소) | `handoffs/<branch>.md` (1 per 브랜치) |

## 저장 경로 — 저장소 기준 + PC 간 동기화

followup / handoff 는 `scripts/sfstate.py` 가 경로를 정하고, `scripts/sfbackend.py` 가 동기화한다. Terraform backend 처럼 원격은 key → 내용 저장소이고 `~/.hbrness/state/` 는 그 캐시다.

```
~/.hbrness/
├── backend.json                          # backend 설정 (Terraform 의 backend 블록 역할)
├── credentials.json                      # s3 자격증명 (mode 600, state 밖)
└── state/                                # 원격의 로컬 캐시 (PC 마다 하나)
    ├── <host>/<owner>/<repo>/            # 저장소 키 = origin remote URL 정규화 (예: github.com/hbs9312/hbrness)
    │   ├── followups/
    │   │   ├── <slug>.md                 # 항목 하나 = 파일 하나 (frontmatter 가 진실원, summary = INDEX 한 줄 설명)
    │   │   ├── _config.json              # 선택: {"resolved_keep": 10}
    │   │   └── INDEX.md                  # 생성물 — 올리지 않고 각 PC 에서 다시 만든다
    │   └── handoffs/
    │       ├── main.md
    │       └── feat/login.md             # 브랜치 feat/login
    ├── _local/<경로키>/                   # remote 없는 프로젝트 — 이 PC 에만
    ├── _conflicts/                       # 충돌 때 비켜 둔 이 PC 의 버전 — 이 PC 에만
    └── .sfstate/manifest.json            # 파일마다 마지막으로 맞춘 원격 etag 와 내용 해시

<bucket>/<prefix>/
├── .sfbackend                            # 저장소 ID — 없으면 원격에 닿지 못한 것으로 본다
└── repos/<host>/<owner>/<repo>/{followups,handoffs}/…
```

- **저장소 키**: `git@github.com:o/r.git`, `https://github.com/o/r`, `ssh://git@github.com:22/o/r.git` 모두 `github.com/o/r` 로 같다. clone 경로가 PC 마다 달라도 같은 저장소면 같은 디렉토리를 쓴다.
- **브랜치 기준 핸드오프**: 워크트리 폴더 이름은 PC 마다 다르지만 브랜치는 push 하면 같다. git 은 한 브랜치를 두 워크트리에 동시에 체크아웃하지 못하게 막으니 한 PC 안에서도 겹치지 않는다.
- **동기화**: 스킬이 읽기 전에 `sfstate.py prepare`(pull), 쓰고 나서 `sfstate.py sync`. pull 은 원격 목록에서 etag 가 바뀐 것만 받고, sync 는 로컬에서 내용이 바뀐 파일만 올린다.
- **conditional write**: 이미 있던 파일은 `If-Match`(manifest 의 etag), 새 파일은 `If-None-Match: *` 로 올린다. 그사이 다른 PC 가 같은 파일을 바꿨으면 원격이 거절한다. 그러면 원격본을 원래 자리에 받고 이 PC 의 버전은 `_conflicts/` 에 남긴 뒤 `CONFLICT=` 로 알린다. 항목마다 파일이 따로라 두 PC 가 다른 항목을 고치면 충돌하지 않는다. lock 은 쓰지 않는다 — Terraform 은 state 가 파일 하나라 lock 이 필요하지만 여기는 파일 단위로 충돌을 가린다.
- **삭제**: 원격 삭제도 etag 를 확인한다. 그사이 다른 PC 가 고친 파일은 지우지 않고 그 버전을 받는다. DeleteObject 의 `If-Match` 를 무시하는 저장소(예: MinIO)에서는 지우기 직전에 HEAD 로 확인해서 아주 짧은 경합 창이 남는다 — `doctor` 가 알려 준다.
- **원격에 닿지 못하면**: 저장소 표시(`.sfbackend`)를 읽지 못하면 빈 저장소로 보지 않고 실패한다. 빈 목록으로 읽으면 pull 이 로컬 사본을 전부 지우기 때문이다. manifest 는 저장소 ID 에 묶여 있어서, 같은 자리에 저장소를 새로 만들면 예전 manifest 를 버리고 로컬 파일을 다시 올린다. 로컬 디렉토리를 읽다 에러가 나도 빠진 파일을 삭제로 읽지 않고 sync 를 멈춘다.
- **turn 끝에 받아오기**: 각 도구의 Stop hook 에 `python3 <sessionflow>/scripts/sfstate.py pull --background` 를 걸면 turn 이 끝날 때마다 다른 PC 의 변경을 받아 온다. 바로 돌아오고 뒤에서 pull 하므로 turn 종료를 붙잡지 않으며, 이미 pull 이 돌고 있으면 건너뛴다. 끝나면 `paths` 의 `PULL_STAMP` 파일(`state/.sfstate/pulled`)을 갱신해, 표시 쪽(statusline 등)이 mtime 으로 다시 그릴 때를 안다. hook 의 cwd 를 `--dir` 로 넘기면 그 저장소의 INDEX.md 도 다시 만든다. 받기만 하고 올리지는 않는다.
- **INDEX.md 는 생성물**: 두 PC 가 같은 목록 파일을 고치면 충돌하므로, 항목 frontmatter(`title`·`summary`·`status`·`discovered`·`resolved`)로 매번 다시 만든다. 상한(`resolved_keep`, 기본 10)을 넘는 오래된 resolved 는 sync 때 지운다.

### backend 정하기 (새 PC 도 같다)

```bash
# S3 API 저장소 — AWS S3·Cloudflare R2·MinIO 등. 자격증명은 stdin 으로 넘겨 credentials.json(mode 600)에 저장한다.
printf '%s\n%s\n' "$ACCESS_KEY_ID" "$SECRET_ACCESS_KEY" | \
  python3 <sessionflow>/scripts/sfstate.py init --backend s3 \
    --endpoint https://<account>.r2.cloudflarestorage.com --region auto \
    --bucket <bucket> --prefix hbrness --credentials-stdin
# 디렉토리 하나를 원격처럼 쓴다 (테스트·오프라인용)
python3 <sessionflow>/scripts/sfstate.py init --backend local --path <dir>

# 저장소가 conditional write 를 지키는지, versioning 이 켜졌는지 확인한다
python3 <sessionflow>/scripts/sfstate.py doctor
# 현황 보기
python3 <sessionflow>/scripts/sfstate.py status
```

- `init` 은 `backend.json` 을 쓰고, 원격과 맞춘 뒤 로컬 전체를 올린다. 다른 PC 에서 이미 올린 내용이 있으면 먼저 받는다.
- AWS 가 아닌 저장소는 `--endpoint` 를 준다. endpoint 가 있으면 path-style(`<endpoint>/<bucket>/<key>`)이 기본이고, `--virtual-host` 로 바꿀 수 있다. 환경변수 `HBRNESS_S3_ACCESS_KEY_ID` 와 `HBRNESS_S3_SECRET_ACCESS_KEY` 가 둘 다 있으면 (`HBRNESS_S3_SESSION_TOKEN` 과 함께) 한 묶음으로 `credentials.json` 보다 먼저 쓴다. 파일 값과 섞지 않는다. `--credentials-stdin` 으로 준 자격증명은 저장된 것을 통째로 바꾼다 (환경변수 묶음이 있으면 init 도 그쪽으로 맞춘다).
- bucket versioning 을 켜 두면 지운 항목·덮어쓴 버전을 되살릴 수 있다.
- backend 가 없으면 스킬은 `~/.hbrness/state/` 에 로컬로만 기록하고 그 사실을 알린다. 나중에 `init` 하면 그대로 올라간다.

### 예전 git state repo 에서 옮기기 (≤0.18)

0.18 까지는 `~/.hbrness/state` 가 private git repo 의 clone 이었고 commit + push 로 동기화했다. 1.0 부터는 git 으로 동기화하지 않는다. 그 자리에서 `init --backend …` 를 하면 `.git`·`.gitignore`·`README.md` 를 `~/.hbrness/state.git-archive-<시각>/` 로 치우고 항목 파일은 그대로 backend 에 올린다. 다른 PC 는 먼저 `git pull` 로 최신을 받은 뒤 같은 `init` 을 하면 된다. GitHub 의 state repo 는 건드리지 않으니 옮긴 걸 확인한 뒤 archive 한다.

```bash
# (선택) 예전 경로 기준 데이터를 한 번에 옮기기 — 각 스킬도 처음 실행될 때 그 프로젝트 몫을 옮긴다
python3 <sessionflow>/scripts/sfstate.py migrate-all --dry-run
python3 <sessionflow>/scripts/sfstate.py migrate-all
```

### 예전 경로 기준 데이터 (≤0.15)

이전 버전은 `~/.hbrness/sessionflow/<project-key>/`(`<project-key>` = 절대경로의 `/` 를 `-` 로) 아래에 `followups/` 와 워크트리별 `HANDOFF.md` 를 뒀습니다. `sfstate.py` 는 처음 실행될 때 그 프로젝트의 데이터를 저장소 기준으로 옮깁니다.

- followup 항목은 그대로 복사하고, 예전 INDEX.md 의 '한 줄 설명'을 각 항목의 `summary` 로, Ideas 줄을 `status: idea` 파일로 바꿉니다. 예전 INDEX 의 resolved 상한(`최근 N`)은 `_config.json` 으로 옮깁니다.
- 핸드오프는 메인 레포 것과 **아직 살아 있는 워크트리** 것만 옮기고(브랜치는 헤더의 `Branch:` 나 워크트리 HEAD 로), 지워진 워크트리의 핸드오프는 남겨 둡니다.
- 원본은 지우지 않고 `.sfstate-migrated.json` 표시만 남깁니다.

### phase-run / phase-loop / relay 상태 (PC 로컬)

```
~/.hbrness/sessionflow/<project-key>/
├── HANDOFF.md                            # phase-run/phase-loop/relay 가 페이즈 경계에서 쓰는 핸드오프
├── PHASES.md                             # phase-run/phase-loop 계획 (있을 때)
├── hooks.spec                            # phase-run/phase-loop 훅 선언 (load-hooks 대상, 있을 때)
├── phases/                               # phase-run 상태 (state.env + phases.tsv + hooks/ + gates.tsv)
├── phase-loop/                           # phase-loop 상태 (phase-run 과 분리된 네임스페이스)
├── relay/                                # relay 상태
└── worktrees/
    └── <wt-name>/                        # 각 워크트리별 (HANDOFF.md, PHASES.md, hooks.spec, phases/, phase-loop/)
```

이 상태는 tmux pane·워크트리에 묶인 오케스트레이션 상태라 동기화하지 않습니다. 여기의 `HANDOFF.md` 는 `/handoff` 가 쓰는 `handoffs/<branch>.md` 와 별개이고, 형식만 같은 규약을 따릅니다. phase-loop 는 팀 모드에서 페이즈마다 브랜치를 새로 따기 때문에 브랜치 기준 저장과 맞지 않습니다.

- `<project-key>` = 프로젝트 절대경로의 `/` 를 `-` 로 치환 (leading dash 유지).
- `<wt-name>` = `basename "$(git rev-parse --git-dir)"` — git 워크트리 디렉토리명

## MEMORY.md 갱신 (Tier 2 — 하네스별 자동로드 위치)

스킬은 동시에 양쪽 하네스의 MEMORY.md 의 `## Followups` 또는 `## Handoff` 섹션을 갱신해 위 state 경로(`~/.hbrness/state/...`)를 가리키게 합니다. MEMORY.md 는 PC 마다 따로라, 다른 PC 에서 처음 이어받을 때는 `/handoff load` 나 `/followup list` 가 그 PC 의 MEMORY.md 를 채웁니다.

| 하네스 | MEMORY.md 위치 |
|---|---|
| Claude | `~/.claude/projects/<project-key>/memory/MEMORY.md` |
| Codex | `~/.codex/memories/<project-key>/MEMORY.md` |

스킬 본문은 `{CLAUDE_MEMORY_PREFIX}` / `{CLAUDE_MEMORY_SUFFIX}` 와 `{CODEX_MEMORY_PREFIX}` / `{CODEX_MEMORY_SUFFIX}` placeholder 로 양쪽 경로를 표현합니다.

## 동작 보장

- **install** 은 SKILL.md 만 배치합니다. MEMORY.md 와 backend 는 스킬이 실제로 실행될 때만 갱신됩니다.
- `followup` 과 `handoff` 는 서로의 파일을 절대 건드리지 않습니다. clear 스킬도 마찬가지입니다.
- `handoff` 는 브랜치 격리 — 같은 저장소의 다른 브랜치 핸드오프를 덮어쓰지 않습니다.
- `followup` 은 저장소 단위 — 어느 워크트리·PC 에서 호출해도 같은 `followups/` 디렉토리에 누적됩니다.
- backend 에는 핸드오프의 diff·에러 원문이 들어가므로 **공개되지 않는 bucket** 에만 둡니다.
