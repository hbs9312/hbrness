# 다른 방식 — 안내용

testflow 는 지금 **웹 헤드리스 확인**과 **Docker visual regression** 만 실행 절차로 갖고 있다. 아래 방식은 사용자에게 선택지와 비용을 안내할 때만 쓴다. 실행 절차를 지어내지 말고, 필요하면 사용자와 범위를 정한 뒤 공식 문서를 따른다.

원칙: 구조화된 인터페이스(DOM, 접근성 트리, adb, simctl)가 있으면 픽셀 기반 computer use 보다 그쪽이 빠르고 안정적이다. 격리(보안)와 화면 점유는 다른 문제라 둘 다 필요한지 먼저 정한다.

## Docker + Xvfb (가상 화면 위 headed 브라우저·Linux GUI 앱)

- 언제: 브라우저 주소창, 파일 선택 창, 권한 팝업, 확장 프로그램 UI 처럼 헤드리스로 안 찍히는 것의 **생김새**를 봐야 할 때. Linux 데스크톱 앱.
- 웹앱의 다이얼로그 **동작**은 헤드리스에서도 Playwright 이벤트(`filechooser`, `dialog`, `context.grantPermissions`)로 확인된다. 그래서 웹이면 필요한 경우가 드물다.
- 구조: 컨테이너 안 Xvfb 가상 화면 + 윈도우 매니저 + 대상 앱. 에이전트는 `docker exec` 로 `scrot`(캡처)·`xdotool`(입력)을 부른다. 사람은 noVNC 로 들여다본다 (포트는 `127.0.0.1` 에만, 비밀번호 설정).
- Electron 앱은 먼저 Playwright `_electron`(CDP)을 시도한다. Xvfb 는 Linux 빌드를 띄우는 것이라 macOS 메뉴바·네이티브 모듈 문제는 못 잡는다.
- 참고: Anthropic `computer-use-demo`(github.com/anthropics/anthropic-quickstarts)는 같은 구성이지만 컨테이너 안에서 자체 에이전트 루프를 돌리는 데모다. 코딩 에이전트가 그 화면을 쓰는 방법은 아니다.

## macOS 네이티브 앱

- **macOS VM (격리 O)**: Lume(trycua/cua), UTM, Tart. Apple Virtualization.framework 기반. Apple 라이선스상 호스트 1대당 macOS VM 동시 2개까지. 디스크 이미지가 수십 GB 라 골든 이미지를 클론해서 쓴다. GPU·Apple ID·App Store 기능이 제한될 수 있다.
- **백그라운드 드라이버 (격리 X)**: 접근성(AX) API 로 앱을 앞으로 가져오지 않고 조작한다. 손쉬운 사용·화면 기록 권한이 필요하다. 화면 점유만 피할 뿐 호스트에 그대로 접근하므로 신뢰할 수 있는 작업에만 쓴다.
- 문서: cua.ai/docs

## Windows 앱

Windows VM 또는 Windows Sandbox (Windows 호스트 필요). macOS 호스트면 ARM Windows VM.

## 클라우드 데스크톱 샌드박스

- E2B Desktop (Ubuntu + XFCE, VNC 스트림, SDK), Cua Cloud, 원격 브라우저 서비스(Browserbase, Steel 등).
- 언제: 병렬 실행, 로컬 리소스 절약, 신뢰할 수 없는 작업.
- 주의: 클라우드 샌드박스는 로컬 dev 서버를 볼 수 없다. 터널(cloudflared, ngrok)로 dev 서버를 외부에 열어야 하므로 노출 범위와 인증을 먼저 정한다.
- 문서: e2b.dev/docs/use-cases/computer-use

## 모바일

- **Android**: `emulator -avd <AVD> -no-window -no-audio -no-boot-anim -gpu swiftshader_indirect` 로 창 없이 띄우고 `adb exec-out screencap -p`, `uiautomator dump` 로 확인한다. Apple Silicon 은 arm64 시스템 이미지. `adb shell input text` 는 한글을 넣지 못하고 공백은 `%s` 로 바꿔야 한다 (한글은 ADBKeyboard 같은 IME 필요).
- **iOS (macOS 호스트)**: Simulator.app 을 열지 않고 `xcrun simctl boot` → `install` → `launch` → `io booted screenshot`. 시뮬레이터 런타임을 먼저 받아야 한다. 탭·스와이프는 simctl 로 안 되고 XCUITest, idb, Appium 같은 도구가 더 필요하다.

## 보안 공통

- 컨테이너·VM 에 호스트 홈 디렉토리를 마운트하지 않는다. 필요한 볼륨만.
- 실 계정 비밀번호·실 API 키를 넣지 않는다. 테스트 계정·테스트 키.
- 외부 임의 사이트 접속은 프롬프트 인젝션 경로가 된다. 접속 대상을 좁힌다.
- 결제·삭제·외부 전송처럼 되돌릴 수 없는 동작은 사람이 확인한다.
- 세션마다 새 컨테이너·VM(또는 스냅샷 복원)으로 시작한다.
