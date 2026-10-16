# 헤드리스 스크린샷 충실도 — 실제 화면과 같은가

렌더링 엔진은 headed 와 같다. 차이는 주로 **환경**(폰트, 배율, GPU, OS 위젯)에서 생긴다.

## Chromium 헤드리스는 두 종류다

| | `chromium-headless-shell` | new headless |
|---|---|---|
| 정체 | 예전 headless 구현을 떼어 낸 별도 바이너리 (Chrome 132 에서 Chrome 본체에서 빠짐) | 일반 Chrome 과 같은 코드, 창만 없음 |
| Playwright 에서 | 헤드리스 chromium 의 기본값 (1.49 부터) | `channel: 'chromium'` 또는 `'chrome'` |
| 충실도 | 미세한 차이가 날 수 있다 | headed 와 거의 같다 |

- testflow 의 `capture.sh` 는 기본값(headless shell)을 쓴다. 받는 용량이 작고 레이아웃 확인에는 충분하다.
- Playwright MCP 는 기본으로 설치된 Chrome 을 new headless 로 쓴다.
- Docker linux/arm64 에서는 `channel: 'chrome'` 을 쓸 수 없으니 `'chromium'` 을 쓴다.

## 결과가 달라지는 지점

| 항목 | 증상 | 대응 |
|---|---|---|
| 폰트 | 컨테이너에 한글 폰트가 없으면 □ 나 다른 글꼴 | CJK·이모지 폰트 설치 (vr.sh 이미지에는 들어 있다), 웹폰트 로딩 대기 |
| 시스템 폰트 이름 | `system-ui`·`sans-serif` 가 OS 마다 다른 폰트로 풀려 글꼴·굵기가 달라진다 | 웹폰트를 쓰거나, 비교는 같은 이미지에서만 |
| OS 폰트 렌더링 | macOS 와 Linux 의 안티앨리어싱 차이로 픽셀 diff | 기준 생성과 비교를 같은 Docker 이미지에서 |
| 배율 | 기본 `deviceScaleFactor` 1 → Retina 보다 흐림 | 선명도가 필요할 때만 2 |
| 뷰포트 | Playwright 기본 1280x720 → 반응형 breakpoint 차이 | 명시 (testflow 기본 1440x900) |
| 모바일 viewport meta | `<meta name="viewport">` 가 없으면 모바일 에뮬레이션에서 980px 폭으로 그려진다 | 실제 폰도 같다. 페이지에 meta 를 넣는다 |
| GPU | 소프트웨어 렌더링이라 WebGL·blur·backdrop-filter 가 다를 수 있다 | 해당 영역 mask |
| OS 위젯 | 스크롤바, `<select>`, date picker 모양 | 커스텀 컴포넌트를 쓰거나 mask |
| 캡처 범위 | 주소창·네이티브 다이얼로그·권한 팝업은 안 찍힌다 | 동작은 Playwright 이벤트로 확인. 생김새가 필요하면 `other-methods.md` 의 Xvfb |
| User-Agent | `HeadlessChrome` 이 들어가 외부 서비스가 다른 화면을 줄 수 있다 | 자사 서비스면 상관없다. 필요하면 UA 지정 |
| 코덱 | 오픈소스 Chromium 에 H.264·AAC 가 없다 | `channel: 'chrome'` (호스트에서) |
| 애니메이션·타이밍 | 캡처 시점마다 다른 프레임 | `animations: 'disabled'`, 특정 상태를 기다린 뒤 캡처 |
| 시간·로케일 | 날짜 표기·시간대 차이 | `locale`, `timezoneId`, 필요하면 `page.clock` |

## 캡처 체크리스트

- [ ] 뷰포트를 명시했다
- [ ] `locale: 'ko-KR'`, `timezoneId: 'Asia/Seoul'`
- [ ] 컨테이너면 CJK·이모지 폰트가 있다
- [ ] 캡처 전에 특정 요소와 `document.fonts.ready` 를 기다렸다
- [ ] 애니메이션을 껐다
- [ ] 시간·광고·아바타·랜덤 데이터를 mask 하거나 고정했다
- [ ] 기준 이미지 생성과 비교를 같은 Docker 이미지에서 했다
- [ ] 실패 시 trace·스크린샷을 남긴다

## 캡처 코드

```ts
await page.goto(url);
await page.getByRole('main').waitFor();
await page.evaluate(async () => { await document.fonts.ready; });
await page.screenshot({
  path: '.testflow/screenshots/home.png',
  fullPage: true,
  animations: 'disabled',
  mask: [page.getByTestId('clock')],
});
```

`page.evaluate(() => document.fonts.ready)` 처럼 FontFaceSet 을 그대로 돌려주면 직렬화할 수 없는 값을 반환하게 된다. 위처럼 함수 안에서 await 한다.
