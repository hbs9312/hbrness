# 예시 프리셋: 구현 → 리뷰 → 출하 (phase-loop 스타일을 stage+hook 으로 표현)
#
# phase-loop 의 파이프라인(구현 → xreview → commit/push/PR → handoff)을
# phase-run 의 stage+hook 으로 흉내 낸 예시. 리뷰/커밋/PR 은 LLM 판단이 필요하므로
# prompt 훅으로 두고, 기계적으로 강제할 수 있는 부분만 shell 게이트로 둔다.
#
# 주의: 이건 "엔진으로 이런 워크플로우를 표현할 수 있다"는 데모다.
# 실제 자동 xreview·스택 PR·모드 분기가 필요하면 sessionflow:phase-loop 스킬을 써라.

stages: work, review, ship, handoff
gates:  gate

# work — 구현
[work].prompt
이번 페이즈(=PR 단위)를 구현한다. HANDOFF 의 Next Action 부터.
[end]

# review — 다른 에이전트 리뷰 지침(LLM 이 수행)
[review].prompt
xreview:live 를 --scope working 으로 돌려 이번 변경을 리뷰받고,
blocking 지적을 반영한다. 미해결은 followup 으로 남긴다.
[end]

# ship — 커밋/푸시/PR 지침 + 출하 전 기계적 게이트
[ship].shell
# 출하 전 기계적 확인(프로젝트에 맞게 교체). 실패하면 advance 거부.
git diff --quiet || true
[end]

[ship].prompt
저장소 커밋 컨벤션대로 커밋 → push → (팀이면) PR 생성.
PR 본문에 이번 페이즈 의도 요약을 넣는다.
[end]

# handoff — 다음 페이즈 기준 핸드오프 작성
[handoff].prompt
sessionflow:handoff 규약으로 HANDOFF.md 를 다음 페이즈 기준으로 작성·검증.
"이 핸드오프만으로 대화 로그 없이 다음 페이즈를 시작할 수 있는가?" 통과해야 한다.
[end]
