# 프론트엔드 프로젝트 컨텍스트

모든 frontflow 스킬이 참조하는 프로젝트 설정입니다.
프로젝트 초기화 시 1회 작성하고, 기술 스택 변경 시 갱신하세요.

## 프레임워크

```yaml
framework:
  name: ""               # Next.js | React | Vue | Svelte
  version: ""            # 예: 14.x
  app_router: true       # Next.js 전용
```

## 스타일링

```yaml
styling:
  method: ""             # tailwind | css-modules | styled-components | vanilla
  design_system_package: ""   # 예: @company/ui-kit (있으면)
  tailwind_config_path: ""    # 예: tailwind.config.ts
  global_css_path: ""         # 예: src/app/globals.css
```

## 디렉토리 구조

```yaml
structure:
  component_dir: ""      # 예: src/components
  page_dir: ""           # 예: src/app
  hook_dir: ""           # 예: src/hooks
  util_dir: ""           # 예: src/lib
  type_dir: ""           # 예: src/types
  naming: "PascalCase"   # 컴포넌트 파일명 컨벤션
  barrel_exports: true   # index.ts re-export 여부
  co_location: true      # 컴포넌트 + 스타일 + 테스트 같은 폴더
```

## 컴포넌트 패턴

```yaml
component_pattern: |
  // 에이전트가 생성하는 컴포넌트의 기본 구조
  // 프로젝트에 맞게 수정하세요
  import { type FC } from 'react'

  interface {ComponentName}Props {
    // props
  }

  export const {ComponentName}: FC<{ComponentName}Props> = ({ ...props }) => {
    return (...)
  }
```

## 상태 관리

```yaml
state_management:
  client_state: ""       # useState | zustand | jotai | redux
  server_state: ""       # tanstack-query | swr | rtk-query
  form: ""               # react-hook-form | formik | none
```

## 테스트

```yaml
testing:
  runner: ""             # vitest | jest
  component_test: ""     # testing-library | enzyme
  storybook: true
  storybook_dir: ""      # 예: src/stories 또는 co-located
  snapshot: false
```

## API 클라이언트

```yaml
api_client:
  method: ""             # fetch | axios | ky
  base_url_env: ""       # 예: NEXT_PUBLIC_API_URL
  auth_header: ""        # 예: Authorization: Bearer {token}
```

## 에러 핸들링

```yaml
error_handling:
  codes_file: ""         # 예: src/errors/codes.ts — impl-error-handling 출력 (backend 와 code 값 동기)
  handler_file: ""       # 예: src/errors/handler.ts — code → {message, uiFlow, retriable} 순수 함수
  ui_flow_file: ""       # 예: src/errors/ui-flow.tsx — React 프리셋 (선택)
  i18n_library: ""       # i18next | formatjs | lingui | inline — inline 시 message 를 codes.ts 에 내장
  i18n_output_dir: ""    # 예: src/locales — errors.{lang}.json (i18n_library != inline 시)
  languages: ["ko", "en"] # 생성 언어 (TS §에러 코드 맵 컬럼과 1:1)
  default_ui_flow:       # ui_flow 컬럼이 TS 에 없을 때 http_status 기반 fallback
    "4xx": toast
    "5xx": modal
```
