# 화면설계서 출력 템플릿

```yaml
문서 ID: UI-{YYYY}-{NNN}
기능 참조: {FS ID}
와이어프레임 참조: {WF ID}
Figma 링크: {URL}
작성일: {YYYY-MM-DD}
상태: Draft

# 1. 디자인 토큰 참조
색상: {용도}: {$토큰}
타이포: {용도}: {$토큰}
간격: {용도}: {$토큰}

# 2. 컴포넌트 명세
### {컴포넌트명}
- 구성: [{자식}] + [{자식}]
- 상태별: default, hover, pressed, disabled, loading, error
- 터치 영역: 최소 44×44px

# 3. 인터랙션 & 애니메이션
{이름}: 트리거, 효과, duration, easing

# 4. 반응형 규칙
# 5. 접근성 요구사항
```
