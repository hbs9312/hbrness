# 문제 해결

## 캡처·브라우저

| 증상 | 원인 | 해결 |
|---|---|---|
| `NEED_BROWSER_INSTALL=1` | Playwright 브라우저를 아직 안 받았다 | 출력된 `INSTALL_CMD` 실행. 사용자에게 용량을 알리고 승인받는다 |
| `--device "iPhone ..."` 에서 webkit 설치를 요구 | iPhone·iPad 기기의 기본 브라우저가 webkit 이다 | webkit 을 받거나 chromium 기기(`Pixel 7` 등)로 찍는다 |
| `URL_UNREACHABLE=1` | dev 서버가 꺼져 있거나 포트가 다르다 | 서버를 띄우고 포트를 확인한다 |
| 한글이 □ 로 나온다 | 한글 폰트가 없는 Linux 환경 | `fonts-noto-cjk` 설치 후 `fc-cache -f`. vr.sh 이미지에는 들어 있다 |
| 모바일 캡처가 980px 폭으로 작게 나온다 | 페이지에 `<meta name="viewport">` 가 없다 | 실제 폰도 같다. 페이지를 고친다 |
| 스크린샷이 매번 조금씩 다르다 | 애니메이션, 폰트 로딩, 동적 데이터 | `fidelity.md` 체크리스트 |

## Playwright MCP

| 증상 | 원인 | 해결 |
|---|---|---|
| 사용자 화면에 브라우저 창이 뜬다 | `--headless` 가 없다 (MCP 기본은 headed) | 설정에 `--headless` 를 더한다. `check_env.sh` 로 확인 |
| 설정한 플래그가 무시된다 | `claude mcp add` 에서 `--` 를 빠뜨렸다 | 서버 인자는 `--` 뒤에 쓴다 |
| 설정했는데 `browser_*` 도구가 안 보인다 | 실행 중인 세션은 새 MCP 서버를 읽지 않는다 | 새 세션을 연다. 설정 범위(project/local/user)도 확인 |
| `Browser "chrome-for-testing" is not installed` | `--browser chromium` 인데 브라우저를 안 받았다 | `npx @playwright/mcp@<버전> install-browser chrome-for-testing` |
| 브라우저가 이미 쓰이고 있다는 에러 | persistent 프로필을 두 세션이 같이 쓴다 | `--isolated` |
| 로그인 상태가 매번 풀린다 | `--isolated` 의 의도된 동작 | `--storage-state <file>` 로 테스트 계정 상태를 넣는다 |

## Docker · visual regression

| 증상 | 원인 | 해결 |
|---|---|---|
| `DOCKER=not-running` | Docker 데몬이 꺼져 있다 | Docker Desktop 을 켠다 |
| `A snapshot doesn't exist at ...-darwin.png` | 호스트 macOS 에서 테스트를 돌렸다 | `vr.sh test` 로 돌린다 (`visual-regression.md`) |
| 로컬은 통과, CI 는 픽셀 차이 | CI 가 다른 이미지이거나 아키텍처(amd64)가 다르다 | CI 도 같은 Dockerfile 로. 기준은 `--platform linux/amd64` 로 만들거나 CI 에서만 갱신 |
| `npx playwright install chrome` 이 `not supported on Linux Arm64` | Apple Silicon 의 linux/arm64 컨테이너에는 Google Chrome 설치가 막혀 있다 | `channel: 'chromium'` 을 쓴다 |
| esbuild·swc 가 다른 플랫폼용이라는 에러 | 호스트 macOS 의 `node_modules` 를 컨테이너가 그대로 썼다 | vr.sh 는 볼륨으로 가린다. 직접 `docker run` 할 때도 `node_modules` 를 별도 볼륨으로 가린다 |
| Chromium 이 컨테이너에서 죽는다 | `/dev/shm` 부족 | `--ipc=host` 또는 `--shm-size=1g` (vr.sh 는 `--ipc=host`) |
| 이미지 빌드 실패 | 그 Playwright 버전의 공식 이미지 태그가 없다 | `--pw-version` 으로 있는 버전을 주거나 프로젝트 Playwright 를 올린다 |
| `Executable doesn't exist` (컨테이너 안) | 호스트 `node_modules` 의 Playwright 버전과 lockfile 버전이 다르다 | 호스트에서 의존성을 다시 설치하고 `vr.sh test --rebuild` |
| Linux 호스트에서 root 소유 파일이 남는다 | 컨테이너가 root 로 돈다 | vr.sh 가 새로 만든 파일은 돌려놓는다. 남은 파일은 `sudo chown` |

## 컨테이너에서 호스트 dev 서버에 붙을 때

컨테이너 안의 `localhost` 는 컨테이너 자신이다. 가능하면 `playwright.config` 의 `webServer` 로 서버를 컨테이너 안에서 띄운다. 호스트 서버에 꼭 붙어야 하면:

- 주소: `http://host.docker.internal:<port>`. macOS Docker Desktop 은 기본으로 되고, Linux 는 `--add-host=host.docker.internal:host-gateway` 가 필요하다 (vr.sh 는 넣는다).
- Linux 에서는 dev 서버가 `127.0.0.1` 에만 떠 있으면 닿지 않는다. `0.0.0.0` 으로 띄운다.
- **Vite** 는 `server.allowedHosts` 에 없는 Host 헤더를 막는다 (5.4.12 / 6.0.9 이후). `allowedHosts: ['host.docker.internal']` 를 더한다.
- **Next.js** 는 다른 origin 에서 오는 dev 리소스 요청을 `allowedDevOrigins` 로 검사한다. `allowedDevOrigins: ['host.docker.internal']` 를 더한다.
- 환경 변수로 baseURL 을 넘길 때: `vr.sh test --env BASE_URL=http://host.docker.internal:3000`.
