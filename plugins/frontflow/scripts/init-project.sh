#!/bin/bash
set -euo pipefail
echo "🚀 frontflow 프로젝트 초기화"
CONTEXT_DIR=".frontflow"
mkdir -p "$CONTEXT_DIR"
if [ ! -f "$CONTEXT_DIR/frontend.md" ]; then
  cp "$(dirname "$0")/../context/frontend.md" "$CONTEXT_DIR/frontend.md"
  echo "✅ $CONTEXT_DIR/frontend.md 생성 — 프로젝트에 맞게 작성하세요"
else
  echo "⏭️  $CONTEXT_DIR/frontend.md 이미 존재"
fi
echo "🎉 초기화 완료! $CONTEXT_DIR/frontend.md 를 작성한 후 워크플로우를 시작하세요."
