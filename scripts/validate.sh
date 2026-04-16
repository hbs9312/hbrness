#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGINS_DIR="$ROOT/plugins"
DIST_DIR="$ROOT/dist"
ERRORS=0

err() { echo "  ERROR: $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "  WARN:  $1"; }
ok() { echo "  OK:    $1"; }

echo "========================================"
echo "Validating hbrness build outputs"
echo "========================================"

# --- 1. Source validation (plugins/) ---
echo ""
echo "--- Source (plugins/) ---"

# Check no SKILL.md without .common. in plugins/
stale_skills=$(find "$PLUGINS_DIR" -name "SKILL.md" -not -name "*.common.md" 2>/dev/null | head -5)
if [ -n "$stale_skills" ]; then
  err "Found non-common SKILL.md in source (should be SKILL.common.md):"
  echo "$stale_skills" | while read -r f; do echo "    $f"; done
else
  ok "All skills use .common.md naming"
fi

# Check no ${CLAUDE_ in common source files
claude_refs=$(grep -rl '\${CLAUDE_' "$PLUGINS_DIR" --include="*.common.md" 2>/dev/null | head -5 || true)
if [ -n "$claude_refs" ]; then
  err "Found \${CLAUDE_ references in common source:"
  echo "$claude_refs" | while read -r f; do echo "    $f"; done
else
  ok "No Claude-specific env vars in common source"
fi

# Check no ${CODEX_ in common source files
codex_refs=$(grep -rl '\${CODEX_' "$PLUGINS_DIR" --include="*.common.md" 2>/dev/null | head -5 || true)
if [ -n "$codex_refs" ]; then
  err "Found \${CODEX_ references in common source:"
  echo "$codex_refs" | while read -r f; do echo "    $f"; done
else
  ok "No Codex-specific env vars in common source"
fi

# --- 2. Per-harness validation ---
for harness in claude codex; do
  harness_dir="$DIST_DIR/$harness"
  if [ ! -d "$harness_dir" ]; then
    warn "$harness build output not found (skipping)"
    continue
  fi

  echo ""
  echo "--- dist/$harness/ ---"

  # No .common.md in dist
  leftover=$(find "$harness_dir" -name "*.common.md" 2>/dev/null | head -5)
  if [ -n "$leftover" ]; then
    err "Found .common.md files in dist/$harness/ (should be converted):"
    echo "$leftover" | while read -r f; do echo "    $f"; done
  else
    ok "No .common.md leftover"
  fi

  # Cross-contamination check
  if [ "$harness" = "claude" ]; then
    contam=$(grep -rl '\${CODEX_' "$harness_dir" --include="*.md" 2>/dev/null | head -5 || true)
    if [ -n "$contam" ]; then
      err "Found \${CODEX_ in Claude output:"
      echo "$contam" | while read -r f; do echo "    $f"; done
    else
      ok "No Codex contamination in Claude output"
    fi
  fi

  if [ "$harness" = "codex" ]; then
    contam=$(grep -rl '\${CLAUDE_' "$harness_dir" --include="*.md" 2>/dev/null | head -5 || true)
    if [ -n "$contam" ]; then
      err "Found \${CLAUDE_ in Codex output:"
      echo "$contam" | while read -r f; do echo "    $f"; done
    else
      ok "No Claude contamination in Codex output"
    fi

    # Codex should not have allowed-tools in frontmatter
    # Check first 10 lines of SKILL.md files for allowed-tools
    at_found=0
    while IFS= read -r skill_file; do
      if head -10 "$skill_file" | grep -q "^allowed-tools:"; then
        err "allowed-tools found in Codex output: $skill_file"
        at_found=1
      fi
    done < <(find "$harness_dir" -name "SKILL.md" 2>/dev/null)
    if [ "$at_found" -eq 0 ]; then
      ok "No allowed-tools in Codex SKILL.md frontmatter"
    fi
  fi

  # Manifest check
  for plugin_dir in "$harness_dir"/*/; do
    plugin_name=$(basename "$plugin_dir")
    if [ "$harness" = "claude" ]; then
      manifest="$plugin_dir/.claude-plugin/plugin.json"
    else
      manifest="$plugin_dir/.codex-plugin/plugin.json"
    fi
    if [ ! -f "$manifest" ]; then
      err "Missing manifest for $plugin_name in dist/$harness/"
    fi
  done
  ok "Manifests present for all plugins"

  # Skill count parity
  source_count=$(find "$PLUGINS_DIR" -name "SKILL.common.md" 2>/dev/null | wc -l | tr -d ' ')
  dist_count=$(find "$harness_dir" -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$source_count" -eq "$dist_count" ]; then
    ok "Skill count matches: $source_count source = $dist_count $harness"
  else
    err "Skill count mismatch: $source_count source != $dist_count $harness"
  fi
done

# --- Summary ---
echo ""
echo "========================================"
if [ "$ERRORS" -eq 0 ]; then
  echo "PASS: All validations passed"
else
  echo "FAIL: $ERRORS error(s) found"
fi
echo "========================================"

exit "$ERRORS"
