---
name: scan-codebase
description: 기존 프로젝트의 컴포넌트, 훅, 유틸리티를 스캔하여 레지스트리를 생성합니다. "코드베이스 스캔", "기존 컴포넌트 파악" 요청 시 사용.
argument-hint: (인자 없음 — frontend.md의 경로를 자동 참조)
tools: [file:read, search:grep, search:glob, file:write, shell(npm *), shell(npx *), shell(cat *)]
effort: medium
model: sonnet
---

# 코드베이스 스캔 (FU1)

기존 프로젝트에서 재사용 가능한 컴포넌트, 훅, 유틸리티를 파악합니다.
F2에서 "이미 있는 것을 새로 만들지 않도록" 방지하는 핵심 스킬입니다.

## 컨텍스트 로드

- **프로젝트 설정**: [frontend.md](../../context/frontend.md)

## 스캔 대상

frontend.md에서 경로를 읽어 스캔:

1. **프로젝트 컴포넌트** (`component_dir`)
   - 모든 .tsx/.vue/.svelte 파일
   - export된 컴포넌트 이름
   - Props/interface 타입
   - 의존 관계 (import 분석)

2. **디자인 시스템 패키지** (`design_system_package`)
   - `npm ls --json`으로 패키지 존재 확인
   - 패키지의 package.json에서 exports 필드 읽기
   - 타입 정의 파일(.d.ts)에서 export된 컴포넌트명 + Props 추출
   - Glob/Read만으로 node_modules 탐색은 느리므로 Bash 활용

3. **커스텀 훅** (`hook_dir`)
   - use* 패턴의 함수
   - 반환 타입

4. **공유 유틸리티** (`util_dir`)
   - export된 함수 목록

## 출력

```yaml
# component-registry.md

existing_components:
  from_design_system:
    - name: "Button"
      package: "@company/ui-kit"
      props: ["variant", "size", "disabled", "onClick", "children"]
      variants: ["primary", "secondary", "ghost", "danger"]

    - name: "Input"
      package: "@company/ui-kit"
      props: ["label", "error", "placeholder", "value", "onChange"]

  from_project:
    - name: "Card"
      path: "src/components/common/Card"
      props: ["children", "className"]
      used_by: ["Dashboard", "Settings"]

    - name: "Modal"
      path: "src/components/common/Modal"
      props: ["isOpen", "onClose", "title", "children"]

existing_hooks:
  - name: "useAuth"
    path: "src/hooks/useAuth"
    returns: "{ user, isLoading, login, logout }"

  - name: "useToast"
    path: "src/hooks/useToast"
    returns: "{ toast, dismiss }"

existing_utils:
  - name: "formatDate"
    path: "src/lib/format"
  - name: "cn"
    path: "src/lib/utils"
    description: "clsx + tailwind-merge"

scan_summary:
  components: {N}
  hooks: {N}
  utils: {N}
  scanned_at: "{timestamp}"
```

## 저장: component-registry.md (프로젝트 루트 또는 .frontflow/)

## 갱신 시점
- frontflow 워크플로우 시작 전 1회
- 새 컴포넌트 추가 후 (Phase 2/3 완료 후)
