---
name: extract-figma
description: Figma MCP에서 컴포넌트/화면의 레이아웃·스타일 데이터를 추출·정제합니다. "Figma 추출", "디자인 데이터" 요청 시 사용.
argument-hint: [Figma 파일 URL 또는 노드 ID] [추출 범위: component | page]
disable-model-invocation: true
tools: [file:read, file:write, search:grep, search:glob, shell(npx figma*)]
effort: high
model: sonnet
---

# Figma 데이터 추출 (FU2)

Figma MCP를 통해 디자인 데이터를 가져오고,
에이전트가 사용할 수 있도록 정제합니다.

## ★ Figma MCP 연결 확인 ★

이 스킬은 Figma MCP 서버 연결 시 최대 효과를 발휘합니다.

실행 시 아래 순서로 확인:

1. Figma MCP 도구가 사용 가능한지 확인
2. 사용 가능하면 → MCP를 통해 Figma 노드 데이터 요청
3. 사용 불가능하면 → 사용자에게 아래 안내:

"Figma MCP가 연결되어 있지 않습니다.
 두 가지 방법이 있습니다:
 
 방법 1: Figma MCP 연결 (권장)
   환경 변수 설정: FIGMA_ACCESS_TOKEN
   발급: figma.com > Settings > Personal access tokens
 
 방법 2: 수동 추출
   1. Figma에서 해당 컴포넌트/프레임 선택
   2. Dev Mode 탭 열기
   3. 우측 패널의 CSS/속성 정보 복사
   4. 이 대화에 붙여넣기"

## 입력

$ARGUMENTS 에서:
1. Figma URL 또는 노드 ID
2. 추출 범위: `component` (단일 컴포넌트) | `page` (전체 페이지)

## ★ 컨텍스트 크기 관리 ★

Figma 원본 데이터는 매우 큽니다.
반드시 추출 범위를 한정하고 불필요한 데이터를 제거합니다.

- F2(원자)에서는 원자 컴포넌트 노드만
- F3(복합)에서는 복합 컴포넌트 노드만
- F4(페이지)에서는 페이지 레벨 프레임만

## 추출 항목

### 레이아웃 속성 (핵심)
```yaml
- layoutMode: HORIZONTAL | VERTICAL     → flex-direction
- itemSpacing: {N}                       → gap
- paddingTop/Right/Bottom/Left: {N}      → padding
- primaryAxisAlignItems: MIN|CENTER|MAX  → justify-content
- counterAxisAlignItems: MIN|CENTER|MAX  → align-items
- layoutSizingHorizontal: FIXED|FILL|HUG → width
- layoutSizingVertical: FIXED|FILL|HUG   → height
```

### 스타일 속성
```yaml
- fills: [{type, color: {r,g,b,a}}]     → background / color
- effects: [{type, radius, offset}]      → box-shadow
- cornerRadius: {N}                      → border-radius
- strokes: [{color, weight}]             → border
- opacity: {N}                           → opacity
```

### 텍스트 속성
```yaml
- fontFamily: ""
- fontSize: {N}
- fontWeight: {N}
- lineHeight: {value, unit}
- letterSpacing: {value, unit}
- textAlignHorizontal: LEFT|CENTER|RIGHT
```

### 제거 항목 (노이즈)
- 노드 id, plugin 데이터
- 내부 메타데이터
- 숨겨진(visible=false) 요소
- 편집 히스토리

## 출력

```yaml
# 정제된 Figma 데이터
figma_data:
  node_name: "SpeakerCard"
  type: "FRAME"
  layout:
    direction: "horizontal"
    gap: 12
    padding: { top: 16, right: 16, bottom: 16, left: 16 }
    align: { main: "start", cross: "center" }
    sizing: { width: "fill", height: "hug" }
  style:
    background: { r: 255, g: 255, b: 255, a: 1 }
    corner_radius: 8
    shadow: { x: 0, y: 1, blur: 3, color: "rgba(0,0,0,0.1)" }
  children:
    - name: "StatusIcon"
      type: "FRAME"
      size: { width: 12, height: 12 }
      style:
        background: { token_hint: "green-500" }
        corner_radius: 6
    - name: "TextGroup"
      type: "FRAME"
      layout:
        direction: "vertical"
        gap: 2
      children:
        - name: "SpeakerName"
          type: "TEXT"
          font: { family: "Inter", size: 16, weight: 600 }
        - name: "StatusText"
          type: "TEXT"
          font: { family: "Inter", size: 13, weight: 400 }
          style:
            color: { token_hint: "text-secondary" }
```

## Figma MCP 없이 사용할 때

```markdown
Figma MCP가 연결되어 있지 않습니다.
아래 방법으로 수동 추출할 수 있습니다:

1. Figma에서 해당 컴포넌트/프레임 선택
2. Dev Mode 탭 열기
3. 우측 패널의 CSS/속성 정보 복사
4. 이 대화에 붙여넣기

또는 Figma MCP를 연결해주세요:
/plugin install figma@claude-plugins-official
```
