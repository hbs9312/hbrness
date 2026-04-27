# ERD 출력 템플릿

## 1) Mermaid 소스 (`.mmd`)

```
erDiagram
    %% ------- 관계 -------
    %% BR-030, self-ref, nullable, inferred
    USERS }o--o| USERS : manages
    %% BR-003
    USERS ||--o| USER_PROFILES : has
    %% BR-012, BR-013
    USERS ||--o{ ORDERS : places
    %% BR-020
    ORDERS ||--|{ ORDER_ITEMS : contains
    %% BR-020
    PRODUCTS ||--o{ ORDER_ITEMS : appears_in

    %% ------- 엔티티 -------
    %% source: TS §4.users
    USERS {
        uuid id PK
        varchar email UK "로그인 이메일"
        varchar name
        uuid manager_id FK "조직도 상위 사용자"
        timestamptz created_at
    }

    %% source: TS §4.user_profiles
    USER_PROFILES {
        uuid user_id PK "FK to users.id"
        text bio
        varchar avatar_url
    }

    %% source: TS §4.orders
    ORDERS {
        uuid id PK
        uuid user_id FK
        varchar status "PENDING|PAID|CANCELED"
        numeric total_amount
        timestamptz created_at
    }

    %% source: TS §4.products
    PRODUCTS {
        uuid id PK
        varchar sku UK
        varchar name
        numeric price
    }

    %% source: TS §4.order_items
    ORDER_ITEMS {
        uuid order_id PK
        uuid product_id PK
        int quantity
        numeric unit_price
    }
```

**중요**: Mermaid `erDiagram` 은 **라인 끝 인라인 `%%` 주석을 거부**합니다. 모든 주석은 해당 라인 바로 위에 독립 라인으로 쓰세요. 파서 에러 메시지가 `Expecting ... got '%'` 로 뜨면 이 규칙 위반입니다.

## 2) 카디널리티 레퍼런스

Mermaid 관계 연산자는 **왼쪽 엔티티에서 본 오른쪽 엔티티의 개수**를 표현합니다.

| 왼쪽 | 오른쪽 | 기호 | 읽기 |
|---|---|---|---|
| 정확히 1 | 정확히 1 | `\|\|--\|\|` | 1:1 필수 |
| 정확히 1 | 0 또는 1 | `\|\|--o\|` | 1:0..1 |
| 정확히 1 | 1 이상 | `\|\|--\|{` | 1:N 필수 |
| 정확히 1 | 0 이상 | `\|\|--o{` | 1:N 옵션 |
| 0 이상 | 0 이상 | `}o--o{` | M:N (조인 테이블 동반) |
| 0 이상 | 정확히 1 | `}o--\|\|` | N:1 |

**TS 제약 → 기호 매핑 휴리스틱**

- `NOT NULL` + `FK` + PK 가 이 FK 포함 아님 → `}o--||` (N:1 필수)
- `NULL 허용` + `FK` → `}o--o|`
- PK 가 (FK_a, FK_b) 두 개 조합 (조인 테이블) → **각 FK 에 대해 개별 N:1 관계만 그림**. 상위 두 엔티티 간의 M:N 단축 관계(`}o--o{`)는 **그리지 않음** — 중복이고 시각적 노이즈. 조인 엔티티 자체가 M:N 의미를 전달.
- 같은 테이블을 가리키는 FK → 자기참조: `}o--||` (nullable 이면 `}o--o|`)
- PK == FK (identifying relationship, 예: `user_profiles.user_id` PK+FK) → 왼쪽 `||--o|` (부모는 0..1 자식만 가질 수 있고, 자식은 부모 필수)

## 3) 프로젝트 사본 (`specs/ERD-{TS-ID}.md`)

```markdown
---
문서 ID: ERD-{TS-ID}
TS 참조: {TS-ID}
FS 참조: {FS-ID 또는 N/A}
작성일: {YYYY-MM-DD}
생성기: specflow:generate-erd
---

# ERD — {TS 제목}

**소스 TS**: `{project-relative TS 경로}`
**엔티티**: {N}개 · **관계**: {M}개
**렌더 엔드포인트**: `{$MERMAID_RENDER_URL 또는 "미사용"}`
**🔗 편집**: [Live Editor 에서 열기]({$DEEP_LINK})  <!-- 팬/줌, 텍스트 이어 편집 -->

## 다이어그램

{렌더 성공 시:}
![ERD](./.assets/ERD-{TS-ID}.{svg|png})

{mermaid 소스 — GitHub/Obsidian 등에서 자동 렌더:}
​```mermaid
{위 §1 내용 그대로}
​```

## Legend — 관계 라벨 원문

| 기호 | 엔티티 쌍 | 라벨 | 원본 서술 (TS) | BR 근거 |
|---|---|---|---|---|
| `\|\|--o{` | USERS → ORDERS | places | "사용자 1명은 여러 주문을 가짐" | BR-012 |
| `\|\|--\|{` | ORDERS → ORDER_ITEMS | contains | "주문은 최소 1개 이상의 라인 아이템" | BR-020 |
| ... | ... | ... | ... | ... |

## 변경 이력

| 일시 | 사유 | TS 커밋 |
|---|---|---|
| {YYYY-MM-DD HH:MM} | 초기 생성 | {git rev-parse --short HEAD} |
```

## 4) 정규화 규칙 (중요)

파싱할 때 실수하기 쉬운 부분:

- **엔티티명**: 공백/하이픈/점을 `_` 로 치환하고 대문자. `order items` → `ORDER_ITEMS`
- **속성명**: 소문자 snake_case 유지. Mermaid 는 `camelCase` 도 허용하지만 일관성 위해 snake
- **타입**: `VARCHAR(255)` → `varchar` / `DECIMAL(10,2)` → `numeric` / `TIMESTAMP` → `timestamptz` (타임존 유/무 구분 단서 있으면 반영)
- **PK 복합키**: 두 줄 모두 `PK` 마커. Mermaid 는 composite PK 의미를 암묵적으로 받음
- **enum/상태값**: 타입이 `ENUM` 이거나 설명에 `"A|B|C"` 가 있으면 속성 주석에 그대로 인용
- **주석에 쉼표**: Mermaid 주석(`%%`) 는 한 줄 끝까지 파싱됨. 여러 BR 나열 시 `%% BR-012, BR-013` 안전
