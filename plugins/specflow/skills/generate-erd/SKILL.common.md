---
name: generate-erd
description: 기술 명세서의 데이터 모델 섹션에서 Mermaid erDiagram 을 생성하고 셀프 호스팅 렌더러로 이미지를 만듭니다. "ERD", "ER 다이어그램", "엔티티 관계도", "mermaid 스키마 그려줘" 요청 시 사용.
argument-hint: [TS 경로] [FS 경로] [--render] [--format svg|png] [--no-project-copy] [--open]
tools: [file:read, search:grep, search:glob, file:write, shell(curl*), shell(mkdir*), shell(date*), shell(python3*)]
effort: medium
model: sonnet
---

# ERD 생성 (G5)

당신은 기술 명세서(TS)의 **데이터 모델**을 Mermaid `erDiagram` 로 번역합니다. 목적은 두 가지입니다:

1. 리뷰어가 텍스트 테이블 대신 한눈에 스키마 관계를 파악하도록
2. 명세 문서에 최신 ERD 이미지를 **자동으로 유지**되도록 (렌더러 URL만 있으면 재실행 시 갱신)

## 공통 컨텍스트 로드

- **문서 컨벤션**: [conventions.md](../../context/conventions.md)
- **도메인 용어집**: [glossary.md](../../context/glossary.md)
- **출력 템플릿**: [template.md](./template.md)

## 입력 파싱

`$ARGUMENTS` 에서 다음을 추출:

- **TS 경로** (필수, 첫 번째 `.md` 경로)
- **FS 경로** (선택, 두 번째 `.md` 경로) — 있으면 관계/제약에 `BR-NNN` 근거 주석을 채움
- **플래그**
  - `--render` : 렌더 서비스에 POST 해서 이미지 저장 (환경변수 `MERMAID_RENDER_URL` 필요)
  - `--format svg` (기본) / `--format png`
  - `--no-project-copy` : 프로젝트 `specs/` 에 복사하지 않고 Tier 1 캐시에만 저장
  - `--open` : 생성 후 live-editor deep link 를 브라우저에서 즉시 열기 (macOS `open` / Linux `xdg-open`). 실패는 silent.

TS 파일 상단 frontmatter 의 `문서 ID` 에서 **TS-ID** 를 뽑으세요 (예: `TS-2026-003`). 못 찾으면 파일명 stem 을 쓰세요.

## 단계

### 1) 데이터 모델 섹션 추출

TS 를 Read 로 읽고 `# 4. 데이터 모델` 이하 `# 5. ` 또는 다음 최상위 헤딩 전까지를 잘라내세요. 섹션이 없으면 **중단하고 사용자에게 "TS 에 데이터 모델 섹션이 없음" 보고**하세요 — 추측으로 ERD 를 만들지 마세요.

### 2) 엔티티 파싱

각 `## {테이블명}` 블록을 엔티티 1개로 매핑:

- 이름: 테이블명을 **UPPER_SNAKE** 로 정규화 (`user_sessions` → `USER_SESSIONS`) — Mermaid 관행
- 속성: 아래 필드 테이블에서 `필드 / 타입 / 제약 / 설명` 행을 전부 속성으로
  - 타입은 Mermaid 가 허용하는 식별자로 정규화: `VARCHAR(255)` → `varchar`, `TIMESTAMP WITH TIME ZONE` → `timestamptz`, 공백·괄호 제거
  - 제약 키워드 매핑: `PK` / `FK` / `UK` (unique) — 그 외 제약(NOT NULL, DEFAULT 등)은 드롭 (Mermaid 어휘에 없음)
  - 필드 설명이 있으면 속성 라인 끝에 `"설명"` 으로 인용

### 3) 관계 판별

각 테이블의 `관계:` 라인 또는 필드 `제약` 의 `FK → {타겟}` 을 보고 엔티티 쌍과 카디널리티를 뽑아내세요.

| 단서 | 카디널리티 | Mermaid |
|---|---|---|
| FK 단일 + 타겟의 PK 가 이 테이블의 PK 이기도 함 | 1 : 1 | `||--||` |
| FK 단일, 일반 FK (nullable 아님) | N : 1 (많은 쪽 → 하나) | `}o--||` |
| FK 가 nullable (제약에 `NULL 허용` 또는 `optional`) | N : 0..1 | `}o--o|` |
| 조인 테이블 (PK 가 두 FK 조합) | 각 FK → N:1 | `}o--||` **두 줄만**. 상위 두 엔티티 간 `}o--o{` 단축관계는 **그리지 않음** (조인 엔티티가 이미 의미 전달) |
| 자기 참조 FK | N : 1 | `}o--||` (라벨에 `self-ref`) |

**결정 우선순위**: (1) 필드의 FK 제약 > (2) `관계:` 라인 서술 > (3) 이름 휴리스틱 (`*_id`). 추측이 필요하면 라인 끝에 `%% inferred` 주석을 붙이세요.

관계 라벨은 한국어 동사구(예: `"속한다"`, `"보유"`) 보다 **영문 소문자 단어 1-2개** (`belongs_to`, `has_many`, `contains`) 가 Mermaid 문법상 안전합니다. 원본 관계 서술은 아래 **Legend** 섹션에 보존하세요.

### 4) Mermaid 소스 조립

[template.md](./template.md) 를 따라 작성. 핵심 규칙:

- 최상단 `erDiagram` 선언
- 관계 라인을 먼저, 엔티티 블록을 그 뒤에 (Mermaid 권장 순서)
- **주석은 반드시 독립 라인** — Mermaid 의 `erDiagram` 파서는 관계/엔티티 라인 **끝의 인라인 `%%` 를 거부**합니다. 그래서 주석은 항상 해당 라인 바로 **앞에** 별도 줄로 씁니다.
  - 예) 먼저 `%% BR-012, BR-013` 을 쓰고 다음 줄에 `USERS ||--o{ ORDERS : places`
- 각 엔티티 블록 바로 위에도 동일하게 `%% source: TS §4.<세부섹션>` 독립 주석
- **관계 라벨**(콜론 뒤)은 영문 단어 1-2개로 (`has`, `places`, `contains`, `appears_in`). 한글이나 공백이 있는 구문은 파서 리스크.
- **속성 설명**의 enum 등에 `|` 를 쓰려면 반드시 따옴표로 감싸세요: `varchar status "PENDING|PAID|CANCELED"` — 따옴표 밖 `|` 는 관계 연산자로 오해됨.

### 5) 저장

저장 경로는 **Tier 1 규약** (`~/.hbrness/` 하위):

```bash
TS_ID="{추출한 TS-ID}"
TS_CACHE_DIR="$HOME/.hbrness/specflow/erd/${TS_ID}"
TS="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$TS_CACHE_DIR"
```

Write 로 `${TS_CACHE_DIR}/${TS}.mmd` 를 씁니다 (mermaid 소스 only, 코드펜스 없음).

### 6) 렌더 (옵션)

`--render` 가 있고 `$MERMAID_RENDER_URL` 이 비어있지 않으면:

```bash
FORMAT="{svg 또는 png}"
OUT="${TS_CACHE_DIR}/${TS}.${FORMAT}"
HTTP_CODE=$(curl -sS -o "$OUT" -w "%{http_code}" \
  -X POST \
  -H "Content-Type: text/plain" \
  --data-binary "@${TS_CACHE_DIR}/${TS}.mmd" \
  "$MERMAID_RENDER_URL")

if [ "$HTTP_CODE" != "200" ]; then
  echo "⚠️  렌더 실패 (HTTP $HTTP_CODE). .mmd 만 저장하고 계속합니다." >&2
  rm -f "$OUT"
fi
```

**실패는 non-fatal**: `.mmd` 는 남기고 이미지 링크 없이 마크다운을 작성하세요. 반드시 HTTP 상태코드를 로그에 남기세요.

URL 호환성 노트: 이 호출 방식은 Kroki (`POST /mermaid/<format>` body=소스) 및 일반 mermaid HTTP 서버 중 body=raw 를 받는 구현과 호환됩니다. 사용자가 **mermaid-ink 스타일(GET + base64)** 을 쓴다면 `MERMAID_RENDER_URL` 끝에 `/render` 가 없는지 확인하라고 안내하세요.

### 7) Live Editor Deep Link 생성

셀프 호스팅 `mermaid-live-editor` 로 바로 이어 편집·팬/줌할 수 있도록 URL 하나 만듭니다. 환경변수 `MERMAID_LIVE_EDITOR_URL` (기본 `http://localhost:9000`) 에 **pako 인코딩된 hash** 를 붙이는 방식입니다.

인코딩 규칙 (live-editor 공식):
- 페이로드 = JSON `{code, mermaid, autoSync, updateDiagram, panZoom}` 직렬화
- zlib deflate (max compression) → base64url → `#pako:{...}` hash

Python 표준 라이브러리만 사용 (macOS/Linux 기본 내장):

```bash
LIVE_EDITOR_URL="${MERMAID_LIVE_EDITOR_URL:-http://localhost:9000}"
DEEP_LINK=$(python3 - "$TS_CACHE_DIR/$TS.mmd" "$LIVE_EDITOR_URL" <<'PY'
import json, zlib, base64, sys
mmd_path, base_url = sys.argv[1], sys.argv[2]
code = open(mmd_path).read()
state = {
    "code": code,
    "mermaid": json.dumps({"theme": "default"}),
    "autoSync": True,
    "updateDiagram": True,
    "panZoom": True,
}
raw = json.dumps(state).encode("utf-8")
b64 = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")
print(f"{base_url}/edit#pako:{b64}")
PY
)
echo "live editor: $DEEP_LINK"
```

`python3` 가 없거나 live-editor URL 호출 실패가 예상되면 이 단계는 **non-fatal**. 변수만 빈 문자열로 두고 계속하세요. 마크다운에는 "Live Editor 미사용" 으로 표시.

`--open` 플래그가 있으면 생성 직후 브라우저 오픈:

```bash
if [ -n "$DEEP_LINK" ]; then
  if command -v open >/dev/null 2>&1; then
    open "$DEEP_LINK"            # macOS
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$DEEP_LINK"        # Linux
  fi
fi
```

### 8) 프로젝트 사본 작성

`--no-project-copy` 없으면 `specs/ERD-{TS-ID}.md` 에 마크다운 파일 하나를 씁니다. [template.md](./template.md) 의 "프로젝트 사본" 섹션 구조대로:

- frontmatter (문서 ID, TS 참조, 생성일)
- 생성 메타데이터 (소스 TS 경로, 엔티티 개수, 관계 개수, 렌더 URL 사용 여부)
- **🔗 Live Editor 링크** (위 7 단계에서 생성된 URL — 클릭 시 브라우저에서 에디터 오픈)
- mermaid 코드블록 (GitHub 에서 자동 렌더됨)
- 렌더 이미지 링크 (`--render` 성공 시 이미지를 `specs/.assets/ERD-{TS-ID}.{svg|png}` 에 복사하고 상대 링크. 홈 디렉토리 경로는 상대경로 해석 불가라 절대 복사)
- Legend: 관계 라벨 ↔ 원본 한국어 서술 매핑

## 품질 자가 점검

- [ ] TS 의 모든 테이블이 엔티티로 나옴 (누락 0)
- [ ] 각 FK 가 관계 1개로 그려짐 (nullable/non-null 구분 반영)
- [ ] PK 마커가 모든 엔티티에 최소 1개
- [ ] Mermaid 예약문자(`.`, `-`, 공백) 가 이름에 없음 (있으면 `_` 치환)
- [ ] FS 가 주어졌을 때 관계 주석의 BR 참조율 ≥ 80%
- [ ] 추측된 관계는 `%% inferred` 로 표시됨
- [ ] 저장 경로가 Tier 1 규약 (`~/.hbrness/...`) — 하네스별 홈 디렉토리 리터럴 미사용

## 출력 위치

- 원본 캐시 (Tier 1): `~/.hbrness/specflow/erd/{TS-ID}/{timestamp}.mmd` (+ 옵션 `.svg`/`.png`)
- 프로젝트 사본: `specs/ERD-{TS-ID}.md`

## 사용 예

```
# 가장 단순한 경우
/specflow:generate-erd specs/TS-2026-003.md

# FS 함께 — 관계 주석에 BR 참조 강화
/specflow:generate-erd specs/TS-2026-003.md specs/FS-2026-003.md

# 렌더까지
MERMAID_RENDER_URL=http://localhost:8000/mermaid/svg \
  /specflow:generate-erd specs/TS-2026-003.md --render

# PNG, 캐시에만
MERMAID_RENDER_URL=http://kroki.internal/mermaid/png \
  /specflow:generate-erd specs/TS-2026-003.md --render --format png --no-project-copy
```
