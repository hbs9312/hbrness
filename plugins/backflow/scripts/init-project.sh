#!/bin/bash
set -euo pipefail
echo "🚀 backflow 프로젝트 초기화"
CONTEXT_DIR=".backflow"
mkdir -p "$CONTEXT_DIR"
if [ ! -f "$CONTEXT_DIR/backend.md" ]; then
  cp "$(dirname "$0")/../context/backend.md" "$CONTEXT_DIR/backend.md"
  echo "✅ $CONTEXT_DIR/backend.md 생성 — 프로젝트에 맞게 작성하세요"
else
  echo "⏭️  $CONTEXT_DIR/backend.md 이미 존재"
fi
if [ -f ".gitignore" ] && ! grep -q ".backflow/service-registry.md" .gitignore 2>/dev/null; then
  echo -e "\n# backflow\n.backflow/service-registry.md" >> .gitignore
  echo "✅ .gitignore 업데이트"
fi
echo "🎉 초기화 완료! $CONTEXT_DIR/backend.md 를 작성한 후 워크플로우를 시작하세요."
