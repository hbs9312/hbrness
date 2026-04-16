#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
PLUGINS_DIR="$ROOT/plugins"
ADAPTERS_DIR="$ROOT/adapters"
DIST_DIR="$ROOT/dist"

usage() {
  echo "Usage: build.sh <claude|codex|all> [plugin-name]"
  echo "  harness:     claude, codex, or all"
  echo "  plugin-name: optional, build only this plugin"
  exit 1
}

build_harness() {
  local harness="$1"
  local target_plugin="${2:-}"
  local adapter="$ADAPTERS_DIR/${harness}.adapter.json"

  if [ ! -f "$adapter" ]; then
    echo "Error: adapter not found: $adapter"
    exit 1
  fi

  echo ""
  echo "========================================"
  echo "Building for: $harness"
  echo "========================================"

  for plugin_dir in "$PLUGINS_DIR"/*/; do
    local plugin_name
    plugin_name=$(basename "$plugin_dir")

    if [ -n "$target_plugin" ] && [ "$plugin_name" != "$target_plugin" ]; then
      continue
    fi

    local output_dir="$DIST_DIR/$harness/$plugin_name"
    python3 "$SCRIPT_DIR/build-plugin.py" "$harness" "$plugin_dir" "$adapter" "$output_dir"
  done
}

# --- Main ---

HARNESS="${1:-}"
PLUGIN="${2:-}"

if [ -z "$HARNESS" ]; then
  usage
fi

case "$HARNESS" in
  claude|codex)
    build_harness "$HARNESS" "$PLUGIN"
    ;;
  all)
    build_harness "claude" "$PLUGIN"
    build_harness "codex" "$PLUGIN"
    ;;
  *)
    echo "Error: unknown harness '$HARNESS'"
    usage
    ;;
esac

echo ""
echo "Build complete."
