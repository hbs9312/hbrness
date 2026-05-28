# hbrness — Project Instructions

## Plugin version bump

플러그인(`plugins/<name>/`) 내부 파일을 수정하고 커밋한 뒤에는 **반드시** 같은 플러그인의 `plugins/<name>/plugin.meta.json` 의 `version` 도 SemVer 규칙으로 범프하고 별도 커밋한다.

- fix / 호환 가능한 내부 변경 → patch (x.y.Z+1)
- 신규 기능 / 동작 추가 → minor (x.Y+1.0)
- 호환성 깨짐 → major (X+1.0.0)

커밋 메시지 형식: `chore(<plugin>): bump <prev> → <next>`. 본문에는 어떤 변경들이 묶여 들어갔는지 fix/feat 커밋 SHA 와 한 줄 요약을 나열한다.

빠뜨리기 쉬우니, 플러그인 파일 수정이 끝나서 마지막 fix/feat 커밋을 만든 직후에 바로 범프 커밋을 추가하는 것을 기본 루틴으로 삼는다. 사용자가 명시적으로 범프하지 말라고 하지 않은 한 항상 한다.
