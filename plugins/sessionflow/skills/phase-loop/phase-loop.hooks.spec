# phase-loop 프리셋 — 한 페이즈(=PR 단위)의 파이프라인을 stage+훅으로 표현한다.
#
# 각 stage 의 prompt 훅은 그 단계에서 LLM 이 할 일을 담고, verify 는 커밋 전
# 기계적 게이트(shell 훅)다. SKILL 의 "페이즈 프로토콜"을 stage 로 옮긴 것이며,
# 모드(team/personal)·스택(stack/parallel) 분기는 PHASES.md 를 보고 prompt 훅 안에서 판단한다.
#
# 로드: loop.sh pf load-hooks "${SKILL_DIR}/phase-loop.hooks.spec"
# walk: 각 페이즈에서 stage 순서대로 run-hooks → 마지막에 advance.
#       advance 는 verify 게이트 통과를 확인한다(미실행/실패면 거부).

stages: implement, xreview, verify, commit, ship, cut, handoff
gates:  verify

# ── implement ────────────────────────────────────────────────
# 전제: 이번 페이즈 브랜치는 이미 체크아웃돼 있어야 한다(팀: worktree-create/직전 cut).
[implement].prompt
git branch --show-current 가 PHASES.md/HANDOFF.md 의 이번 페이즈 브랜치와 일치하는지 확인만 한다.
어긋났으면 폴백으로 만든다(stack: 직전 페이즈 브랜치에서, parallel: 통합 base 에서). 개인 모드는 전환 없음.
그 다음 TITLE 페이즈의 실제 구현을 한다 — HANDOFF 의 Next Action 부터.
[end]

# ── xreview (비동기) ─────────────────────────────────────────
[xreview].prompt
xreview:live 를 start 로 호출: --scope working --approve auto --context "<이번 페이즈 의도·설계결정 3~6줄>" (reviewer 생략=반대편 도구). 출력의 slug 기억.
그리고 이 turn 을 끝내고 핑을 기다린다(추가 작업 금지). 핑은 완료뿐 아니라 stuck/gone/timeout 으로도 온다.
핑/폴링으로 분기:
 - 완료 → REVIEW_RESULT.md 를 severity 순으로. blocking 없거나 approve 면 stage 종료. blocking 있으면 반영 후 라운드 +1(최대 N=PHASES.md xreview max-rounds, 기본 2). N 도달 시 미해결을 sessionflow:followup 에 남기고 다음 stage 로.
 - stuck → /xreview:live peek <slug> 또는 /xreview:stop 후 재시작. 조용히 기다리지 말 것.
 - gone/timeout → /xreview:status <slug> 확인 후 1회 재시작, 또 실패면 followup 남기고 진행.
주의: 이 stage 는 turn 경계를 넘는다. 핑으로 돌아오면 /clear 없이 같은 페이즈이며 STAGE_IDX 가 xreview 를 가리킨다 — 'stage' 로 확인하고 이어간다.
[end]

# ── verify (커밋 전 기계적 게이트) ───────────────────────────
# 기본은 no-op(true). 프로젝트 검증(테스트/린트/타입체크)을 여기에 넣으면
# 통과해야만 commit 이후 stage 로 진행하고 advance 가 허용된다.
# loop.sh pf set-hook verify --shell <<'EOF' ... EOF  로 교체하거나 hooks.spec 를 편집.
[verify].shell
true
[end]

# ── commit (정책별) ──────────────────────────────────────────
[commit].prompt
이번 페이즈 변경분만 스테이징(의도치 않은 파일 제외).
무인(팀/--auto): 저장소 커밋 컨벤션대로 바로 커밋(ghflow:commit 규약 있으면 그 스타일).
확인(개인/--confirm): git status / git diff --stat 보여주고 커밋 확인받기. 확인 전엔 커밋하지 말 것.
[end]

# ── ship (push + PR) ─────────────────────────────────────────
[ship].prompt
remote 있으면 git push -u origin <이번 브랜치>. 없으면(개인 로컬) 건너뛰고 그 사실 보고.
팀 모드(또는 명시): PR 생성 — stack 이면 --base 직전 페이즈 브랜치(Phase1 은 통합 base), parallel 이면 --base 통합 base.
PR 본문 상단에 스택 표시 + 이번 페이즈 의도 요약(ghflow:create-pr 템플릿 있으면 따름). 개인 모드/remote 없음은 PR 건너뜀.
생성된 PR 번호/URL 기록(핸드오프에 들어감).
[end]

# ── cut (다음 페이즈 stacked 브랜치) ─────────────────────────
[cut].prompt
팀 모드 + 마지막 페이즈 아님일 때만: 다음 페이즈가 깨어날 자리를 지금 만든다.
stack: git checkout -b <다음 브랜치> <이번 브랜치> / parallel: git checkout -b <다음 브랜치> <통합 base>.
다음 브랜치명은 PHASES.md 의 다음 페이즈 '브랜치:' 그대로. 이 checkout 으로 워킹트리가 다음 브랜치로 이동한다.
마지막 페이즈거나 개인 모드면 이 stage 는 건너뜀.
[end]

# ── handoff ──────────────────────────────────────────────────
[handoff].prompt
sessionflow:handoff 규약으로 HANDOFF.md 를 다음 페이즈 기준으로 작성한다.
표준 섹션 + Phase Loop Progress(완료/다음/모드/이어받기) + (팀) Stack State(워크트리·완료 브랜치·PR·현재 체크아웃=다음 브랜치·PR base·병합 순서).
검증: "이 핸드오프+PHASES.md 만으로 대화 로그 없이 다음 페이즈를 시작할 수 있는가?" 빠진 분기 base·PR 번호·미해결 리뷰·다음 액션 채우기. 비밀값 금지.
그 다음 advance(= 마지막 행동).
[end]
