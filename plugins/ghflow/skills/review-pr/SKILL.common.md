---
name: review-pr
model: sonnet
description: >
  PR(Pull Request)에 달린 리뷰 댓글을 불러와 정리하고, 각 피드백을 코드와 함께 검토할 수 있게 도와주는 스킬.
  사용자가 "PR 리뷰 확인", "리뷰 내용 봐줘", "리뷰 달린 거 확인해줘", "PR 피드백 정리", "#101 리뷰 검토해줘",
  "review-pr", "pr review check", "review comments 보여줘", "리뷰 코멘트 처리", "/review-pr" 등을 말하면 트리거한다.
  PR 번호를 인자로 받으면 해당 PR의 브랜치로 전환 후 리뷰를 검토하고, 없으면 현재 브랜치의 PR 리뷰를 검토한다.
  리뷰 내용 확인뿐 아니라 피드백 항목을 처리하는 것까지 적극적으로 도와줄 것.
  채팅에는 항상 flat 마크다운으로 결과를 출력한다. `--save` 를 주면 같은 결과를
  ~/.hbrness/reviews/{owner}/{repo}/ 아래 HTML 리포트로 저장하고, `--open` 을 주면 저장 후 브라우저로 연다.
  디폴트는 unresolved 스레드만 가져와 토큰을 절약한다. resolved 까지 보고 싶으면 `--all`.
  Usage: /review-pr [#PR번호] [--save|-s] [--open|-o] [--all|-a]
---

# Review PR Skill

PR에 달린 리뷰 댓글을 불러와 **고정된 템플릿**으로 정리하고, 각 피드백 항목을 코드와 함께 검토한다.

채팅 출력은 항상 flat 마크다운으로 한다. `--save` 또는 `--open` 을 받으면 사용자의 `~/.hbrness/reviews/` 아래에 정적 HTML 리포트(필요 시 옆에 review.json)를 추가로 만든다. HTML 은 단일 파일 self-contained 이며 브라우저로 열면 카드형 UI · 필터 · diff syntax-highlight 가 동작한다.

## Arguments

- `[#PR번호]` or `[PR번호]`: Optional. 검토할 PR 번호 (예: `#101` 또는 `101`). 생략하면 현재 브랜치의 PR을 사용.
- `--save` / `-s`: Optional. **HTML 리포트로 저장**한다. 옆에 동일 베이스명의 `.json` (renderer 입력)도 함께 남긴다. 디폴트는 저장하지 않고 채팅 출력만.
- `--open` / `-o`: Optional. 저장한 HTML을 기본 브라우저로 연다. `--save` 를 implies (자동 켜짐).
- `--all` / `-a`: Optional. **resolved 스레드까지 포함**해 가져온다. 디폴트(미지정)는 unresolved 만 fetch 해서 컨텍스트/토큰을 절약한다. resolved 갯수만 헤더에 노출됨. resolved 코멘트 본문을 다시 봐야 할 때만 켠다.

Examples:
- `/review-pr` — 현재 브랜치 PR 리뷰, unresolved 만, 채팅 출력만
- `/review-pr #101` — PR #101 리뷰, unresolved 만, 채팅 출력만
- `/review-pr 101 --save` — PR #101 리뷰, HTML 로 저장
- `/review-pr 101 -o` — PR #101 리뷰, HTML 저장 + 브라우저로 열기
- `/review-pr 101 --all` — PR #101 리뷰, resolved 포함 전부 fetch (저장 X)
- `/review-pr 101 -a -o` — PR #101 리뷰, resolved 포함 + HTML 저장 + 브라우저 열기

## Output Contract (중요)

출력 채널 두 개를 명확히 분리한다:

| 채널 | 포맷 | 트리거 |
|---|---|---|
| **채팅(Claude Code 대화)** | 항상 **flat 마크다운** | 모든 호출 |
| **저장 파일** (`.html` + `.json`) | 정적 HTML | `--save` 또는 `--open` |

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
- **저장이 요청된 경우에만** `~/.hbrness/reviews/{owner}/{repo}/pr-{number}-{YYYYMMDD-HHMMSS}.{html,json}` 으로 저장한다. 프로젝트 git에는 기록되지 않는다.

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
gh pr view {number} --json number,title,headRefName,state,baseRefName,isDraft,url,author,additions,deletions,changedFiles,body
```

**If no PR number:**
```bash
gh pr view --json number,title,headRefName,state,baseRefName,isDraft,url,author,additions,deletions,changedFiles,body
```
If no PR is associated with the current branch, inform the user and abort.

### Step 2: Switch Branch (only when PR number was explicitly provided)

If the PR's branch differs from the current branch:
1. Check for uncommitted changes: `git status --porcelain`. 있으면 먼저 경고.
2. 물어보기: `"PR #{n}의 브랜치(\`{headRefName}\`)로 전환할까요? (현재: \`{currentBranch}\`)"`
3. 승인 시: `gh pr checkout {number}`

거절 시에도 리뷰 데이터는 API로 확인 가능하므로 그대로 진행. 단 `repo_root` 기반 `vscode://` 링크가 검토 중 PR과 어긋날 수 있으니 사용자에게 알린다.

### Step 3: Fetch Review Data (GraphQL 단일 호출)

전체 PR 메타·review submission·reviewThread·인라인 코멘트를 **GraphQL 한 번**으로 받는다. 디폴트는 **unresolved 스레드만 처리**하며, resolved 본문은 컨텍스트에 적재하지 않는다 (`--all` 시에만 처리).

`{owner}/{repo}`: `gh repo view --json nameWithOwner -q .nameWithOwner`

`{repo_root}` (저장 시 vscode 링크용): `git rev-parse --show-toplevel`

#### 3.1 쿼리

```graphql
query($owner:String!,$repo:String!,$number:Int!) {
  repository(owner:$owner, name:$repo) {
    pullRequest(number:$number) {
      number title body state isDraft url
      additions deletions changedFiles
      headRefName baseRefName
      author { login }
      reviews(first: 50) {
        nodes { author { login } state body submittedAt }
      }
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          resolvedBy { login }
          path
          line
          comments(first: 30) {
            nodes {
              id
              databaseId
              author { login }
              body
              path
              line
              originalLine
              createdAt
              updatedAt
              lastEditedAt
              outdated
              url
              diffHunk
              replyTo { databaseId }
            }
          }
        }
      }
    }
  }
}
```

> 🔑 안정 식별자: `comments[].databaseId` (integer) 와 `reviewThreads[].id` (string) 는 재호출 사이에도 변하지 않는다. 채팅에 노출되는 `#1, #2 …` 는 매 호출마다 재배치될 수 있으므로 **모든 영속 처리(저장 파일, GitHub 답글, 델타 비교)는 `database_id` / `thread_id` 를 기준**으로 한다.

호출:
```bash
gh api graphql \
  -f owner={owner} -f repo={repo} -F number={number} \
  -f query="$QUERY"
```

#### 3.2 클라이언트 측 필터링

응답을 받은 직후, 처리 모드에 따라 다음을 수행한다.

| 모드 | 처리 |
|---|---|
| **디폴트** (resolved 숨김) | `reviewThreads.nodes` 중 `isResolved == false` 만 펼친다. resolved thread 의 코멘트 본문은 **읽지 않고**, `resolved_hidden_count` 만 센다. |
| **`--all`** | resolved 포함 전부 펼친다. resolved 코멘트는 `[RESOLVED]` 배지 + 본문 취소선으로 표시. |

`reviewThreads(first:100)` cap 을 초과하면 (응답에 `pageInfo.hasNextPage` 가 있을 경우) 사용자에게 알리고 `--all`/추가 페이지네이션 옵션을 안내한다 — 100 초과 PR 은 드물지만 가능.

#### 3.3 전역 번호 매기기

펼쳐진 thread 들을 **createdAt 오름차순**으로 정렬 → thread 단위로 첫 코멘트가 `#1, #2, ...` 를 받는다. thread 내 reply 는 같은 번호의 reply 트리로 묶는다 (별도 번호 부여 X).

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

### Step 4: Render Chat Output

채팅에는 **항상 아래 flat 마크다운 템플릿**을 그대로 출력한다. `<details>` 태그 절대 금지(CLI에서 raw 태그로 노출됨).

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

**분포**: ✅{N} · ⚠️{N} · ❌{N} · 🤔{N}  |  **미해결 스레드**: {N}건  |  **이슈 분리 제안**: {N}건  |  **resolved 숨김**: {N}건 (디폴트 모드일 때만; `--all` 이면 표시 생략)
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

##### 채팅 포맷 세부 규칙

- **대시보드 테이블 컬럼 순서 고정**: `#` · 판정 · 태그 · 위치 · 요약 · 권장
- 요약은 **15자 이내 한국어** 권장 (긴 경우 `…`)
- `권장` 컬럼 값은 `수정 / 검토 / 논의 / 반박 / 무시 / 이슈 생성` 중 하나
- 상세 블록은 각 코멘트당 **헤더 1줄 + 인용 ≤3줄 + 🔗/🔍/🛠 3줄 + diff ≤5줄** = 대략 8–12줄
- diff가 5줄 초과면 마지막에 `... (+N lines)` 추가
- 코멘트 본문은 3줄 초과 시 3줄 + `…` (중요 내용은 🔍 근거에서 다시 언급)
- `처리 순서 제안`은 Valid → Partial → Unclear → Invalid 순, 같은 그룹 내는 번호순

### Step 4.5: Save HTML Report (옵트인)

`--save` 또는 `--open` 이 켜져 있을 때만 수행한다. 꺼져 있으면 이 단계는 통째로 스킵.

#### 저장 경로

```
~/.hbrness/reviews/{owner}/{repo}/pr-{number}-{YYYYMMDD-HHMMSS}.html
~/.hbrness/reviews/{owner}/{repo}/pr-{number}-{YYYYMMDD-HHMMSS}.json
~/.hbrness/reviews/{owner}/{repo}/pr-{number}-latest.html  ← symlink → 위 최신 .html
~/.hbrness/reviews/{owner}/{repo}/pr-{number}-latest.json  ← symlink → 위 최신 .json
```

- `{owner}/{repo}`: `gh repo view --json nameWithOwner -q .nameWithOwner` 결과
- 타임스탬프: 저장 시점 (`date +%Y%m%d-%H%M%S`). 같은 PR을 여러 번 리뷰해도 덮어쓰지 않고 이력을 남긴다.
- **`pr-{number}-latest.*` 심링크는 `render.mjs` 가 자동 생성**한다. 브라우저 탭을 `pr-{n}-latest.html` 에 두면 다음 호출 후 새로고침만으로 갱신된 리포트를 본다.
- `.json` 은 `.html` 의 입력(중간 표현)이며 schema 는 이 스킬의 `schema.json` 참고.

#### 자동 델타 (재호출 시)

`render.mjs` 는 같은 디렉토리에서 직전 `pr-{number}-{ts}.json` 을 찾아 **databaseId 기준으로 비교**한다. 첫 호출이면 비교 대상이 없어 깔끔히 스킵.

| 변화 | 표시 |
|---|---|
| 이전엔 없던 코멘트 | 카드/대시보드에 `🆕 NEW` 배지, 헤더 stats strip 에 "🆕 신규 N건" |
| 같은 databaseId, 본문/수정시각 변경 | `✏️ EDITED` 배지 |
| outdated 전환 | `⏱ OUTDATED` 배지 |
| thread 에 신규 답글 추가 | `↳ +N` 배지 |
| 이전엔 있었던 databaseId 가 사라짐 | 대시보드 상단 노란 strip 에 목록 노출 (resolved / 숨김 / 삭제 모두 포함). `resolved_by` 가 있으면 함께 표기. |

채팅 채널에는 델타가 자동으로 표시되지 않는다. 사용자가 변경 사항을 묻거나 재호출 컨텍스트에서 필요하다고 판단되면 채팅에도 "이전 호출 이후 X건 신규/Y건 사라짐" 한 줄을 추가한다.

디렉토리가 없으면 먼저 생성:
```bash
mkdir -p ~/.hbrness/reviews/{owner}/{repo}
```

#### 4.5.1 review.json 작성

스킬 디렉토리의 `schema.json` 형식에 맞춰 JSON을 만들어 `.json` 경로에 Write.

스키마 핵심 필드 (자세한 타입은 `schema.json` 직접 참고):

```json
{
  "pr": { "number": 101, "title": "...", "url": "...", "state": "OPEN",
          "is_draft": false, "author": "...", "branch": {"head":"...","base":"..."},
          "changes": {"additions":N,"deletions":N,"files":N}, "body": "..." },
  "owner": "...", "repo": "...",
  "repo_root": "/abs/path/to/repo",
  "reviews": { "approved":N, "changes_requested":N, "commented":N,
               "by_reviewer": [ { "login":"...", "state":"APPROVED|CHANGES_REQUESTED|COMMENTED",
                                  "body":"...", "comment_numbers":[1,3] } ] },
  "resolved_hidden_count": N,
  "include_resolved": false,
  "comments": [
    { "number":1,
      "database_id":3243171001,
      "thread_id":"PRRT_kwDO...",
      "url":"https://github.com/.../pull/101#discussion_r3243171001",
      "updated_at":"2026-05-15T09:12:00Z",
      "last_edited_at":null,
      "is_outdated":false,
      "resolved_by":null,
      "validity":"valid|partial|invalid|unclear",
      "tag":"blocking|suggestion|question|note",
      "path":"...", "line":N, "reviewer":"...", "resolved":false,
      "body":"...", "summary":"<=15자 요약",
      "replies":[{"database_id":3243171501,"author":"...","body":"..."}],
      "related":[{"path":"...","line":N,"note":"..."}],
      "rationale":"1–2줄 근거",
      "recommendation":"수정|검토|논의|반박|무시|이슈 생성",
      "recommendation_reason":"한 줄 이유",
      "diff_hunk":"@@ ..." }
  ],
  "processing_order": [1,4,2,3,5],
  "generated_at": "{ISO 8601}"
}
```

전역 번호·판정·연관 위치 등 채팅 출력에서 이미 산출한 값을 그대로 채워 넣는다 — 두 채널이 같은 데이터로 만들어지도록.

#### 4.5.2 HTML 렌더링

스킬 디렉토리의 `scripts/render.mjs` 와 `template.html` 을 사용해 정적 HTML 을 만든다.

```bash
SKILL_DIR="${CLAUDE_PLUGIN_ROOT:-$HOME/.claude/plugins/marketplaces/hbrness/plugins/ghflow}/skills/review-pr"
node "$SKILL_DIR/scripts/render.mjs" \
  ~/.hbrness/reviews/{owner}/{repo}/pr-{n}-{ts}.json \
  "$SKILL_DIR/template.html" \
  ~/.hbrness/reviews/{owner}/{repo}/pr-{n}-{ts}.html
```

`CLAUDE_PLUGIN_ROOT` 환경변수가 없는 환경(다른 harness, dev install 등)에서는 `gh/codex` 등의 실제 설치 경로로 `SKILL_DIR` 만 바꿔서 호출한다.

#### 4.5.3 알림

저장 후 사용자에게 경로를 알린다:
> `💾 저장됨: ~/.hbrness/reviews/{owner}/{repo}/pr-{number}-{ts}.html (+ .json)`

#### 4.5.4 브라우저로 열기 (`--open` / `-o` 지정 시)

`--open` 이 켜져 있으면 (또는 사용자가 explicit `--open` 만 줘서 implicit `--save` 가 켜졌으면) HTML을 기본 브라우저로 연다.

```bash
# macOS
open "~/.hbrness/reviews/{owner}/{repo}/pr-{number}-{ts}.html"
# Linux (fallback)
xdg-open "~/.hbrness/reviews/{owner}/{repo}/pr-{number}-{ts}.html"
```

`open`·`xdg-open` 둘 다 없으면 알림으로 안내: "기본 브라우저 launcher가 없습니다. 파일 경로를 직접 여세요: {path}"

열기 후에도 Step 5로 이어서 피드백 처리 대화를 계속한다.

#### 프로젝트 git 비오염 보장

- 저장 경로는 사용자의 글로벌 `~/.hbrness/` 아래이므로 프로젝트 저장소와 무관 — 추가 `.gitignore` 작업 불필요.
- 사용자가 의도적으로 프로젝트 내 경로를 지정하지 않는 한 다른 위치에 쓰지 않는다.

### Step 5: Handle User Selection

사용자가 번호를 고르면 처리 방식은 해당 코멘트의 **타당성 판정**에 따라 달라진다.

**공통 처리**:
1. 해당 전역 번호 → 코멘트 매핑에서 파일/라인/본문/타당성/근거 확보 (대시보드 테이블이 마스터 인덱스)
2. Step 3.5에서 이미 읽은 상태라면 재확인만, 아니면 Read로 현재 상태 확인

**타당성별 기본 흐름**:
- **✅ Valid** → 수정안 제시 → 승인 후 Edit 적용 (자명한 오타/스타일은 바로 적용) → **수정 완료 답글 초안 제공** (아래 "답글 초안 형식" 참고)
  - **권장 대응이 `이슈 생성`인 경우** → 이 PR에서 고치지 않고 **별도 이슈 초안** 작성 (제목·배경·제안·영향 범위 포함) → 사용자 승인 시 `ghflow:create-issue` 스킬을 호출해 이슈 등록 → PR 답글 초안 제공 ("이 건은 범위가 커서 issue #{NN}로 분리했습니다" 톤). `create-issue` 스킬이 없거나 실패하면 `gh issue create` 명령어를 출력해 사용자가 직접 실행할 수 있게 대체.
- **⚠️ Partial** → 어떤 부분만 반영할지 먼저 사용자와 합의, 이후 수정 → 반영/보류 범위를 정리한 답글 초안 제공 (나머지를 이슈로 분리하기로 하면 위 ✅ Valid의 `이슈 생성` 흐름 재사용)
- **❌ Invalid** → 기본은 **반박 답글 초안** 작성 (판정 근거를 정중한 톤으로 정리). 사용자가 그래도 수정 원하면 수정 진행.
- **🤔 Unclear** → 확인해야 할 항목을 리스트로 제시하고 사용자에게 결정 요청. 필요 시 리뷰어에게 되물을 답글 초안도 제공.

**답글 초안 형식** (Valid 완료 / Partial 반영 / Invalid 반박 / Unclear 재질문 모두 공통):

> ⚠️ **리뷰어 멘션 필수** — 답글 초안의 **첫 줄은 반드시 `@{리뷰어 GitHub login}` 으로 시작**한다. 리뷰어가 알림을 받지 못하면 응답이 묻히므로 예외 없이 멘션을 단다. 리뷰어가 PR 작성자 본인이거나 봇(`[bot]` 접미사)인 명백한 경우에만 생략 가능. thread 의 원 코멘트 작성자(`comments[0].author.login`)를 그대로 쓴다. thread 내 여러 리뷰어가 섞여 있으면 마지막 코멘트 작성자를 우선하되, 필요 시 콤마로 복수 멘션(`@alice @bob`).

```
@{reviewer}

> (원 코멘트 인용 1–2줄)

{본문 2–3줄, 정중한 톤}
{필요하면 관련 코드 라인 링크: `path:line` — 수정 적용한 경우 변경 후 라인 우선}
```

본문 톤 가이드:
- **Valid 수정 완료**: "지적 감사합니다. {요약}으로 수정했습니다." + 변경 위치 링크
- **Partial 부분 반영**: 반영된 부분과 보류 사유를 한 줄씩
- **Invalid 반박**: 판정 근거를 사실 위주로, 단정보다 "확인해보니 ~~로 동작합니다" 톤
- **Unclear 재질문**: 알고 싶은 것을 글머리 기호로 1–3개

사용자 승인 후 `gh api` PATCH/POST로 답글을 달거나, 수동 복붙용으로 출력만 하고 끝낼 수 있다 — 어느 쪽을 원하는지 물어본다. 어느 경로든 멘션이 빠진 채로 PR 에 올라가면 안 된다.

**마무리**:
- 처리 완료된 항목은 대시보드 테이블의 해당 행을 `~~취소선~~` 처리하거나 `권장` 컬럼을 `완료 ✔`로 업데이트해 다시 출력
- 남은 항목을 다시 안내

## Guidelines

- **템플릿 일관성이 최우선**: 섹션 순서·헤더·라벨을 바꾸지 않는다. 데이터가 없으면 "없음"·"_없음_"·"(본문 없음)"으로 채운다.
- **전역 번호 유지**: 리뷰어가 달라도 `#1 → #2 → #3`로 이어지게 매긴다. 대시보드와 상세 블록이 같은 번호를 공유해야 한다.
- **#번호 vs databaseId**: `#N` 은 **이번 호출 한정 라벨**이다. resolved 상태가 바뀌거나 새 코멘트가 끼면 다음 호출에서 같은 코멘트가 다른 #번호를 받을 수 있다. 한 세션 안에서 다음 두 가지를 지킨다:
  - 같은 세션에서 사용자가 "3번 처리해줘"라고 했을 때, 이번 호출 채팅에 노출한 #3 의 `databaseId` 를 LLM 내부적으로 기억한다.
  - 그 사이에 `/review-pr` 이 재호출돼 새 채팅 블록이 등장했다면, **새 블록의 #번호 기준으로 해석**한다(이전 블록의 #번호는 더 이상 유효하지 않음). 만약 사용자가 가리키는 코멘트가 새 호출에서 사라졌으면(resolved/숨김) 처리하기 전에 명시적으로 안내한다.
  - 외부에 답글을 달거나 PR 코멘트를 가리킬 때는 항상 `database_id` 또는 `url` 을 쓴다. `#N` 만 적은 답글 초안은 며칠 뒤 재호출하면 의미가 어긋난다.
- **채팅 채널은 항상 flat 마크다운**: `<details>` 같은 HTML 태그는 절대 사용 금지 (CLI에서 raw 태그로 노출됨).
- **HTML 채널 (저장 시)**: Claude 가 HTML 을 직접 쓰지 않는다. `review.json` 만 schema 에 맞춰 작성하고 `render.mjs` 가 합성한다.
- **태그 분류 기준**:
  - `🔴 blocking`: 리뷰어가 Changes Requested 상태이거나 본문에 "must", "required", "blocking", "should change" 등 명시
  - `❓ question`: 물음표로 끝나거나 "why", "어떻게", "이유" 같은 질문 톤
  - `💡 suggestion`: "consider", "how about", "nit", "could", "might" 등 제안 톤
  - `💬 note`: 위에 해당하지 않는 단순 코멘트/칭찬
- **Resolved threads**:
  - **디폴트 (`--all` 미지정)**: resolved thread 는 fetch 단계에서 본문을 읽지 않는다. 헤더 분포 라인의 `resolved 숨김: {N}건` 으로만 노출. 대시보드 / 상세 / 처리 순서에서 모두 제외.
  - **`--all` 지정 시**: resolved 도 받아서 표시. 코멘트 헤더에 `[RESOLVED]` 배지 + 본문 취소선. 대시보드 행은 회색 톤 라벨(`~~`)로 두되 처리 순서 제안에서는 여전히 제외(이미 닫힌 논의이므로).
- **Draft PR**: 헤더에 `[DRAFT]` 배지, 리뷰는 그대로 표시.
- **Closed/Merged PR**: 헤더에 `[CLOSED]`/`[MERGED]` 배지, "PR이 이미 닫혔습니다" 한 줄 안내 후 리뷰 표시.
- **리뷰 없음**: 대시보드를 "아직 인라인 코멘트가 없습니다."로 대체, 상세/리뷰어 요약 섹션은 빈 섹션으로 유지("_없음_").
- **Rate limit**: 감지 시 사용자에게 알리고 재시도 제안.
- **diff 절삭 (채팅)**: 5줄 초과 시 `... (+N lines)` 한 줄 추가. (HTML 채널은 renderer 가 30줄 cap 으로 처리)
- **본문 길이 (채팅)**: 코멘트 본문은 첫 3줄만 노출, 초과 시 `…`. (HTML 채널은 renderer 가 전체 본문 + 답글 스레드 전부 노출)
- **답글에는 항상 리뷰어 멘션**:
  - PR 리뷰 코멘트에 답글을 다는 모든 경로(Valid 수정 완료 보고, Partial 부분 반영, Invalid 반박, Unclear 재질문, 이슈 분리 안내 등)에서 답글 초안의 **첫 줄은 `@{리뷰어 GitHub login}`** 으로 시작한다. 이 규칙은 사용자에게 보여주는 초안과 `gh api` 로 실제 게시할 본문 양쪽에 모두 적용된다.
  - 멘션 대상은 **thread 의 원 코멘트 작성자**가 기본. thread 안에서 다른 리뷰어가 추가 의견을 단 상태라면 마지막 코멘트 작성자를 같이 멘션(`@alice @bob`).
  - 예외: 리뷰어가 PR 작성자 본인이거나 봇(login 이 `[bot]` 으로 끝남)으로 자명한 경우만 멘션을 생략한다. 이 경우에도 사용자에게 멘션 생략 이유를 한 줄로 알린다.
  - 답글 게시 직전에 본문에 `@<login>` 토큰이 포함돼 있는지 한 번 더 확인한다. 누락되어 있으면 사용자 승인을 받지 않은 상태이므로 게시하지 않고 초안을 다시 보여준다.
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
