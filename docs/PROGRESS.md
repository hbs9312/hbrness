# hbrness — 진행 현황 및 이어갈 항목

현재 시점 기준: **v0.2.0 npm publish 완료 / 파이프라인 자동화 완료**. 이 문서는 지금까지의 이력, 남은 작업, 그리고 작업 중 드러난 비자명한 주의사항을 모아둔다.

---

## 1. 지금까지 한 것

### 1.1 배포 모델 전환 (마켓플레이스 → npm)

- **마켓플레이스 중심에서 npm 직접 설치로 전환**. GitHub 레포 `hbs9312/hbrness`(public) 신설.
- `package.json` + `bin/hbrness.js` 진입점. `files` 화이트리스트로 소스는 제외하고 `bin/`, `dist/`, `scripts/install/`, `LICENSE`, `README.md`만 tarball에 포함.
- MIT LICENSE 추가.
- `.gitignore`에 `node_modules/`, `*.tgz`, `.npm-debug.log*` 추가.

### 1.2 CLI (`scripts/install/`)

| 명령 | 동작 |
|---|---|
| `hbrness install <harness> [plugin]` | `dist/{harness}/{plugin}/skills|agents/*` 를 `~/.claude|.codex/skills/{plugin}-{name}` 로 심볼릭 링크 + Claude면 hooks 병합 |
| `hbrness uninstall <harness> [plugin]` | 우리 소유 심볼릭 제거 + 우리 소유 hook 항목 제거 |
| `hbrness list <harness>` | 설치 항목 나열 (심볼릭 target path로 플러그인명 역추론) |
| `hbrness plugins <harness>` | dist에 빌드된 플러그인 목록 |
| `hbrness doctor [harness]` | dangling symlink · stale hook path · 오래된 backup 탐지 |
| `hbrness repair [harness]` | doctor가 찾은 자동 수정 가능한 이슈 처리 |
| `hbrness update` | git clone 모드는 `git pull + build + 재링크`, npm 모드는 upgrade 안내 |

공통 플래그: `--dry-run`, `--json`, `--no-hooks` (install/uninstall), `--version`, `--help`.

### 1.3 Claude hooks 병합

- `dist/claude/{plugin}/hooks/hooks.json` → `~/.claude/settings.json.hooks` 에 병합
- `${CLAUDE_PLUGIN_ROOT}` 를 실제 dist 절대경로로 치환
- 각 항목에 `_hbrness: { plugin, installedAt }` 센티넬 부착 → uninstall 시 정확히 우리 것만 제거
- 재설치는 idempotent: 기존 우리 항목만 제거 후 재삽입 (중복 방지)
- 수정 전마다 `settings.json.hbrness-bak.<ISO-ts>` 백업
- 원자적 쓰기 (tmp + rename)
- `--no-hooks` 플래그로 옵트아웃 가능

### 1.4 리뷰 스킬 포맷 재설계 (`ghflow/review-pr`)

- **채팅 / 파일 이원 채널** — 채팅은 항상 flat(CLI 친화), 파일은 `--rich`/`-r` 플래그로 rich(`<details>` 접힘 포함)
- **한눈 대시보드 테이블** 최상단 배치 (#, 판정, 태그, 위치, 요약, 권장)
- **판정별 상세 그룹** (✅ Valid / ⚠️ Partial / 🤔 Unclear / ❌ Invalid)
- 기존 "액션 아이템" 섹션 제거 (대시보드가 대체)
- `--open` 동작: flat이면 소스뷰, rich면 `markdown.showPreview`로 접힘 동작
- **토큰 절약 개편 (2026-04-29)**:
  - **GraphQL 단일 호출**로 통합 (REST + 2× GraphQL → 1× GraphQL `pullRequest` 쿼리)
  - **디폴트는 unresolved 스레드만** fetch — resolved 본문은 컨텍스트에 적재하지 않고 `resolved 숨김: N건` 카운트만 노출
  - `--all`/`-a` 플래그로 resolved 포함 모드 옵트인
  - flat 모드는 `diffHunk` 필드 미요청 (rich 만 포함) — 어차피 출력 단계에서 5줄로 절삭되던 hunk 가 컨텍스트에도 안 들어옴
  - 평균적인 PR(resolved ~50%) 기준 인라인 코멘트 영역 토큰 약 40~55% 절감

### 1.5 CI / Publish 자동화

- `.github/workflows/ci.yml` — push/PR마다 build + validate + CLI smoke + `npm pack --dry-run`
- `.github/workflows/publish.yml` — GitHub Release 생성 시 Trusted Publishing(OIDC)으로 자동 `npm publish --provenance --access public`
- Node 24 사용 (npm 11+ 번들 필요 — 하위 내용 주의사항 참조)
- README에 npm / license / node 뱃지 추가

### 1.6 npm 배포 이력

| 버전 | 상태 | 설명 |
|---|---|---|
| 0.1.0 | ✅ on registry | 수동 publish (OTP 사용, provenance 없음) |
| 0.1.1 | 태그·release만 존재 | publish 실패 (404 — npm 10.8 이슈) |
| 0.1.2 | 태그·release만 존재 | publish 실패 (npm 자체 업그레이드 시 의존성 깨짐) |
| 0.1.3 | ✅ on registry | Node 24 전환 후 Trusted Publishing 성공. provenance 서명 첨부 |
| 0.2.0 | ✅ on registry | doctor/repair/update 기능 추가. MINOR bump. |

### 1.7 커밋 이력

모든 변경은 `main` 브랜치에 순차 커밋됨. 커밋 분리 기준:
- 리뷰 포맷 재설계 · npm CLI · 라이선스/패키징 · CI/Publish workflow · hooks merging · doctor/repair · update — 각 기능 단위로 분리 커밋.

---

## 2. 남은 것 (할 일)

우선순위 3단계로 분류.

### 🔴 지금 하면 바로 효과 있음

1. **README 업데이트**
   - `doctor`, `repair`, `update` 명령이 README에 아직 없음 — 공개 사용자가 인지 못 함
   - CLI 명령 목록 / 옵션 / 예제 업데이트

2. **CHANGELOG.md 추가**
   - 현재 버전별 변경사항은 GitHub Releases의 auto-generated notes만 존재
   - 수동으로 기록되는 CHANGELOG가 있으면 히스토리 추적이 쉬워짐
   - `npm version` hook이나 `standard-version`/`changesets` 도입 고려

3. **git config 전역 identity 설정** (사용자 직접 수행)
   - 현재 커밋 author가 `seok@Seokui-MacBookPro.local` 로컬 hostname
   - GitHub 프로필에 커밋이 연결 안 됨
   - 해결: `git config --global user.name "hbs9312"` + `git config --global user.email hbs9312@gmail.com`

### 🟡 이어서 하면 좋음

4. **CI 강화**
   - 현재 CI는 `install --dry-run` smoke 하나뿐
   - `doctor`, `repair`, `update --dry-run` 경로도 돌려야 regression 잡힘
   - 격리 HOME 환경 만들어서 실제 `install` → `uninstall` 왕복까지 CI에서 확인

5. **actions 버전 업 / Node 24 default 준비**
   - `actions/checkout@v4`, `setup-node@v4`, `setup-python@v5` 가 Node 20 기반이라 deprecation 경고
   - 2026-06-02 부터 Node 24 강제 적용. 그 전에 action 최신 버전 확인 or `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true` 환경변수 설정

6. **Codex hook-capable plugin smoke**
   - `llm-kb` 이후 Codex root `hooks.json` 산출과 local marketplace 등록 경로가 생김
   - 남은 작업은 실제 Codex 재시작 후 hook fire 여부를 smoke 하는 것

### 🟢 여유 생길 때

7. **자동화 테스트 프레임워크 도입**
   - Node 내장 `node:test` 도입
   - `tests/codex-local-plugin.test.js` 가 임시 HOME 에서 Codex hook-capable plugin install → doctor clean → fault injection → repair 회복 경로를 검증
   - 남은 작업은 Claude hook merge, generic installer, update 경로까지 테스트 범위 확대

8. **State store**
   - 현재는 심볼릭 target path 스캔 + `_hbrness` 센티넬로 상태 추론
   - `~/.hbrness/state.json` 도입 시 이력·버전·옵션 기록 가능 → `update`, `doctor` 정확도 상승
   - 파일 이름 변경이나 수동 이동에 대한 취약성 개선

9. **Manifest JSON per-plugin**
   - 플러그인별로 "이 디렉토리는 skills, 이 파일은 hooks, 이 디렉토리는 agents"를 명시적 선언
   - 현재 스캐닝 컨벤션 의존 대체
   - 플러그인 종류·구조 다양해질 때 필요

10. **실패 release 정리** (선택)
    - `v0.1.1`, `v0.1.2` 태그·release는 publish 실패 이력
    - 정리할지 기록으로 남길지 판단 필요
    - 정리한다면: `git tag -d`, `gh release delete`, remote에서 force delete

11. **npm `0.1.0` deprecate**
    - 수동 publish라 provenance 없음
    - `npm deprecate hbrness@0.1.0 "use 0.1.3 or later"` 고려

12. **계정 보안**
    - npm에 security key 1개만 등록됨 — 하나 더 추가 (YubiKey or 다른 디바이스 passkey)
    - recovery codes 패스워드 매니저 + 종이 이중 저장 확인

---

## 3. 주의사항 / 함정 / 비자명한 결정

### 3.1 npm Trusted Publishing은 npm 11+ 필요

- Node 20/22 번들 npm은 10.8.x → provenance 서명은 성공하나 **publish PUT에서 404** 반환 (auth 실패를 404로 마스킹)
- `npm install -g npm@latest` 로 인라인 업그레이드하면 의존성이 깨짐 (`Cannot find module 'promise-retry'`)
- **해결: Node 24 사용** (`actions/setup-node@v4` with `node-version: '24'`). npm 11 번들되어 있음
- 작업 기록에서 배운 것이라 workflow 주석에도 같은 내용 명시됨

### 3.2 설치 방식은 "user-level 심볼릭", plugin 시스템 아님

- `~/.claude/plugins/` (Claude의 공식 plugin cache)가 아니라 `~/.claude/skills/<plugin>-<name>/` 에 심볼릭 링크
- 이유: Claude Code plugin 시스템 내부 API에 의존하면 버전 변동에 취약. user-level skills 디렉토리는 안정 API
- 대가: 플러그인 네임스페이스(`ghflow:review-pr`)는 잃고 prefix(`ghflow-review-pr`)만 보존
- Codex 동일 (`~/.codex/skills/<plugin>-<name>/`)

### 3.3 심볼릭이라 dist가 이동하면 링크 깨짐

- npm 패키지 설치 위치 (`node_modules/hbrness/dist/...`) 기준으로 링크
- `npm update -g hbrness` 로 업그레이드하면 이전 버전 `node_modules` 경로가 사라지면서 링크 전부 dangling
- 해결: 업그레이드 후 **`hbrness install <harness>` 재실행** (README에 명시 필요 — todo §2.1)
- `hbrness doctor` 가 dangling을 찾아주고 `repair`가 정리해주긴 함

### 3.4 Codex hooks는 local plugin registration 경로를 사용

- user-level skill symlink만으로는 Codex가 plugin root `hooks.json` 을 로드하지 않는다.
- hook-capable Codex 플러그인은 추가로 `~/plugins/<plugin>` symlink, `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>` copy, `~/.agents/plugins/marketplace.json`, `~/.codex/config.toml` enable 항목과 `[features] codex_hooks = true`, `plugin_hooks = true` 를 설치한다.
- Codex hook command 는 workspace cwd 에서 실행되므로 cache copy 의 `hooks.json` 안 `./hooks/...` 같은 plugin-relative 경로는 install 시 absolute path 로 rewrite 한다.
- 스킬 discoverability는 기존 `~/.codex/skills/<plugin>-<name>` symlink가 계속 담당하고, 훅 로드는 Codex local plugin registration이 담당한다.
- 실제 훅 발화는 Codex 재시작 후 smoke 필요.

### 3.5 Hooks 병합 시 `_hbrness` 센티넬이 유일한 소유권 표식

- 사용자가 `settings.json`을 수동 편집해 센티넬을 지우면, **우리는 그 항목을 우리 것으로 인식하지 못함**
- uninstall로 지워지지 않고 남음 → 수동 삭제 필요
- 반대로 사용자가 수작업으로 `_hbrness` 필드를 붙이면 우리 uninstall이 엉뚱하게 지울 수 있음
- 실제 발생 가능성 낮지만 문서화 필요

### 3.6 Backup은 누적되고 자동 삭제 안 됨

- `settings.json.hbrness-bak.<ts>` 는 수정 때마다 쌓임
- 현재는 `hbrness doctor`가 10개 초과 시 info 수준으로 경고 + `repair`가 최근 5개만 남기고 정리
- 자동 prune은 일부러 안 함 (사용자 데이터라 명시적 요청 시에만 삭제)

### 3.7 `--rich` 는 **파일에만 적용**. 채팅 출력은 항상 flat

- `<details>` HTML 태그가 CLI 터미널에 그대로 노출되면 오히려 노이즈
- 설계상 VS Code Markdown preview / GitHub 웹에서만 접힘 효과 발휘
- `--open` 과 조합하면 VS Code preview 모드로 열어 접힘 동작 확인 가능

### 3.8 Samsung Pass QR 가로채기 함정 (개발 외 기록)

- QR 스캔 시 삼성 OS가 기본 카메라에서 패스키로 해석해 Samsung Pass에 저장하는 흐름 존재
- npm TOTP 설정 시 `Add authenticator app` 경로의 QR은 **Google Authenticator 앱 내부 스캐너**로 찍어야 TOTP로 인식됨
- 카메라 앱 사용 금지

### 3.9 GitHub Release 생성이 publish 게이트

- 현재 workflow 트리거는 `on: release: types: [published]`
- 즉 `npm version patch && git push --follow-tags` 만으로는 publish 안 됨
- **`gh release create <tag>` 가 유일한 publish 발동점**
- 의도적 설계 — 실수 방지 게이트 역할
- 대안(aggressive): `on: push: tags: ['v*']` 로 바꾸면 태그 push만으로 자동 publish. 단 실수 리스크 큼

### 3.10 태그와 release는 커밋을 가리킴. tag 이동은 force-push 필요

- 예: workflow 수정 후 기존 `v0.1.2` release에 반영하려면 tag를 새 커밋으로 옮겨야 함
- `git push --force-with-lease origin v0.1.2` 필요 — 시스템 권한에서 막힐 수 있음
- 대신 **새 버전 번호로 patch bump**하는 게 깔끔 (이번 세션에서 0.1.2 실패 후 0.1.3으로 넘어간 이유)

---

## 4. 다음 릴리스 표준 절차

```bash
# 1. 코드 수정 → 커밋 → push (이번에 달라지는 부분)
git add ... && git commit -m "..."
git push origin main

# 2. 버전 bump
npm version patch      # 0.2.0 → 0.2.1
# 또는
npm version minor      # 0.2.x → 0.3.0  (새 기능일 때)
# 또는
npm version major      # 0.x.x → 1.0.0  (호환성 깨지는 변경)

# 3. 태그까지 push
git push --follow-tags

# 4. Release 생성 → 이 순간 자동 publish 발동
gh release create v0.2.1 --title v0.2.1 --generate-notes

# 5. 2-3분 후 검증 (선택)
npm view hbrness version
```

로컬 머신에서는 OTP·토큰 입력 없음. 실수로 publish되는 경로 없음.

---

## 5. 환경 재구성 빠른 참고

### 새 머신에서 dev 시작
```bash
git clone https://github.com/hbs9312/hbrness.git
cd hbrness
# Python 3 + Node 20+ 필요
./scripts/build.sh all
./scripts/validate.sh
```

### 사용자로서 설치
```bash
npm install -g hbrness
hbrness install claude         # 전체 플러그인
hbrness install claude ghflow  # 특정 플러그인만
hbrness doctor claude          # 상태 점검
```

### 버전 업그레이드
```bash
npm install -g hbrness@latest
hbrness install claude         # 심볼릭 재연결 (dangling 방지)
```

---

*이 문서는 세션 간 핸드오프용이다. 이 파일 자체도 프로젝트 진행에 맞춰 업데이트되어야 한다.*
