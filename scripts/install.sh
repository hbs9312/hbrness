#!/bin/bash
# Wrapper around bin/hbrness.js for backward compatibility.
#
# New preferred entry points:
#   npx hbrness <command> ...
#   hbrness <command> ...             (after "npm install -g hbrness")
#
# Legacy usage that still works here:
#   scripts/install.sh <harness> [plugin]
#   scripts/install.sh uninstall <harness> [plugin]
#   scripts/install.sh list <harness>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
CLI="$ROOT/bin/hbrness.js"

if [ ! -f "$CLI" ]; then
  echo "error: $CLI not found" >&2
  exit 1
fi

# Build dist first if it's missing or stale compared to source.
need_build=0
for harness in claude codex; do
  if [ ! -d "$ROOT/dist/$harness" ]; then
    need_build=1
    break
  fi
done
if [ "$need_build" -eq 1 ]; then
  echo "[hbrness] dist missing — running build first"
  bash "$SCRIPT_DIR/build.sh" all
fi

CMD="${1:-}"

case "$CMD" in
  ""|"-h"|"--help"|"help")
    exec node "$CLI" --help
    ;;
  install|uninstall|list|plugins|--version|-v)
    exec node "$CLI" "$@"
    ;;
  claude|codex)
    # Legacy shorthand: "install.sh claude [plugin]" → "hbrness install claude [plugin]"
    exec node "$CLI" install "$@"
    ;;
  *)
    # Pass through everything else so new commands work without editing this wrapper.
    exec node "$CLI" "$@"
    ;;
esac
