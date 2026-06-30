# 예시 프리셋: CI 게이트형
#
# 각 페이즈가 [work] 에서 구현하고, [verify] 의 shell 훅(타입체크+테스트)이
# 통과해야만 advance(페이즈 경계 통과)가 허용된다. verify 가 실패하면
# 엔진이 advance 를 거부하므로, 통과 못 한 변경이 다음 페이즈로 넘어가지 않는다.
#
# 사용:
#   phaseflow.sh init --stages 'work,verify' ...   # 또는 hooks.spec 의 stages: 로 정의
#   (hooks.spec 을 HANDOFF.md 와 같은 디렉토리에 두고)
#   phaseflow.sh load-hooks
#   ... 구현 ...
#   phaseflow.sh run-hooks verify     # 실패하면 고치고 재실행
#   phaseflow.sh advance              # verify 통과해야 넘어감

stages: work, verify
gates:  verify

[work].prompt
이번 페이즈 목표를 구현한다. HANDOFF 의 Next Action 부터 시작.
[end]

[verify].shell
# 프로젝트에 맞게 교체. exit≠0 이면 advance 가 거부된다.
npm run typecheck && npm test
[end]
