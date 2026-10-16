# Visual regression — Docker 로 기준 이미지 만들고 비교하기

## 왜 Docker 인가

같은 페이지라도 macOS 와 Linux 는 폰트 안티앨리어싱·힌팅·시스템 폰트가 달라서 픽셀이 다르게 나온다. 그래서 기준 이미지를 만드는 곳과 비교하는 곳이 같은 환경이어야 diff 가 의미 있다. `vr.sh` 는 둘 다 같은 컨테이너 이미지에서 돌린다.

Playwright 는 스냅샷 파일 이름에 플랫폼을 붙인다(`home-linux.png`, `home-darwin.png`). 호스트 macOS 에서 `npx playwright test` 를 그냥 돌리면 `*-darwin.png` 를 찾으므로, Docker 에서 만든 `*-linux.png` 기준과 비교되지 않는다. 기준 이미지는 항상 `vr.sh` 로 만들고 비교한다.

## vr.sh 가 하는 일

1. 프로젝트에 설치된 `@playwright/test` 버전을 읽는다 (`--pw-version` 으로 지정 가능).
2. 이미지 `testflow-pw:<버전>-<arch>` 가 없으면 플러그인의 `assets/Dockerfile.vr` 로 빌드한다.
   - 베이스: `mcr.microsoft.com/playwright:v<버전>-noble` (없으면 `-jammy`). 그 버전에 맞는 브라우저가 들어 있다.
   - 추가: `fonts-noto-cjk`, `fonts-noto-color-emoji`. 빌드할 때 한 번만 넣어서 실행마다 폰트 버전이 바뀌지 않게 한다.
3. 저장소 루트를 `/work` 에 마운트하고, `/work/node_modules` 는 named volume(`testflow-nm-<경로 해시>-<arch>`)으로 가린다. 호스트 macOS 의 `node_modules` 에 든 esbuild·swc 같은 네이티브 바이너리는 Linux 에서 돌지 않기 때문이다.
4. lockfile 해시가 바뀌었을 때만 컨테이너 안에서 의존성을 새로 설치한다 (`npm ci`, `pnpm install --frozen-lockfile`, `yarn install --frozen-lockfile|--immutable`).
5. `npx playwright test` (update 면 `--update-snapshots`) 를 돌린다. 옵션: `--ipc=host`(Chromium 메모리), `--init`, `--add-host=host.docker.internal:host-gateway`.
6. Linux 호스트면 컨테이너가 root 로 만든 파일을 호스트 사용자 소유로 돌려놓는다.
7. 실패하면 `test-results/` 의 `*-diff.png` 경로를 `DIFF=` 로 출력한다.

첫 실행은 Playwright 이미지(약 3.5GB)를 받고 의존성을 설치하느라 몇 분 걸린다. 그다음부터는 테스트 시간만 든다.

## 테스트 작성 요령

```ts
import { test, expect } from '@playwright/test';

test('home', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('main').waitFor();             // 특정 요소를 기다린다 (networkidle 은 과신하지 않는다)
  await page.evaluate(async () => { await document.fonts.ready; });
  await expect(page).toHaveScreenshot('home.png', {
    fullPage: true,
    mask: [page.getByTestId('clock')],                 // 시간·아바타·랜덤 데이터
    maxDiffPixelRatio: 0.01,
  });
});
```

- `toHaveScreenshot` 은 애니메이션을 멈추고 caret 을 숨기는 게 기본값이다.
- 날짜·시간이 화면에 나오면 `page.clock` 으로 고정하거나 mask 한다.
- 서버는 `playwright.config` 의 `webServer` 로 컨테이너 안에서 띄우는 게 가장 간단하다. 컨테이너에서 호스트의 `localhost` 는 보이지 않는다.

## 기준 이미지 다루기

- `*-snapshots/*-linux.png` 를 커밋한다.
- `update` 는 화면 변경이 의도된 것일 때만 돌리고, 범위를 좁힌다: `vr.sh update -- tests/home.spec.ts` 또는 `-- -g "home"`.
- 갱신한 기준 이미지는 커밋 전에 사람이 diff 를 본다.

## CI 와 맞추기

CI 도 같은 이미지에서 돌아야 로컬 기준과 비교된다. 플러그인의 `assets/Dockerfile.vr` 를 프로젝트에 복사해서 CI 에서 빌드한다. GitHub Actions 예:

```yaml
- name: Build VR image
  run: docker build --build-arg PW_VERSION=1.64.1 -t vr -f ci/Dockerfile.vr ci
- name: Visual regression
  run: docker run --rm --ipc=host -v "$PWD":/work -w /work vr bash -c "npm ci && npx playwright test"
```

- **아키텍처**: Apple Silicon 로컬은 `linux/arm64`, GitHub 호스티드 러너는 보통 `linux/amd64` 다. 같은 Linux 라도 아키텍처에 따라 렌더링이 미세하게 다를 수 있다. 기준을 공유하면 로컬에서 `--platform linux/amd64` 로 만든다 (에뮬레이션이라 느리다). 아니면 기준 이미지를 CI 에서만 갱신한다.
- `PW_VERSION` 은 프로젝트의 `@playwright/test` 버전과 같이 올린다.

## 한계

- 모노레포에서 하위 패키지마다 `node_modules` 가 따로 있으면 루트만 가려지므로 아직 지원하지 않는다. `--dir` 은 `playwright.config` 위치만 바꾼다.
- bun 등 npm·pnpm·yarn 외 lockfile 은 지원하지 않는다.
- 브라우저 주소창·네이티브 다이얼로그 생김새는 헤드리스로 안 찍힌다 (`other-methods.md` 의 Xvfb 방식).

## 정리

```bash
bash <plugin>/scripts/vr.sh clean          # 이 프로젝트의 node_modules 볼륨 삭제
docker image rm testflow-pw:<버전>-<arch>   # 이미지까지 지울 때
```
