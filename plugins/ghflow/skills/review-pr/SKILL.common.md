---
name: review-pr
description: >
  PR(Pull Request)에 달린 리뷰 댓글을 불러와 정리하고, 각 피드백을 코드와 함께 검토할 수 있게 도와주는 스킬.
  사용자가 "PR 리뷰 확인", "리뷰 내용 봐줘", "리뷰 달린 거 확인해줘", "PR 피드백 정리", "#101 리뷰 검토해줘",
  "review-pr", "pr review check", "review comments 보여줘", "리뷰 코멘트 처리", "/review-pr" 등을 말하면 트리거한다.
  PR 번호를 인자로 받으면 해당 PR의 브랜치로 전환 후 리뷰를 검토하고, 없으면 현재 브랜치의 PR 리뷰를 검토한다.
  리뷰 내용 확인뿐 아니라 피드백 항목을 처리하는 것까지 적극적으로 도와줄 것.
  결과는 ~/.claude/reviews/{owner}/{repo}/ 아래 프로젝트별 파일로 저장되며, --open 인자를 주면 VS Code로 연다.
  Usage: /review-pr [#PR번호] [--rich|-r] [--open|-o]
---

# Review PR Skill

PR에 달린 리뷰 댓글을 불러와 **고정된 템플릿**으로 정리하고, 각 피드백 항목을 코드와 함께 검토한다.
결과는 사용자의 `~/.claude/reviews/` 아래 프로젝트별로 저장되며(= 현재 프로젝트 git에 포함되지 않음), 필요하면 VS Code로 바로 열 수 있다.
피드백 처리·수정까지 이어서 도와준다.

## Arguments

- `[#PR번호]` or `[PR번호]`: Optional. 검토할 PR 번호 (예: `#101` 또는 `101`). 생략하면 현재 브랜치의 PR을 사용.
- `--rich` / `-r`: Optional. 저장 파일을 **rich 포맷**(접을 수 있는 `<details>` 블록, 전체 diff)으로 기록한다. GitHub 웹/Markdown 프리뷰에서 읽을 때 유용. 채팅 출력은 항상 flat 포맷으로 고정.
- `--open` / `-o`: Optional. 리뷰 파일 저장 후 VS Code로 연다. `--rich`와 함께 쓰면 **프리뷰 모드**로, 단독이면 **소스 모드**로 연다.

Examples:
- `/review-pr` — 현재 브랜치 PR 리뷰, flat 저장만
- `/review-pr #101` — PR #101 리뷰, flat 저장만
- `/review-pr 101 --open` — PR #101 리뷰, flat 저장 후 VS Code 소스 뷰로 열기
- `/review-pr 101 -r` — PR #101 리뷰, rich 저장만 (GitHub에 붙여넣기 좋음)
- `/review-pr 101 -r -o` — PR #101 리뷰, rich 저장 후 VS Code **프리뷰**로 열기

## Output Contract (중요)

출력은 **항상 아래 템플릿을 그대로 따른다.** 임의로 섹션을 추가·삭제·재배열하지 않는다.

### 출력 채널 2개 분리

| 채널 | 포맷 | 이유 |
|---|---|---|
| **채팅(Claude Code 대화)** | 항상 **flat** | 터미널에 `<details>` 태그가 그대로 노출되면 가독성이 떨어짐 |
| **저장 파일** | 기본 flat / `--rich`면 rich | flat은 CLI/소스뷰 친화, rich는 GitHub·프리뷰 친화 |

### 공통 규칙

- 섹션 순서: `① 헤더 → ② 한눈 대시보드 → ③ 상세 (판정별 그룹) → ④ 리뷰어 요약 → ⑤ 다음 단계`
- 빈 섹션도 **생략하지 않고** "없음"으로 표기
- 이모지/라벨은 아래 매핑표를 고정 사용
- 코멘트 번호(`#1, #2 …`)는 전체 PR에서 **연속된 전역 번호**로 매긴다 (리뷰어 교차하더라도 유지). 사용자가 "3번 처리해줘"로 호출할 수 있도록.
- 파일 경로는 항상 `` `path:line` `` 백틱 포맷 유지
- **대시보드 테이블**과 **상세 블록**이 같은 전역 번호를 공유해야 한다
- 본문이 비어 있으면 `(본문 없음)` 문자열로 대체
- **모든 인라인 코멘트는 타당성 평가(Validity)를 함께 표시**한다. 평가 근거는 1–2줄로 간결히.
- **타당성 평가는 지적 라인만 보고 내리지 않는다.** 그 라인이 호출/참조하는 연관 코드(함수 정의, 타입, 상수, 구독자 등)를 **필요한 만큼 Grep·Read로 추적**해서 판정에 반영한다. 확인한 연관 위치는 `🔗` 필드에 `path:line`으로 명시.
- **렌더링 결과는 항상** `~/.claude/reviews/{owner}/{repo}/pr-{number}-{YYYYMMDD-HHMMSS}.md`로 저장한다. 프로젝트 git에는 기록되지 않는다.

### 포맷별 차이

| 요소 | flat (기본) | rich (`--rich`) |
|---|---|---|
| 상세 블록 래핑 | 평문 (구분선 `---`만) | `<details><summary>` 접힘 |
| diff hunk | 최대 **5줄**, 초과 시 `... (+N lines)` | **원본 그대로** (최대 20줄까지) |
| 코멘트 본문 인용 | 첫 3줄 + 필요시 절삭 표시 | 전체 본문 |
| 코멘트 블록 높이 | 6–8줄 | 자유 (접힘으로 커버) |

### 고정 매핑

| 상태/유형 | 라벨 |
|---|---|
| Review: Approved | ✅ Approved |
| Review: Changes Requested | 🔴 Changes Requested |
| Review: Commented | 💬 Commented |
| Comment tag: blocking (요청자가 Changes Requested) | 🔴 blocking |
| Comment tag: suggestion / nit | 💡 suggestion |
| Comment tag: question | ❓ question |
| Comment tag: praise / nitpick 외 기타 | 💬 note |
| Thread resolved | `[RESOLVED]` (취소선 적용) |
| PR Draft | `[DRAFT]` 배지 헤더에 추가 |
| PR Merged/Closed | `[MERGED]` / `[CLOSED]` 배지 |
| Validity: 유효 (지적이 맞고 수정 필요) | ✅ Valid |
| Validity: 부분 유효 (일부만 타당 / 조건부) | ⚠️ Partial |
| Validity: 오판 (근거 부족·사실과 다름) | ❌ Invalid |
| Validity: 판단 유보 (정보 부족·주관적) | 🤔 Unclear |
| 권장 대응 | 수정 / 검토 / 논의 / 반박 / 무시 / 이슈 생성 |

## Procedure

### Step 1: Determine Target PR

**If PR number provided:**
```bash
gh pr view {number} --json number,title,headRefName,state,baseRefName,isDraft
```

**If no PR number:**
```bash
gh pr view --json number,title,headRefName,state,baseRefName,isDraft
```
If no PR is associated with the current branch, inform the user and abort.

### Step 2: Switch Branch (only when PR number was explicitly provided)

If the PR's branch differs from the current branch:
1. Check for uncommitted changes: `git status --porcelain`. 있으면 먼저 경고.
2. 물어보기: `"PR #{n}의 브랜치(\`{headRefName}\`)로 전환할까요? (현재: \`{currentBranch}\`)"`
3. 승인 시: `gh pr checkout {number}`

거절 시에도 리뷰 데이터는 API로 확인 가능하므로 그대로 진행.

### Step 3: Fetch Review Data (병렬)

```bash
# 1. Review submissions
gh pr view {number} --json reviews \
  --jq '.reviews[] | {author: .author.login, state, body, submittedAt}'

# 2. Inline review comments (with resolution status via GraphQL if possible)
gh api "repos/{owner}/{repo}/pulls/{number}/comments" \
  --jq '[.[] | {
    id, author: .user.login, body, path,
    line: (.line // .original_line),
    diff_hunk, created_at,
    in_reply_to_id
  }]'

# 3. PR overview
gh pr view {number} --json title,body,author,additions,deletions,changedFiles,state,isDraft,headRefName,baseRefName

# 4. Thread resolution (optional, GraphQL)
gh api graphql -f query='
  query($owner:String!,$repo:String!,$number:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$number){
        reviewThreads(first:100){ nodes { isResolved comments(first:1){ nodes { databaseId } } } }
      }
    }
  }' -f owner={owner} -f repo={repo} -F number={number}
```

`{owner}/{repo}`: `gh repo view --json owner,name -q '"\(.owner.login)/\(.name)"'`

### Step 3.5: Assess Validity (타당성 평가)

**모든 인라인 코멘트**에 대해 실제 코드를 기준으로 타당성을 평가한다.
지적된 라인만 보고 판단하지 말고, **필요한 만큼 연관 코드까지 추적**해서 본다.

#### 3.5.1 지적 라인과 주변 컨텍스트 읽기

1. PR 브랜치로 체크아웃된 상태라면 로컬 파일을 Read로 확인. 아니라면 `gh api`로:
   ```bash
   gh api "repos/{owner}/{repo}/contents/{path}?ref={headRefName}" --jq '.content' | base64 -d
   ```
2. 지적된 라인 ± 20줄 정도는 기본으로 확인 (함수 경계, 블록 범위 파악용).

#### 3.5.2 연관 코드 탐색 (필수)

지적된 라인이 다음 중 하나라도 포함하면 **연관 대상도 반드시 읽고** 판정에 반영한다.

| 지적 라인에 있는 것 | 추가로 확인해야 할 대상 |
|---|---|
| 다른 함수/메서드 호출 (`foo()`, `obj.bar()`) | 그 함수 정의 — 동작/반환/부수효과 확인 |
| 클래스·컴포넌트 사용 (`new X()`, `<X />`) | 클래스/컴포넌트 정의, 생성자/props 타입 |
| import / require 된 심볼 | 해당 모듈의 export 구현 |
| 타입·인터페이스 참조 (`: Foo`, `as Bar`) | 타입 정의 |
| 상수·설정 참조 | 그 상수 선언부 (값·용도) |
| 이벤트·훅 발생 (`emit`, `useXxx`) | 구독자/처리부 |
| DB 쿼리·API 호출 | 스키마·엔드포인트 시그니처 |
| 리뷰어가 "이거 여기서 처리 안 해도 {다른 곳}에서 될 것 같은데" 류로 언급 | 해당 "다른 곳" 실존·동작 여부 |
| "다른 파일에서도 같은 패턴이 있을 것" 류 | `Grep`으로 동일 패턴 검색하여 일관성 확인 |

**탐색 도구 우선순위**: Grep (심볼·패턴 검색) → Read (정의 확인) → Glob (파일 위치).
탐색은 **판정에 필요한 만큼만**. 무관한 파일까지 훑지 않는다.

#### 3.5.3 판정

네 단계 중 하나:
- **✅ Valid** — 지적이 정확하고 수정이 필요 (연관 코드까지 확인해도 문제 재현됨)
- **⚠️ Partial** — 일부만 타당 / 조건부로 맞음 (특정 호출 경로·환경에서만 발생)
- **❌ Invalid** — 사실과 다름 (연관 코드가 이미 처리 중, 지적 대상이 다른 의미, 컨벤션상 OK 등)
- **🤔 Unclear** — 정보 부족·주관적 / 탐색해도 판단이 안 설 때

근거는 **1–2줄로 간결히**. 필요 시 연관 위치를 `` `path:line` ``로 명시.

#### 3.5.4 원칙

- 리뷰어의 권위가 아니라 **현재 코드 + PR diff + 연관 코드**를 기준으로 내린다.
- Changes Requested라도 Invalid일 수 있고, 단순 코멘트라도 Valid일 수 있다.
- 연관 코드 확인 없이 Invalid 판정을 내리지 않는다. 확인 못 했으면 🤔 Unclear.
- 탐색 범위가 넓어 시간 소요가 크면 **범위만 밝히고** Unclear로 보류 후 사용자에게 결정 요청.

### Step 4: Render Output

출력 채널마다 포맷이 다르다.

- **채팅 출력**: 항상 **flat 템플릿** (아래 4A)
- **저장 파일**: `--rich` 없으면 **flat**, `--rich`면 **rich 템플릿** (아래 4B)

#### 4A. Flat Template (기본 / 채팅)

````markdown
# PR #{number} — {title} {배지}

| Status | Branch | Changes | Reviews |
|---|---|---|---|
| {state 라벨} | `{head}` ← `{base}` | +{add} / -{del} ({files}개 파일) | ✅{approved_cnt} 🔴{changes_cnt} 💬{commented_cnt} |

> {PR 본문 첫 문단 — 3줄 이내로 절삭, 없으면 "(본문 없음)"}

---

## 📊 한눈 대시보드

| #  | 판정 | 태그 | 위치              | 요약           | 권장 |
|----|-----|-----|-----------------|---------------|-----|
| 1  | ✅  | 🔴  | `api/user.ts:42`   | null 체크 누락   | 수정      |
| 2  | ⚠️  | 💡  | `api/user.ts:88`   | 네이밍 제안      | 검토      |
| 3  | 🤔  | ❓  | `ui/Form.tsx:15`   | 의도 질문        | 논의      |
| 4  | ❌  | 💡  | `lib/date.ts:7`    | 이미 처리됨      | 반박      |
| 5  | ✅  | 💡  | `core/cache.ts:30` | 캐시 전면 개편   | 이슈 생성 |

**분포**: ✅{N} · ⚠️{N} · ❌{N} · 🤔{N}  |  **미해결 스레드**: {N}건  |  **이슈 분리 제안**: {N}건
**처리 순서 제안**: `{공백으로 구분된 번호 나열, Valid(수정) → Valid(이슈 생성) → Partial → Unclear → Invalid 순}`

(코멘트가 없으면 "아직 인라인 코멘트가 없습니다." 한 줄로 대체)

---

## 🔍 상세 (판정별)

### ✅ 수정 필요 · {N}건

**#1** `{path}:{line}` · {태그 라벨} · _@{reviewer}_ {[RESOLVED] if resolved}
> {코멘트 본문 첫 3줄, 길면 `…`로 절삭}

- 🔗 {연관 위치 목록, 없으면 "없음"}
- 🔍 {판정 근거 1–2줄}
- 🛠 {권장 대응 + 한 줄 이유}

```diff
{diff hunk 최대 5줄, 초과 시 ... (+N lines)}
```

**#4** ... (다음 Valid 항목, 동일 구조)

### ⚠️ 부분 반영 · {N}건
{동일 구조, 없으면 "_없음_"}

### 🤔 추가 논의 · {N}건
{동일 구조, 없으면 "_없음_"}

### ❌ 반박 권장 · {N}건
{동일 구조, 🛠 에 "반박 답글 초안 요청 시 작성" 힌트 포함}

---

## 💬 리뷰어 요약

- **@{reviewer1}** — {리뷰 상태 라벨} · 댓글 #{n,n,n} · _"{리뷰 본문 1줄 요약, 없으면 (본문 없음)}"_
- **@{reviewer2}** — ...

(리뷰어가 없으면 "아직 리뷰가 달리지 않았습니다." 한 줄만 출력)

---

## 🚀 다음 단계

어떤 번호부터 처리할까요?
`"1번 처리"` · `"Valid 전부 처리"` · `"3번 뭐 확인?"` · `"4번 반박 초안"` · `"5번 이슈로 분리"`
````

##### Flat 포맷 세부 규칙

- **대시보드 테이블 컬럼 순서 고정**: `#` · 판정 · 태그 · 위치 · 요약 · 권장
- 요약은 **15자 이내 한국어** 권장 (긴 경우 `…`)
- `권장` 컬럼 값은 `수정 / 검토 / 논의 / 반박 / 무시 / 이슈 생성` 중 하나
- 상세 블록은 각 코멘트당 **헤더 1줄 + 인용 ≤3줄 + 🔗/🔍/🛠 3줄 + diff ≤5줄** = 대략 8–12줄
- diff가 5줄 초과면 마지막에 `... (+N lines)` 추가
- 코멘트 본문은 3줄 초과 시 3줄 + `…` (중요 내용은 🔍 근거에서 다시 언급)
- `처리 순서 제안`은 Valid → Partial → Unclear → Invalid 순, 같은 그룹 내는 번호순

#### 4B. Rich Template (`--rich`, 저장 파일 전용)

Flat과 **동일한 5개 섹션 구조**를 유지하되, 다음만 다르게 렌더링한다.

1. **상세 블록을 `<details>`로 감싼다** — 기본 접힘 상태. 요약 라인은 대시보드와 동일한 형식.
2. **diff 전체 노출** (최대 20줄, 초과 시 `... (+N lines)`).
3. **코멘트 본문 전체 노출** (절삭 없음).
4. **답글(reply) 스레드 전체 포함**: `↳ @{author}: {body}` 들여쓰기 유지.
5. **🔗 연관 확인**을 불릿 여러 줄로 확장 가능 (flat은 한 줄 요약).

##### Rich 상세 블록 예시

````markdown
### ✅ 수정 필요 · 2건

<details>
<summary><b>#1</b> <code>api/user.ts:42</code> · 🔴 blocking · <i>@bob</i> — null 체크 누락 <b>[수정]</b></summary>

> {코멘트 본문 전체}
>   ↳ @alice: (reply 1 본문)
>   ↳ @bob: (reply 2 본문)

- 🔗 연관 확인:
  - `util/safe.ts:12` — 호출되지 않음
  - `types/User.ts:8` — `name` 필드가 optional
- 🔍 판정 근거: diff 신규 라인이고 상위 null guard 없음 → 실제 NPE 발생 가능
- 🛠 권장 대응: **수정** — `user?.name ?? ''`로 방어

```diff
{diff hunk 원본, 최대 20줄}
```

</details>

<details>
<summary><b>#4</b> <code>api/auth.ts:20</code> · 💡 suggestion · <i>@alice</i> — 에러 처리 개선 <b>[수정]</b></summary>
...
</details>
````

##### Rich 포맷 세부 규칙

- `<summary>` 안에서는 **인라인 HTML만** 사용 (`<b>`, `<code>`, `<i>`). 블록 요소 금지 — GitHub 렌더러가 깨짐.
- `<details>` 내부는 일반 Markdown 가능 (불릿, diff 코드블록 등).
- `<details>` 간 빈 줄 1개 유지 (Markdown 파서가 구분하도록).
- `<summary>` 맨 끝에 `<b>[{권장}]</b>` 배지로 권장 대응 노출 → 접힌 상태에서도 액션 파악 가능.
- 헤더·대시보드·리뷰어 요약·다음 단계 섹션은 **flat과 동일** (접지 않음).

### Step 4.5: Save & (Optionally) Open

렌더링한 리뷰는 **항상 파일로 저장**한다. 채팅에는 flat 버전을 그대로 출력하고, 파일에는 `--rich` 여부에 따라 flat/rich 버전을 저장한다.

#### 저장 경로 규칙

```
~/.claude/reviews/{owner}/{repo}/pr-{number}-{YYYYMMDD-HHMMSS}.md
```

- `{owner}/{repo}`: `gh repo view --json nameWithOwner -q .nameWithOwner`의 결과
- 타임스탬프는 저장 시점 기준(`date +%Y%m%d-%H%M%S`). 같은 PR을 여러 번 리뷰해도 덮어쓰지 않고 이력을 남긴다.

디렉토리가 없으면 먼저 생성:
```bash
mkdir -p ~/.claude/reviews/{owner}/{repo}
```

#### 저장 절차

1. **채팅 출력**: Step 4의 flat 템플릿 결과 전체를 채팅에 출력.
2. **파일 저장**: `--rich` 없으면 flat 결과 그대로, 있으면 rich 템플릿으로 다시 렌더링한 결과를 Write 툴로 위 경로에 저장.
3. 저장 후 사용자에게 경로와 포맷을 알려준다:
   > `💾 저장됨 (flat): ~/.claude/reviews/{owner}/{repo}/pr-{number}-{ts}.md`
   또는
   > `💾 저장됨 (rich): ~/.claude/reviews/{owner}/{repo}/pr-{number}-{ts}.md`

#### VS Code로 열기 (`--open` / `-o` 지정 시)

열기 방식은 `--rich` 여부에 따라 달라진다.

**flat + `--open`** — 일반 소스 뷰로 열기:
```bash
code "~/.claude/reviews/{owner}/{repo}/pr-{number}-{ts}.md"
```

**rich + `--open`** — Markdown 프리뷰 모드로 열기 (`<details>`가 실제로 접힘 동작):
```bash
code "~/.claude/reviews/{owner}/{repo}/pr-{number}-{ts}.md" \
  && code --command "markdown.showPreview"
```
`--command` 플래그가 동작하지 않는 버전이면 파일만 열고 사용자에게 `Ctrl+Shift+V`로 프리뷰를 켜도록 안내.

- `code` 명령이 PATH에 없으면 알림: "VS Code CLI(`code`)가 PATH에 없습니다. VS Code에서 `Shell Command: Install 'code' command in PATH`를 실행하세요."
- 열기 후에도 Step 5로 이어서 피드백 처리 대화를 계속한다.

#### 프로젝트 git 비오염 보장

- 저장 경로는 사용자의 글로벌 `~/.claude/` 아래이므로 프로젝트 저장소와 무관 — 추가 `.gitignore` 작업 불필요.
- 사용자가 의도적으로 프로젝트 내 경로를 지정하지 않는 한 다른 위치에 쓰지 않는다.

### Step 5: Handle User Selection

사용자가 번호를 고르면 처리 방식은 해당 코멘트의 **타당성 판정**에 따라 달라진다.

**공통 처리**:
1. 해당 전역 번호 → 코멘트 매핑에서 파일/라인/본문/타당성/근거 확보 (대시보드 테이블이 마스터 인덱스)
2. Step 3.5에서 이미 읽은 상태라면 재확인만, 아니면 Read로 현재 상태 확인

**타당성별 기본 흐름**:
- **✅ Valid** → 수정안 제시 → 승인 후 Edit 적용 (자명한 오타/스타일은 바로 적용)
  - **권장 대응이 `이슈 생성`인 경우** → 이 PR에서 고치지 않고 **별도 이슈 초안** 작성 (제목·배경·제안·영향 범위 포함) → 사용자 승인 시 `ghflow:create-issue` 스킬을 호출해 이슈 등록 → PR 답글 초안 제공 ("이 건은 범위가 커서 issue #{NN}로 분리했습니다" 톤). `create-issue` 스킬이 없거나 실패하면 `gh issue create` 명령어를 출력해 사용자가 직접 실행할 수 있게 대체.
- **⚠️ Partial** → 어떤 부분만 반영할지 먼저 사용자와 합의, 이후 수정 (나머지를 이슈로 분리하기로 하면 위 ✅ Valid의 `이슈 생성` 흐름 재사용)
- **❌ Invalid** → 기본은 **반박 답글 초안** 작성 (판정 근거를 정중한 톤으로 정리). 사용자가 그래도 수정 원하면 수정 진행.
- **🤔 Unclear** → 확인해야 할 항목을 리스트로 제시하고 사용자에게 결정 요청. 필요 시 리뷰어에게 되물을 답글 초안도 제공.

**반박/답글 초안 형식** (Invalid·Unclear 공통):
```
> (원 코멘트 인용 1–2줄)

{근거 요약 2–3줄, 정중한 톤}
{필요하면 관련 코드 라인 링크: `path:line`}
```
사용자 승인 후 `gh api` PATCH/POST로 답글을 달거나, 수동 복붙용으로 출력만 하고 끝낼 수 있다 — 어느 쪽을 원하는지 물어본다.

**마무리**:
- 처리 완료된 항목은 대시보드 테이블의 해당 행을 `~~취소선~~` 처리하거나 `권장` 컬럼을 `완료 ✔`로 업데이트해 다시 출력
- 남은 항목을 다시 안내

## Guidelines

- **템플릿 일관성이 최우선**: 섹션 순서·헤더·라벨을 바꾸지 않는다. 데이터가 없으면 "없음"·"_없음_"·"(본문 없음)"으로 채운다.
- **전역 번호 유지**: 리뷰어가 달라도 `#1 → #2 → #3`로 이어지게 매긴다. 대시보드와 상세 블록이 같은 번호를 공유해야 한다.
- **채팅 vs 파일 포맷 분리**:
  - 채팅 출력은 **항상 flat**. `<details>` 태그 절대 사용 금지 (CLI에서 원시 태그로 노출됨).
  - 파일 저장만 `--rich`에 따라 분기.
- **태그 분류 기준**:
  - `🔴 blocking`: 리뷰어가 Changes Requested 상태이거나 본문에 "must", "required", "blocking", "should change" 등 명시
  - `❓ question`: 물음표로 끝나거나 "why", "어떻게", "이유" 같은 질문 톤
  - `💡 suggestion`: "consider", "how about", "nit", "could", "might" 등 제안 톤
  - `💬 note`: 위에 해당하지 않는 단순 코멘트/칭찬
- **Resolved threads**: `[RESOLVED]` 배지 + 본문 취소선. 대시보드 테이블·상세 블록에서 제외(또는 회색 톤으로 표시). 처리 순서 제안에도 포함하지 않음.
- **Draft PR**: 헤더에 `[DRAFT]` 배지, 리뷰는 그대로 표시.
- **Closed/Merged PR**: 헤더에 `[CLOSED]`/`[MERGED]` 배지, "PR이 이미 닫혔습니다" 한 줄 안내 후 리뷰 표시.
- **리뷰 없음**: 대시보드를 "아직 인라인 코멘트가 없습니다."로 대체, 상세/리뷰어 요약 섹션은 빈 섹션으로 유지("_없음_").
- **Rate limit**: 감지 시 사용자에게 알리고 재시도 제안.
- **diff 절삭**:
  - flat: 5줄 초과 시 `... (+N lines)` 한 줄 추가
  - rich: 20줄 초과 시 `... (+N lines)` (그 이하는 그대로 노출)
- **본문 길이**:
  - flat: 코멘트 본문은 첫 3줄만 노출, 초과 시 `…`
  - rich: 전체 본문 + 답글 스레드 전부 노출
- **타당성 평가 원칙**:
  - 리뷰어의 직급·권위가 아니라 **현재 코드 + PR diff**만 근거로 판정한다.
  - Changes Requested라도 ❌ Invalid가 될 수 있고, 단순 note라도 ✅ Valid가 될 수 있다.
  - 판정에 확신이 없으면 무리하게 ✅/❌를 부여하지 말고 🤔 Unclear로 분류 + 필요한 추가 정보 명시.
  - 취향 차이/스타일 논쟁은 기본 🤔 Unclear. 프로젝트 규칙(lint 설정, CLAUDE.md)과 충돌하면 그 규칙을 근거로 ✅/❌ 확정 가능.
  - 권장 대응은 여섯 가지 중 선택: **수정 / 검토 / 논의 / 반박 / 무시 / 이슈 생성** — Valid는 수정이 기본, Partial은 검토, Unclear는 논의, Invalid는 반박 또는 무시에 느슨하게 대응.
  - **`이슈 생성` 선정 기준** (Valid 또는 Partial 판정과 함께 쓰임):
    - (1) 리뷰어가 명시적으로 "이 PR 밖에서", "별도 작업", "follow-up", "out of scope" 류로 언급
    - (2) 지적은 맞지만 수정 범위가 PR 주제와 분리되어 크거나, 다른 시스템·계층·파일 범위를 건드려야 함 (예: "캐시 전략 전면 개편", "이 이슈는 설계 문서부터 다시 봐야 함")
    - (3) 리팩터링·성능 개선·테스트 보강 제안이 타당하지만 현 PR 목적(버그 수정 등)과 직교
    - 판단이 애매하면 대시보드 권장에 일단 `수정`으로 두고, 사용자와 논의 후 `이슈 생성`으로 전환하거나 그 반대로.
- **대시보드 테이블 정렬**:
  - 기본은 전역 번호(`#`) 오름차순
  - `처리 순서 제안`은 Valid(수정) → Valid(이슈 생성) → Partial → Unclear → Invalid 순, 각 그룹 내 번호순. `이슈 생성`은 Valid 안에서도 뒤로 미뤄 묶음 처리하기 편하게.
