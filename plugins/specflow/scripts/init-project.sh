#!/bin/bash
set -euo pipefail
SPECS_DIR="specs"
REVIEWS_DIR="specs/reviews"
CONTEXT_DIR=".specflow"
echo "🚀 specflow 프로젝트 초기화"
mkdir -p "$SPECS_DIR" "$REVIEWS_DIR" "$CONTEXT_DIR"
echo "✅ 디렉토리 생성 완료"
if [ ! -f "$CONTEXT_DIR/glossary.md" ]; then
  cat > "$CONTEXT_DIR/glossary.md" << 'INNER'
# 도메인 용어집

## 용어 사전
| 용어 | 정의 | 비고 |
|------|------|------|
| | | |

## 금지 용어 / 동의어 매핑
| 사용 금지 | 올바른 표현 | 이유 |
|-----------|------------|------|
| | | |
INNER
  echo "✅ $CONTEXT_DIR/glossary.md 생성"
fi
if [ ! -f "$CONTEXT_DIR/team.md" ]; then
  cat > "$CONTEXT_DIR/team.md" << 'INNER'
# 팀 컨텍스트

## 팀 구성
| 이름 | 역할 | 역량 태그 | 가용성 | 도메인 익숙도 |
|------|------|-----------|--------|-------------|
| | | | | |

## 속도 이력
스프린트 길이: 2주
평균 velocity: pt/스프린트
보정 계수:

## 기술 스택
- 프레임워크:
- 언어:
- DB:
- 인프라:

## 프로젝트 제약
마일스톤:
  -
INNER
  echo "✅ $CONTEXT_DIR/team.md 생성"
fi
if [ -f ".gitignore" ] && ! grep -q "specs/reviews/" .gitignore 2>/dev/null; then
  echo -e "\n# specflow\nspecs/reviews/" >> .gitignore
  echo "✅ .gitignore 업데이트"
fi
echo "🎉 초기화 완료! .specflow/glossary.md 와 team.md 를 작성하세요."
