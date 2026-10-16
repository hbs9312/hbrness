---
name: ui-check
description: "사용자의 실제 화면·마우스·키보드를 점유하지 않고 웹 UI 를 확인한다. 헤드리스 브라우저로 화면을 캡처·탐색하고(Playwright CLI·스크립트, Playwright MCP --headless), Docker 컨테이너에서 visual regression 기준 이미지를 만들고 비교한다. '화면 확인해줘', 'UI 잘 나오는지 봐줘', '스크린샷 찍어줘', '모바일로도 찍어줘', '다크모드 화면', 'visual regression', '스냅샷 기준 갱신', 'CI 랑 스크린샷이 달라', '한글 폰트 깨져', 'Playwright MCP 헤드리스로 설정', '창 안 뜨게', '내 화면 건드리지 말고', '/testflow:ui-check' 등에 트리거. '헤드리스'라는 말이 없어도 에이전트가 웹 화면을 눈으로 확인해야 하면 쓴다. 쓰지 않는 경우: 사용자가 자기 브라우저·실제 창에서 보여 달라고 할 때(computer-use 계열), Orca 내장 브라우저 페이지, 네이티브 데스크톱·모바일 앱 조작(다른 방식 안내만), Figma 디자인 확인. Usage: /testflow:ui-check [<url> | vr test|update|build|clean | setup-mcp | check]"
argument-hint: "[<url> | vr test|update|build|clean | setup-mcp | check]"
tools: [shell, file:read, file:write, file:edit]
effort: medium
model: inherit
---

# testflow:ui-check — 사용자 화면을 건드리지 않고 웹 UI 확인

에이전트가 UI 를 확인하는 동안 사용자는 자기 화면을 계속 쓴다. 그래서 이 스킬은 브라우저를 **항상 헤드리스**로 띄우고, 화면이 필요한 비교는 Docker 컨테이너 안에서 돌린다.

## 원칙

1. **사용자의 디스플레이·마우스·키보드를 쓰지 않는다.** `headless: false`, `--headed`, `npx playwright open`·`codegen`, 호스트 화면을 조작하는 computer-use 도구는 사용자가 명시적으로 원할 때만 쓴다.
2. **구조로 먼저 확인한다.** 접근성 스냅샷·텍스트로 확인할 수 있으면 그걸로 끝낸다. 스크린샷은 레이아웃·색·폰트처럼 눈으로 봐야 할 때 찍는다.
3. **사용자 환경을 바꾸기 전에 묻는다.** MCP 설정 추가·변경, 브라우저 다운로드(수백 MB), 첫 Docker 이미지 빌드(수 GB), 프로젝트 의존성 추가가 여기에 해당한다.
4. **실 계정 비밀번호·실 API 키를 쓰지 않는다.** 로그인이 필요하면 테스트 계정으로 만든 storage state 파일을 쓴다.
5. **산출물은 `<project-root>/.testflow/`** 에 둔다 (스크린샷 `screenshots/`, 임시 스크립트 `tmp/`, MCP 출력 `mcp/`). 스크립트가 `.gitignore` 에 `.testflow/` 를 한 번만 추가한다.

## 0. 요청 분류

`$ARGUMENTS` 와 사용자 요청으로 경로를 고른다.

| 요청 | 경로 |
|---|---|
| `check`, 이 프로젝트에서 처음 쓸 때 | §1 환경 점검 |
| URL 하나, 화면 몇 장 확인 ("화면 잘 나와?", "모바일도", "다크모드") | §2 캡처 |
| 클릭·입력·여러 단계 흐름 확인 | §3 탐색 |
| `vr ...`, 기준 이미지 비교·갱신, CI 와 스크린샷이 다름, 폰트 깨짐 | §4 visual regression |
| `setup-mcp`, "Playwright MCP 헤드리스로 설정" | §5 MCP 설정 |
| 웹이 아닌 대상(Linux GUI 앱, macOS·Windows 앱, Android·iOS), 브라우저 주소창·네이티브 다이얼로그 생김새, 클라우드 병렬 실행 | `${PLUGIN_ROOT}/references/other-methods.md` 를 읽고 선택지와 비용만 안내한다. 실행 절차는 아직 없다. |

## 1. 환경 점검

```bash
bash "${PLUGIN_ROOT}/scripts/check_env.sh"
```

아무것도 바꾸지 않고 `KEY=VALUE` 를 출력한다.

| 키 | 보는 것 |
|---|---|
| `PROJECT_PLAYWRIGHT` | 프로젝트에 설치된 Playwright 버전. `none` 이면 §3B·§4 를 못 쓴다 |
| `BROWSER_CACHE` | 받아 둔 브라우저. `empty` 면 첫 캡처 때 설치가 필요하다 |
| `DOCKER` | `running` 이어야 §4 를 쓴다 |
| `MCP_PLAYWRIGHT` | `<범위>:<이름>:<headless\|HEADED\|remote>:<isolated\|persistent>`. 설정마다 한 줄, 없으면 `none` |
| `WARN` | 그대로 사용자에게 전한다. `HEADED` MCP 는 쓰지 말고 §5 로 고치자고 제안한다 |

## 2. 캡처 (한 화면)

1. **URL 정하기.** 사용자가 준 URL 을 쓴다. 없으면 `package.json` 의 dev 스크립트·README·프레임워크 설정에서 포트를 추정하고 사용자에게 확인한다.
2. **실행.**
   ```bash
   bash "${PLUGIN_ROOT}/scripts/capture.sh" <url> [옵션]
   ```
   기본값은 데스크톱 1440x900, `ko-KR`, `Asia/Seoul`, chromium 헤드리스다.

   | 옵션 | 쓰는 때 |
   |---|---|
   | `--device "Pixel 7"` | 모바일 (chromium) |
   | `--device "iPhone 15"` | iOS 모양 확인. 기기 기본 브라우저인 webkit 이 필요하다 |
   | `--color-scheme dark` | 다크모드 |
   | `--wait-for "<selector>"` | 데이터가 늦게 그려질 때. `networkidle` 대신 특정 요소를 기다린다 |
   | `--wait-ms <ms>` | 기다릴 요소가 마땅치 않을 때만 |
   | `--full-page` | 스크롤 전체. 세로가 아주 길면 이미지를 읽을 때 축소돼 글자가 안 보인다. 특정 구역만 볼 거면 §3 에서 요소 스크린샷을 찍는다 |
   | `--viewport WxH`, `--load-storage <file>`, `--out <path>` | 뷰포트 지정, 로그인 상태 불러오기, 저장 경로 지정 |

3. **출력 처리.**
   - `SCREENSHOT=<경로>` → 그 이미지를 Read 해서 확인하고, 본 것과 경로를 보고한다.
   - `URL_UNREACHABLE=1` → dev 서버가 꺼져 있다. 사용자에게 알리고, 띄우라고 하면 백그라운드로 띄운 뒤 다시 찍는다. 띄운 서버는 §6 에서 끈다.
   - `NEED_BROWSER_INSTALL=1` → `INSTALL_CMD` 를 보여주고 다운로드 용량(chromium headless shell 약 200MB)을 알린 뒤, 승인받으면 실행하고 다시 찍는다.
   - 그 밖의 실패 → 출력 끝부분을 보고 `${PLUGIN_ROOT}/references/troubleshooting.md` 에서 증상을 찾는다.

## 3. 탐색 (클릭·입력·여러 단계)

아래 순서로 처음 되는 방법을 쓴다.

**A. Playwright MCP** — 이 세션에 `browser_navigate` 같은 도구가 보이고, §1 의 `MCP_PLAYWRIGHT` 가 `headless` 일 때.
- `browser_navigate` → `browser_snapshot`(접근성 트리)으로 상태 확인 → `browser_click`·`browser_type` 등으로 조작 → 눈으로 봐야 할 때만 `browser_take_screenshot` → 끝나면 `browser_close`.
- 스냅샷·스크린샷이 파일 링크로 오면(`.testflow/mcp/...`) 그 파일을 Read 한다.
- `HEADED` 면 쓰지 않는다. 사용자 화면에 창이 뜬다.

**B. 임시 Playwright 스크립트** — 프로젝트에 `@playwright/test` 나 `playwright` 가 있을 때.
- `${PLUGIN_ROOT}/references/web-headless.md` §2 템플릿으로 `.testflow/tmp/explore.mjs` 를 만들고 `node .testflow/tmp/explore.mjs <url>` 로 실행한다. 프로젝트 루트에서 실행해야 모듈을 찾는다.
- `chromium.launch()` 는 기본값(헤드리스)으로 둔다. `headless: false` 를 넣지 않는다.
- `ariaSnapshot()` 출력으로 구조를 보고, 필요한 화면만 `.testflow/screenshots/` 에 찍어 Read 한다.

**C. 둘 다 안 되면** §2 캡처로 확인할 수 있는 만큼 확인하고, 상호작용 확인에는 MCP 설정(§5)이나 프로젝트에 Playwright 추가가 필요하다고 알린다. 의존성을 임의로 추가하지 않는다.

## 4. Visual regression (Docker)

기준 이미지를 만들 때와 비교할 때 같은 컨테이너 이미지를 써서 macOS·CI 렌더링 차이를 없앤다. 동작 방식과 CI 연결은 `${PLUGIN_ROOT}/references/visual-regression.md` 에 있다.

조건: 프로젝트에 `@playwright/test` 와 `toHaveScreenshot` 테스트, 저장소 루트에 lockfile(npm·pnpm·yarn), `DOCKER=running`.

```bash
bash "${PLUGIN_ROOT}/scripts/vr.sh" test   [--dir <subdir>] [--platform linux/amd64] [-- <playwright test 인자>]
bash "${PLUGIN_ROOT}/scripts/vr.sh" update [--dir <subdir>] [-- tests/home.spec.ts]
bash "${PLUGIN_ROOT}/scripts/vr.sh" build | clean
```

- **첫 실행 전**: `docker image ls testflow-pw` 에 맞는 이미지가 없으면, Playwright 이미지(약 3.5GB)를 받고 컨테이너용 `node_modules` 를 따로 설치한다고 알리고 확인받는다.
- **`update` 는 사용자가 화면 변경을 의도했다고 확인한 뒤에만** 실행한다. `--` 뒤에 테스트 파일이나 `-g <이름>` 을 줘서 범위를 좁힌다.
- **결과 읽기**: `RESULT=fail` 이면 `DIFF=` 이미지를 Read 하고, 같은 폴더의 `*-expected.png`·`*-actual.png` 와 비교해 무엇이 바뀌었는지 보고한다.
- **기준 이미지(`*-linux.png`)는 반드시 vr.sh 로 만든다.** 호스트 macOS 에서 `npx playwright test` 를 돌리면 Playwright 가 `*-darwin.png` 를 찾아서 다른 기준과 비교하게 된다.
- 테스트가 호스트에 떠 있는 서버를 보면 컨테이너에서 `localhost` 로 닿지 않는다. `playwright.config` 의 `webServer` 로 컨테이너 안에서 서버를 띄우는 게 가장 쉽다. 안 되면 troubleshooting 의 `host.docker.internal` 항목을 본다.
- 끝나면 `vr.sh clean` 으로 node_modules 볼륨을 지울 수 있다. 이미지는 다음 실행을 위해 남긴다.

## 5. Playwright MCP 헤드리스 설정

1. `${PLUGIN_ROOT}/references/web-headless.md` §1 을 읽는다.
2. 지금 하네스(`{HARNESS_NAME}`)에 맞는 설정 위치와 범위(프로젝트 공유 / 개인)를 사용자와 정한다.
3. 바꿀 내용을 그대로 보여주고 승인받은 뒤 적용한다. 기존 Playwright MCP 설정이 있으면 덮어쓰지 말고 `--headless` 를 더하는 쪽으로 고친다.
4. `check_env.sh` 로 `headless` 가 찍히는지 확인한다.
5. 이미 떠 있는 세션에는 새 MCP 도구가 바로 붙지 않는다. 새 세션에서 쓰라고 알리고, 이번 세션의 확인은 §2·§3B 로 한다.

## 6. 정리

- 에이전트가 띄운 dev 서버를 끈다.
- `.testflow/tmp/` 의 임시 스크립트를 지운다. 스크린샷은 남기고 경로를 알린다.
- MCP 브라우저를 썼으면 `browser_close`.

## 보고

- 본 화면의 파일 경로, 확인한 것과 이상해 보이는 것, 사용한 방식(캡처 / MCP / 스크립트 / vr).
- 헤드리스 캡처는 실제 브라우저와 폰트·배율·OS 위젯이 다를 수 있다. 차이가 판단에 영향을 주면 `${PLUGIN_ROOT}/references/fidelity.md` 를 근거로 함께 적는다.

## References

| 파일 | 내용 |
|---|---|
| `${PLUGIN_ROOT}/references/web-headless.md` | Playwright MCP 하네스별 설정, 탐색 스크립트 템플릿, `playwright.config` 권장값 |
| `${PLUGIN_ROOT}/references/visual-regression.md` | vr.sh 동작, 기준 이미지 규칙, CI 연결, 한계 |
| `${PLUGIN_ROOT}/references/fidelity.md` | 헤드리스 스크린샷이 실제와 달라지는 지점, 캡처 체크리스트 |
| `${PLUGIN_ROOT}/references/troubleshooting.md` | 증상별 해결 |
| `${PLUGIN_ROOT}/references/other-methods.md` | Xvfb, macOS VM, 클라우드 샌드박스, 모바일 — 안내용 |
