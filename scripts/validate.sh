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

# Check no hardcoded ~/.claude or ~/.codex in common source (must use placeholder or ~/.hbrness)
# See plugins/AUTHORING.md for the 3-tier storage convention.
# Files that declare `harness:` frontmatter (Tier 3) are exempt because they're
# explicitly scoped to specific harness(es) — hardcoded paths are legitimate there.
hardcoded_violations=""
while IFS= read -r f; do
  # Skip if file has harness: gate declared (Tier 3 exemption)
  if head -20 "$f" 2>/dev/null | grep -qE '^harness:'; then
    continue
  fi
  hardcoded_violations="$hardcoded_violations$f"$'\n'
done < <(grep -rlE '~/\.claude|~/\.codex|\$HOME/\.claude|\$HOME/\.codex' "$PLUGINS_DIR" --include="*.common.md" 2>/dev/null)
hardcoded_violations=$(echo "$hardcoded_violations" | sed '/^$/d')
if [ -n "$hardcoded_violations" ]; then
  err "Found hardcoded harness path (~/.claude|~/.codex|\$HOME/.claude|\$HOME/.codex) in common source (see plugins/AUTHORING.md — use {HARNESS_HOME}, ~/.hbrness, or gate with 'harness:'):"
  echo "$hardcoded_violations" | while read -r f; do echo "    $f"; done
else
  ok "No hardcoded harness paths in common source (Tier 3 gated files exempt)"
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

  # Skill count parity (accounting for 'harness:' gate in source frontmatter)
  # Expected source count for this harness = total SKILL.common.md minus those gated out.
  source_total=$(find "$PLUGINS_DIR" -name "SKILL.common.md" 2>/dev/null | wc -l | tr -d ' ')
  gated_out=0
  while IFS= read -r skill_src; do
    # Read lines 1..20 of frontmatter; if 'harness:' line exists and doesn't include current harness, count as gated out
    hdr=$(head -20 "$skill_src" 2>/dev/null)
    harness_line=$(echo "$hdr" | awk -F: '/^harness:/{print $0; exit}')
    if [ -z "$harness_line" ]; then
      continue
    fi
    # If the line's value contains the current harness name, keep it; otherwise gated out
    if echo "$harness_line" | grep -q "$harness"; then
      continue
    fi
    gated_out=$((gated_out + 1))
  done < <(find "$PLUGINS_DIR" -name "SKILL.common.md" 2>/dev/null)
  expected_count=$((source_total - gated_out))

  dist_count=$(find "$harness_dir" -name "SKILL.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$expected_count" -eq "$dist_count" ]; then
    if [ "$gated_out" -gt 0 ]; then
      ok "Skill count matches: $expected_count expected (source=$source_total, gated-out=$gated_out) = $dist_count $harness"
    else
      ok "Skill count matches: $source_total source = $dist_count $harness"
    fi
  else
    err "Skill count mismatch: expected $expected_count (source=$source_total, gated-out=$gated_out) != $dist_count $harness"
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
