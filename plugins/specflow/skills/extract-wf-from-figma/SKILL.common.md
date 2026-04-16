---
name: extract-wf-from-figma
description: Figma 디자인에서 구조를 역추출하여 와이어프레임을 생성합니다. "Figma에서 WF 추출", "디자인 퍼스트 WF" 요청 시 사용.
argument-hint: [기능 명세서 경로] [Figma URL 또는 노드 ID]
tools: [file:read, search:grep, search:glob, file:write]
effort: max
---

# Figma → 와이어프레임 역추출 (G2-R)

Figma 디자인이 WF보다 먼저 존재할 때, 디자인에서 **구조만** 역추출하여
표준 WF 문서를 생성합니다. 이후 파이프라인(extract-ui, validate-cross)과
완전히 호환되는 WF를 출력합니다.

## 공통 컨텍스트 로드

- **문서 컨벤션**: [conventions.md](../../context/conventions.md)
- **도메인 용어집**: [glossary.md](../../context/glossary.md)

## 입력

$ARGUMENTS 에서:
1. 기능 명세서(FS) 파일 경로 — Read로 읽기. `Approved` 상태 확인
2. Figma URL 또는 노드 ID — Figma MCP로 디자인 데이터 취득

## Figma MCP 연결 확인

실행 시 아래 순서로 확인:

1. Figma MCP 도구(`get_design_context`, `get_metadata`, `get_screenshot`)가 사용 가능한지 확인
2. 사용 가능하면 → MCP를 통해 디자인 데이터 요청
3. 사용 불가능하면 → 사용자에게 Figma MCP 연결 또는 수동 입력 안내

## 핵심 원칙: "추출하되 시각을 제거한다"

generate-wf(G2)와 동일한 원칙:
### 허용: 레이아웃, 요소 위치, 정보 계층, 상태 전환, 버튼 활성/비활성 조건
### 금지: 색상, 폰트, 애니메이션 수치, 디자인 토큰

Figma에서 가져온 시각 속성(색상, 타이포, 그림자 등)은 WF에 포함하지 않습니다.
이 속성들은 이후 extract-ui(G4) 단계에서 정규화됩니다.

## 역추출 전략

### Phase A: Figma 구조 추출

1. Figma MCP `get_metadata`로 노드 트리 탐색
2. 각 프레임/컴포넌트의 **레이아웃 속성만** 추출:
   - `layoutMode` → 배치 방향 (가로/세로)
   - `itemSpacing` → 요소 간격 (px 수치가 아닌 "간격 있음/없음/밀착" 수준으로 추상화)
   - `paddingTop/Right/Bottom/Left` → 여백 존재 여부
   - `layoutSizingHorizontal/Vertical` → 고정/채움/자동
3. 컴포넌트 인스턴스의 **variant 이름**에서 상태 후보 추출
   - 예: `prop1="Read" | "Edit"` → 상태 2개
4. 프레임 계층 구조를 **부모-자식 트리**로 정리

### Phase B: FS 비즈니스 규칙 매핑

1. FS의 BR(비즈니스 룰)을 Figma UI 요소에 매핑
   - BR이 표현되는 UI 요소 식별 (버튼, 입력 필드, 조건부 영역 등)
   - 매핑되지 않는 BR → warning으로 기록
2. FS의 AC(수용 기준)에서 에러/예외 상태 추출
   - Figma에 에러 상태 variant가 있으면 매핑
   - 없으면 상태 매트릭스에 "Figma 미정의" 표기
3. FS의 화면 전환 흐름을 Figma 프레임 간 관계로 검증

### Phase C: 와이어프레임 조립

1. Figma 프레임 → ASCII 박스 변환
   - 레이아웃 방향에 따라 요소를 가로/세로로 배치
   - 중첩 프레임은 들여쓰기로 표현
   - 텍스트 노드는 `{역할명}` 형태로 추상화
   - 아이콘/이미지는 `[아이콘]` `[이미지]` 로 표기
2. 각 와이어프레임 아래에 필수 정보 부착:
   - **요소 설명**: Figma 레이어명 → 역할 설명
   - **인터랙션 노트**: variant 전환 조건, 버튼 활성/비활성
   - **BR 매핑**: Phase B에서 식별한 매핑
   - **Figma 출처**: 노드명 기록 (추적성)
3. 화면 전환 맵 작성 (정방향 + 역방향)
4. 상태별 화면 변화 매트릭스 작성

## Figma 노드 → WF 요소 변환 규칙

| Figma 노드 타입 | WF 표현 |
|-----------------|---------|
| FRAME (layoutMode=VERTICAL) | 세로 박스 `│ ... │` |
| FRAME (layoutMode=HORIZONTAL) | 가로 배치 `[ A ] [ B ]` |
| TEXT | `{텍스트 역할}` |
| INSTANCE (버튼) | `[ {버튼명} ]` |
| INSTANCE (아이콘) | `[x]` 또는 `[아이콘명]` |
| INSTANCE (입력) | `[_________{힌트}]` |
| RECTANGLE/IMAGE | `[이미지]` |
| 숨겨진 노드 (visible=false) | 제외 |

## 품질 자가 점검

- [ ] FS UI/UX 화면 수 = WF 화면 수
- [ ] 상태 매트릭스 빈 셀 = 0 (Figma 미정의는 명시적 표기)
- [ ] 모든 화면에 뒤로가기/이탈 경로 정의됨
- [ ] **디자인 요소 포함 = 0건** (색상, 폰트, px 수치, 토큰명 없음)
- [ ] 모든 BR의 UI 매핑 존재 (미매핑 BR은 warning 기록)
- [ ] Figma 출처 노드명이 각 요소에 기록됨

## 출력 위치: specs/WF-{YYYY}-{NNN}.md

출력 형식은 generate-wf(G2) 템플릿과 **동일**합니다.
메타데이터에 `생성 방식: design-first (Figma 역추출)` 을 추가합니다.
