#!/bin/bash
set -euo pipefail
SPECS_DIR="${1:-specs}"
OUTPUT="$SPECS_DIR/registry.md"
echo "📋 참조 ID 수집 중... ($SPECS_DIR)"
cat > "$OUTPUT" << 'HEADER'
# 참조 ID 레지스트리
자동 생성 파일입니다.
HEADER
for prefix in US BR FR AC ADR TC TASK; do
  echo "### $prefix" >> "$OUTPUT"
  echo "| ID | 소속 문서 | 컨텍스트 |" >> "$OUTPUT"
  echo "|-----|----------|---------|" >> "$OUTPUT"
  find "$SPECS_DIR" -name "*.md" -not -path "*/reviews/*" -not -name "registry.md" | sort | while read -r file; do
    fn=$(basename "$file" .md)
    grep -n "${prefix}-[0-9]\{3\}" "$file" 2>/dev/null | while IFS=: read -r _ line; do
      id=$(echo "$line" | grep -o "${prefix}-[0-9]\{3\}" | head -1)
      ctx=$(echo "$line" | sed 's/^[ \t]*//' | cut -c1-80)
      [ -n "$id" ] && echo "| $id | $fn | $ctx |" >> "$OUTPUT"
    done
  done
  echo "" >> "$OUTPUT"
done
echo "✅ 레지스트리 생성: $OUTPUT"
