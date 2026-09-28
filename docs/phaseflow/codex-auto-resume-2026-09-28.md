# Codex phase-loop 자동 재개 조사·검증 기록

## 결과

원본은 `plugins/sessionflow/skills/`이다. Codex 설치 경로는 `dist/codex/sessionflow/skills/`를 가리키는 symlink였다. 원본만 수정하고 네 adapter로 빌드·설치했다. enghost 기능 구현, 커밋, push/PR, 실제 루프 재시작은 이 작업에서 실행하지 않았다.

변경 파일:

- `plugins/sessionflow/skills/phase-run/scripts/phaseflow.sh`: 상태 쓰기 원자화/명령 간 잠금, run ID, 예약 분리, 오래된 호출 거부, 정확한 resume 의미, Codex 스킬 접두어 변환. 기존 미커밋 `tmux run-shell -b` 변경 보존.
- 같은 디렉터리 `codex-guard.py`: 전용 Codex PTY, 사용자 입력/resize 세대, private socket, 세대 비교 후 키 전송. 사용자 입력은 버리지 않고 전달한다. 초안 삭제 키는 사용하지 않는다.
- 같은 디렉터리 `inject.py`: 불변 예약과 단일 worker, 단계별 확인, 시도 기록, 제한 시간, ACK 분리 로그, 수동 복구 문서.
- `phase-run/SKILL.common.md`, `phase-loop/SKILL.common.md`: 실행 조건·차이·복구·한계 명시.
- `tests/test_phaseflow_inject.py`, `tests/test_phaseflow_tui.py`: 실패 경로 및 실제 TUI 검증.

`phase-loop/scripts/loop.sh`는 기존 sibling 엔진 위임을 그대로 사용한다. 프로젝트 PHASES/hooks는 재설치하거나 stock으로 교체하지 않는다. 기존 xreview 파일의 미커밋 변경은 이 작업에서 수정하지 않았다.

## 확인된 원인

1. 고정 4초는 응답 종료 신호가 아니다. task 진행 중 `/new`를 보내면 실제 0.157.1에서 `disabled while a task is in progress`로 거부된다.
2. 문자 직후 Enter는 별도 문제다. `paste_burst.rs`의 120ms Enter 억제 구간에서는 CSI-u도 줄바꿈으로 합쳐진다. 실제 TUI에서 문자열과 즉시 CSI-u Enter가 초안에 남았고, 안정화 후 CSI-u와 일반 tmux Enter는 모두 제출됐다. 기존 “일반 Enter는 항상 Ctrl-M 줄바꿈” 주석은 틀렸다.
3. 스킬을 설치해도 `/phase-loop continue`는 0.157.1에서 `Unrecognized command`였다. `$phase-loop continue`는 접수됐다. 엔진은 Codex에서만 알려진 `/phase-loop`, `/phase-run`, `/sessionflow:phase-*` 접두어를 `$phase-*`로 변환한다. 임의 커스텀 프롬프트는 바꾸지 않는다.
4. 기존 `continuation submitted` 로그는 키 전송만으로 성공을 기록했다. 새 로그는 키 전송, 화면 기반 새 세션 확인, TUI 접수, 실패/timeout을 구분한다.

설치 버전: `codex-cli 0.157.1`. 비교 소스: OpenAI Codex `rust-v0.157.1`, commit `36650394c5b38c2990ccf2a3457165ca3e9d9726`. 관련 파일은 `codex-rs/tui/src/bottom_pane/paste_burst.rs`, `chat_composer.rs`, `chatwidget/slash_dispatch.rs`다.

## 인터페이스 선택과 한계

설치 CLI의 app-server/remote/queue 인터페이스와 해당 버전 프로토콜을 조사했다. thread/turn API는 존재하지만 기존 TUI의 미제출 초안과 `/new`의 화면 전환을 원자적으로 보장하는 인터페이스는 확인하지 못했다. 별도 thread를 API로 시작하는 것으로 사용자의 TUI 전환을 대체하지 않았다. 공식 [plugin hooks 문서](https://developers.openai.com/plugins/build/plugins)에 따르면 비관리 hook은 신뢰 검토가 필요하다. 전역 hook을 추가하거나 신뢰 설정을 우회하지 않았다.

따라서 **입력 충돌은 PTY 입력 세대로 차단하고, 상태는 버전 한정 화면 신호로 확인**한다. 래퍼는 `--no-daemon --no-alt-screen`을 사용한다. 일반 Codex pane에 사후 attach하지 않는다. 래퍼 없는 세션이나 다른 버전에서는 자동 입력을 거부한다.

순서:

1. 예약 시 run ID, phase, state hash, tmux server/socket/pane/PID/프로세스 시작 시각/cwd, guard nonce/input epoch를 고정한다.
2. 전체 120초 이내에 busy 표시가 없고 빈 composer와 알려진 footer가 300ms 안정될 때까지 관찰한다.
3. `/new` 입력이 정확히 표시되어 300ms 안정된 뒤 CSI-u Enter를 한 번 보낸다.
4. PTY에서 새 screen-clear가 관측되고 0.157.1 새 대화 header·빈 composer가 확인돼야 다음 단계로 간다(15초 제한).
5. continuation 표시를 확인하고 Enter를 한 번 보낸다. 정확한 사용자 history cell과 빈 composer를 확인하면 `continuation_accepted`다(15초 제한).

화면 ACK는 공식 thread ID ACK나 모델 작업 완료가 아니다. custom UI, popup, 좁은 창/줄바꿈, 출력이 빠르게 화면을 밀어낸 경우에는 실패할 수 있다. 모르는 레이아웃은 성공으로 추정하지 않는다. 외부 app-server 클라이언트와 같은 세션을 동시에 조작하는 환경은 지원하지 않는다. tmux 서버나 프로세스가 소유자의 제어 밖에서 악의적으로 변조되는 상황을 방어하는 보안 경계는 아니다.

각 전송 전에도 상태·pane·사용자 입력을 재확인한다. 사용자 입력을 감지하면 예약을 취소하고, 이미 입력한 자동화 텍스트도 지우지 않는다. 텍스트 전송과 Enter 사이에 사람이 입력했다면 혼합된 초안이 남을 수 있으나 자동 제출하거나 덮어쓰지 않는다. resize/터미널 응답도 보수적으로 취소 사유다.

재시도는 **0회**다. 최초 키 전송 전에 `attempt-<run>-<phase>.json`을 fsync해 crash/timeout 후에도 같은 페이즈를 자동 재전송하지 않는다. worker 중복 실행도 영속 claim으로 차단한다. 접수가 불명확하면 `RECOVERY.md`와 `inject.log`를 확인하고 사용자가 접수 여부를 판정한다. `resume --manual`은 활성화와 예약 취소만 하며 커서를 이동하거나 키를 보내지 않는다. `advance`만 다음 페이즈로 이동한다.

## 검증

- 신규 단위/셸 테스트 13개 통과. busy >4초, 지연된 전환, Enter 줄바꿈, 초안, 중복 예약/worker, 오래된 ticket, guard 부재, 서로 다른 tmux 서버의 동일 pane ID, 전체 timeout, 접수 불명확·재전송 차단 포함.
- 사용자 입력, pause, stop, pane 교체, 세션 종료, run/phase/ticket 변경을 네 키 전송 경계마다 검사하는 32개 하위 시나리오 통과.
- Claude `/clear`+일반 Enter, Grok/Devin `/new`+일반 Enter는 fake tmux 셸 통합으로 확인. dry-run에서 worker나 키가 나가지 않는 것도 확인. 세 런타임의 실제 TUI ACK 검증은 하지 않았다.
- `npm test`의 Node 5개·Python 18개 통과(실제 TUI 1개는 기본 실행에서 skip). 실제 TUI 테스트는 기본 suite에서 opt-in skip이다.
- **실제 Codex TUI 테스트 통과**: 별도 tmux 서버, 임시 HOME/CODEX_HOME, fixture skill, 인증 불필요한 로컬 Responses SSE 서버 사용. 즉시 CSI-u 줄바꿈, 지연 일반 Enter 제출, busy `/new` 거부, 7초 응답 중 4초 시점 무전송, 새 세션 전환, `$phase-loop continue` 접수, 중복 예약 거부, 사용자 초안 입력 시 취소를 검증했다. 실제 OpenAI 모델의 스킬 수행이나 enghost 구현을 실행한 검증은 아니다.
- `bash -n`, `git diff --check`, adapter build/validate 통과.

재실행:

```bash
cd /Users/seok/development/hbrness
npm test
PHASEFLOW_TUI_TEST=1 python3 -m unittest discover -s tests -p test_phaseflow_tui.py -v
```

## 하네스 동기화

`harness-sync`의 hbrness adapter 절차로 `build.sh all sessionflow`, `validate.sh`, `hbrness.js install <runtime> sessionflow`를 실행했다. Claude는 plugin cache, Codex는 dist symlink, Grok/Devin은 native plugin 복제다. 세 실행 스크립트의 설치본과 원본이 네 런타임에서 모두 일치하는지 확인했다. Claude plugin list, Grok inspect, Devin skills list에서 sessionflow 발견을 확인했다. Codex는 설치 symlink/내용 검증까지이며 기존 실행 중 세션의 스킬 캐시 재로드는 하지 않았다.

기존 설치본과 dist는 `/Users/seok/.hbrness/harness-sync/backups/phaseflow-20260928-131645/`에 보존했다. Claude는 오래된 0.14.0 엔진이었고, Grok/Devin의 문서 차이는 설치 경로 치환이었다. 새 설치는 현재 원본 metadata 버전 0.15.0이다. 이 작업에서 commit/push/version commit은 만들지 않았다.

Codex 전용 입력 감시/상태 확인/스킬 접두어 변환을 다른 런타임에 적용하지 않았다. Claude/Grok/Devin의 기존 자동 주입은 DELAY/GAP 기반이며 로그에도 ACK 미검증이라고 명시한다.

## enghost의 동시 변경과 재개 방법

조사 시작 시 `%7`, `CURSOR=4`, `STAGE_IDX=1`을 읽기로 확인했다. 이 작업에서 enghost pane에 키를 보내거나 프로젝트 상태를 쓰는 명령은 실행하지 않았다. 종료 전 해시 검증에서 **별도 변경**을 발견했다:

- Phase 4 커밋 `8328083 feat(navigation): unify work and chat screens`가 생겼다.
- 13:12:40 상태는 `CURSOR=5`, `STATUS=active`, `STAGE_IDX=1`이다.
- HANDOFF는 Phase 4 완료·Phase 5 준비로 갱신됐다. cleanroom 리뷰 규칙은 그대로 있다.
- PHASES.md 해시는 시작 시와 동일하다. 상태/핸드오프는 외부 변경을 덮어쓰거나 복원하지 않았다.

**현재 Phase 4를 재개하면 중복이다.** 재개 직전에 상태와 현재 진행 중 작업을 확인한다:

```bash
cd /Users/seok/development/enghost
bash /Users/seok/.codex/skills/sessionflow-phase-loop/scripts/loop.sh pf current
```

다른 작업이 진행 중이면 새 continuation을 보내지 않는다. 미접수·idle임을 확인하고 초안을 보존한 뒤, tmux의 원하는 pane에서 새 guarded 세션을 직접 시작한다:

```bash
cd /Users/seok/development/enghost
python3 /Users/seok/.codex/skills/sessionflow-phase-run/scripts/codex-guard.py -- --no-alt-screen
```

새 Codex 입력창에 `$phase-loop continue`를 **한 번** 입력한다. 새 세션이므로 `/new`를 추가로 보낼 필요 없다. 현재는 Phase 5를 이어받게 된다. 상태가 paused인 경우에만 먼저 `loop.sh pf resume --manual`로 활성화한다. `advance`, `init`, `load-hooks`를 실행하지 않는다. 새 세션에서 이후 경계를 넘을 때 스킬의 `advance --pane "$TMUX_PANE" --tool codex`가 새 pane을 기록한다. 이 작업은 위 재개 절차를 실제 실행하지 않았다.
