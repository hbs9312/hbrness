# 웹 헤드리스 — Playwright MCP · 탐색 스크립트 · 설정 권장값

확인 기준: Playwright 1.64.1, @playwright/mcp 0.0.83 (2026-10-16). 버전을 올리면 `npx @playwright/mcp@<버전> --help` 로 플래그를 다시 확인한다.

## 1. Playwright MCP 를 헤드리스로

Playwright MCP 는 스크린샷 대신 **접근성 스냅샷**(역할·이름 트리)을 돌려줘서 좌표를 추측하지 않는다. 다만 **기본값이 headed** 라서 `--headless` 를 빼면 사용자 화면에 브라우저 창이 뜬다.

권장 서버 명령:

```text
npx @playwright/mcp@0.0.83 --headless --isolated --viewport-size 1440x900 --output-dir .testflow/mcp
```

| 인자 | 이유 |
|---|---|
| `@0.0.83` (버전 고정) | `@latest` 는 서버가 뜰 때마다 새 버전을 받는다. 올릴 때 `npm view @playwright/mcp version` 으로 확인하고 바꾼다 |
| `--headless` | 창을 띄우지 않는다 |
| `--isolated` | 프로필을 메모리에만 둔다. 빼면 워크스페이스마다 디스크 프로필(macOS `~/Library/Caches/ms-playwright/mcp-{channel}-{hash}`)을 쓰는데, 이 프로필은 브라우저 하나만 열 수 있어서 같은 프로젝트에 세션 두 개가 붙으면 충돌한다 |
| `--viewport-size 1440x900` | 형식이 `WxH` 다. Playwright CLI(`"1440,900"`)와 다르다 |
| `--output-dir .testflow/mcp` | 이름 없이 저장하는 스크린샷·스냅샷 위치. 이름을 준 파일은 워크스페이스 루트 기준으로 저장된다 |

브라우저:
- 기본은 설치된 **Google Chrome** 을 헤드리스로 쓴다. 헤드리스라 창은 뜨지 않고, 사용자 Chrome 프로필도 건드리지 않는다.
- Chrome 이 없으면 `--browser chromium` 을 더하고 `npx @playwright/mcp@0.0.83 install-browser chrome-for-testing` 으로 브라우저를 받는다 (안 받으면 `Browser "chrome-for-testing" is not installed` 에러).

자주 더하는 인자:
- 로그인 유지: `--isolated --storage-state <file>`. 파일은 테스트 계정으로 만든다.
- 모바일: `--device "iPhone 15"` 또는 `--mobile` (Chromium 이면 Pixel, WebKit 이면 iPhone).
- 요청 거르기: `--allowed-origins "http://localhost:3000;https://cdn.example.com"`, `--blocked-origins ...`. 공식 help 에 적힌 대로 **보안 경계가 아니고 리다이렉트에는 걸리지 않는다.** 앱이 쓰는 CDN·API origin 을 빠뜨리면 페이지가 깨진다.

### Claude Code

프로젝트 공유(`.mcp.json`, 커밋 대상):

```bash
claude mcp add playwright -s project -- npx @playwright/mcp@0.0.83 --headless --isolated --viewport-size 1440x900 --output-dir .testflow/mcp
```

`--` 뒤가 MCP 서버로 가는 인자다. `--` 를 빼면 claude 가 `--headless` 를 자기 옵션으로 읽으려다 실패한다. 개인 설정만 바꾸려면 `-s local`(기본) 또는 `-s user`.

만들어지는 `.mcp.json`:

```json
{
  "mcpServers": {
    "playwright": {
      "command": "npx",
      "args": ["@playwright/mcp@0.0.83", "--headless", "--isolated", "--viewport-size", "1440x900", "--output-dir", ".testflow/mcp"]
    }
  }
}
```

### Codex CLI

`~/.codex/config.toml`:

```toml
[mcp_servers.playwright]
command = "npx"
args = ["@playwright/mcp@0.0.83", "--headless", "--isolated", "--viewport-size", "1440x900", "--output-dir", ".testflow/mcp"]
```

### Grok Build · Devin CLI

각 도구의 MCP 설정 방법을 따른다. 서버 명령과 인자는 위와 같다. (이 두 도구의 설정 파일 형식은 testflow 에서 확인하지 않았다.)

### Docker 로 띄우기 (호스트와 분리)

Docker 버전은 headless chromium 만 지원한다.

```bash
# stdio — MCP 클라이언트가 직접 띄운다
docker run -i --rm --init --pull=always mcr.microsoft.com/playwright/mcp

# HTTP — 오래 띄워 두고 여러 클라이언트가 붙는다
docker run -d -i --rm --init --pull=always --entrypoint node --name playwright \
  -p 127.0.0.1:8931:8931 mcr.microsoft.com/playwright/mcp \
  /app/cli.js --headless --browser chromium --no-sandbox --port 8931 --host 0.0.0.0
claude mcp add --transport http playwright http://localhost:8931/mcp
```

컨테이너 안의 `localhost` 는 컨테이너 자신이다. 호스트 dev 서버에 붙는 방법은 `troubleshooting.md` 의 `host.docker.internal` 항목을 본다. 포트는 `127.0.0.1` 에만 연다.

### 쓰는 순서

`browser_navigate` → `browser_snapshot` → `browser_click`·`browser_type`·`browser_fill_form` 등 → (눈으로 봐야 할 때만) `browser_take_screenshot` → `browser_close`.

### 적용한 뒤

- 이미 떠 있는 세션에는 새 MCP 도구가 바로 붙지 않는다. 새 세션을 연다.
- `bash <plugin>/scripts/check_env.sh` 의 `MCP_PLAYWRIGHT` 가 `headless` 인지 본다.

## 2. 탐색 스크립트 템플릿 (MCP 가 없을 때)

프로젝트에 `@playwright/test` 나 `playwright` 가 설치돼 있어야 한다. 프로젝트 루트에서 `node .testflow/tmp/explore.mjs <url>` 로 실행한다.

```js
// .testflow/tmp/explore.mjs
import { chromium } from '@playwright/test'; // 프로젝트에 playwright 만 있으면 'playwright'

const url = process.argv[2];
const browser = await chromium.launch(); // 기본이 헤드리스. headless: false 를 넣지 않는다
const context = await browser.newContext({
  viewport: { width: 1440, height: 900 },
  locale: 'ko-KR',
  timezoneId: 'Asia/Seoul',
  // storageState: '.testflow/auth.json', // 테스트 계정 로그인 상태
});
const page = await context.newPage();
await page.goto(url);
await page.getByRole('main').waitFor();

// 상호작용 예
// await page.getByLabel('이메일').fill('qa@example.com');
// await page.getByRole('button', { name: '로그인' }).click();

console.log(await page.locator('body').ariaSnapshot()); // 구조 확인
await page.evaluate(async () => { await document.fonts.ready; });
await page.getByRole('main').screenshot({ path: '.testflow/screenshots/explore-main.png' });
await browser.close();
```

- 단계마다 `ariaSnapshot()` 을 찍어 상태를 확인하고, 스크린샷은 필요한 요소만 찍는다.
- 다 쓰면 스크립트를 지운다.

## 3. `playwright.config` 권장값 (프로젝트 테스트 코드)

탐색으로 확인한 흐름은 테스트 코드로 남기는 게 좋다.

```ts
import { defineConfig } from '@playwright/test';

export default defineConfig({
  use: {
    // headless 는 기본값 true. 적지 않아도 된다
    viewport: { width: 1440, height: 900 },
    locale: 'ko-KR',
    timezoneId: 'Asia/Seoul',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

- 브라우저 채널: 기본(`chromium-headless-shell`)으로 충분하다. 실제 Chrome 과 같은 코드로 그리려면 `channel: 'chromium'`(new headless, 풀 Chromium 설치 필요). `channel: 'chrome'` 은 Docker linux/arm64 에서 설치되지 않는다 (`troubleshooting.md`).
- `deviceScaleFactor: 2` 는 Retina 와 같은 선명도가 필요할 때만. 에이전트가 읽는 이미지는 1 이 가볍다.
