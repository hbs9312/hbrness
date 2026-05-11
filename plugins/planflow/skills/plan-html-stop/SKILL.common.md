---
name: plan-html-stop
description: "planflow:plan-html 로 띄워둔 helper 서버를 종료한다. 사용자가 '계획 HTML 종료', '플랜 서버 종료', '플랜 닫아줘', 'plan-html stop', 'planflow stop', '/plan-html-stop' 등을 말하면 트리거. 인자로 plan-dir 또는 slug 를 받는다. 미지정 시 현재 프로젝트의 활성 helper 들을 목록으로 보여주고 선택을 요청. Usage: /plan-html-stop [plan-dir 또는 slug]"
argument-hint: [plan-dir 또는 slug]
tools: [file:read, shell]
effort: low
model: sonnet
---

# planflow:plan-html-stop — helper 서버 종료

`planflow:plan-html` 가 띄운 backgroud helper 프로세스를 종료한다.

## 동작

### 1. 대상 plan-dir 결정

```bash
git_common=$(git rev-parse --git-common-dir 2>/dev/null) \
  && project_root=$(cd "$(dirname "$git_common")" && pwd) \
  || project_root=$(pwd)
project_key=$(echo "$project_root" | tr '/' '-')
plans_root="{HBRNESS_HOME}/${project_key}/plans"
```

- `$ARGUMENTS` 가 절대경로면 그대로 사용
- slug 만 주면 `${plans_root}/<slug>`
- 비어있으면 `${plans_root}/*/server.json` 목록을 사용자에게 보여주고 선택 요청

### 2. 종료

```bash
node ${SKILL_DIR}/../plan-html/scripts/stop.mjs "$plan_dir"
```

(stop.mjs 는 plan-html 스킬에 함께 들어 있음)

### 3. 보고

- 종료된 pid / port / plan-dir 1줄 요약
- 종료할 helper 가 없었으면 그 사실 명시
