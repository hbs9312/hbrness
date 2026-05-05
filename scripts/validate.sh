#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGINS_DIR="$ROOT/plugins"
DIST_DIR="$ROOT/dist"
ERRORS=0

err() { echo "  ERROR: $1"; ERRORS=$((ERRORS + 1)); }
warn() { echo "  WARN:  $1"; }
ok() { echo "  OK:    $1"; }

is_harness_gated_out() {
  local file="$1"
  local harness="$2"
  local result

  result=$(awk -v harness="$harness" '
    BEGIN { found = 0; allowed = 0; in_list = 0 }
    NR > 40 { exit }
    /^---$/ && NR > 1 { exit }
    /^harness:/ {
      found = 1
      val = $0
      sub(/^harness:[[:space:]]*/, "", val)
      gsub(/[\[\]",]/, " ", val)
      if (val != "") {
        n = split(val, parts, /[[:space:]]+/)
        for (i = 1; i <= n; i++) {
          if (parts[i] == harness) allowed = 1
        }
        exit
      }
      in_list = 1
      next
    }
    in_list && /^[[:space:]]*-[[:space:]]*/ {
      item = $0
      sub(/^[[:space:]]*-[[:space:]]*/, "", item)
      gsub(/[\[\]",]/, " ", item)
      if (item == harness) allowed = 1
      next
    }
    in_list && $0 !~ /^[[:space:]]*$/ { exit }
    END {
      if (!found || allowed) print "no"; else print "yes"
    }
  ' "$file")

  [ "$result" = "yes" ]
}

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

    # Codex strips agent tools from frontmatter. A malformed strip can leave
    # orphan YAML list items like "  - shell" with no owning key.
    dangling_found=0
    while IFS= read -r md_file; do
      if ! dangling_lines=$(awk '
        BEGIN {
          in_fm = 0
          seen_fm = 0
          in_list = 0
          err = 0
        }
        NR == 1 && $0 == "---" {
          in_fm = 1
          seen_fm = 1
          next
        }
        in_fm && $0 == "---" {
          in_fm = 0
          exit
        }
        in_fm {
          line = $0
          if (line ~ /^[[:space:]]*$/ || line ~ /^[[:space:]]*#/) {
            next
          }
          if (line ~ /^[[:space:]]*-[[:space:]]+/) {
            if (!in_list) {
              print FILENAME ":" NR ":" line
              err = 1
            }
            next
          }
          if (line ~ /^[^[:space:]#][^:]*:[[:space:]]*$/) {
            in_list = 1
            next
          }
          if (line ~ /^[^[:space:]#][^:]*:/) {
            in_list = 0
            next
          }
          if (line !~ /^[[:space:]]/) {
            in_list = 0
          }
        }
        END {
          if (err) {
            exit 1
          }
          if (seen_fm && in_fm) {
            print FILENAME ": unterminated frontmatter"
            exit 1
          }
        }
      ' "$md_file"); then
        err "Dangling YAML list item in Codex frontmatter: $md_file"
        echo "$dangling_lines" | head -5 | while read -r line; do echo "    $line"; done
        dangling_found=1
      fi
    done < <(find "$harness_dir" -name "*.md" 2>/dev/null)
    if [ "$dangling_found" -eq 0 ]; then
      ok "No dangling YAML list items in Codex Markdown frontmatter"
    fi

    dispatcher_missing=0
    while IFS= read -r skill_file; do
      if grep -Eq 'spawn_agent로 `[a-z][-a-z]+:[a-z][-a-z]+`' "$skill_file"; then
        if ! grep -q "참조 에이전트 정의" "$skill_file"; then
          err "Codex dispatcher skill references plugin agent without inlined definition: $skill_file"
          dispatcher_missing=1
        fi
      fi
    done < <(find "$harness_dir" -name "SKILL.md" 2>/dev/null)
    if [ "$dispatcher_missing" -eq 0 ]; then
      ok "Codex dispatcher skills include referenced agent definitions"
    fi

    raw_agent_ref=$(grep -Rnl 'agent_ref:' "$harness_dir" --include="*.md" 2>/dev/null | head -5 || true)
    if [ -n "$raw_agent_ref" ]; then
      err "Found raw agent_ref usage in Codex output:"
      echo "$raw_agent_ref" | while read -r f; do echo "    $f"; done
    else
      ok "No raw agent_ref usage in Codex output"
    fi

    missing_agent_links=0
    while IFS= read -r agent_src; do
      if is_harness_gated_out "$agent_src" "codex"; then
        continue
      fi

      rel="${agent_src#$PLUGINS_DIR/}"
      plugin="${rel%%/*}"
      agent_rel="${rel#*/agents/}"

      if [[ "$agent_rel" != */AGENT.common.md ]]; then
        err "Codex source agent is not directory-form and cannot be installed deterministically: $agent_src"
        missing_agent_links=1
        continue
      fi

      agent_dir="${agent_rel%/AGENT.common.md}"
      if [ ! -f "$harness_dir/$plugin/agents/$agent_dir/AGENT.md" ]; then
        err "Codex source agent missing installable dist directory: $agent_src"
        missing_agent_links=1
      fi
    done < <(find "$PLUGINS_DIR" -path "*/agents/*" -name "*.common.md" 2>/dev/null)
    if [ "$missing_agent_links" -eq 0 ]; then
      ok "Codex source agents are directory-form and installable"
    fi

    missing_skills_manifest=0
    while IFS= read -r plugin_dir; do
      manifest="$plugin_dir/.codex-plugin/plugin.json"
      if [ -d "$plugin_dir/skills" ] && ! grep -q '"skills": "./skills/"' "$manifest"; then
        err "Codex plugin with skills missing manifest skills field: $plugin_dir"
        missing_skills_manifest=1
      fi
    done < <(find "$harness_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)
    if [ "$missing_skills_manifest" -eq 0 ]; then
      ok "Codex plugin manifests expose skills directories"
    fi

    bad_hooks=0
    for plugin_src in "$PLUGINS_DIR"/*/; do
      plugin_name=$(basename "$plugin_src")
      [ -d "$plugin_src/hooks" ] || continue
      if [ ! -f "$harness_dir/$plugin_name/hooks.json" ]; then
        err "Codex hook-capable plugin missing root hooks.json: $harness_dir/$plugin_name"
        bad_hooks=1
      fi
      manifest="$harness_dir/$plugin_name/.codex-plugin/plugin.json"
      if [ -f "$manifest" ] && ! grep -q '"hooks": "./hooks.json"' "$manifest"; then
        err "Codex hook-capable plugin missing manifest hooks field: $manifest"
        bad_hooks=1
      fi
      if [ -f "$harness_dir/$plugin_name/hooks/hooks.json" ]; then
        err "Codex hook config should be root hooks.json, not hooks/hooks.json: $harness_dir/$plugin_name"
        bad_hooks=1
      fi
    done
    if [ "$bad_hooks" -eq 0 ]; then
      ok "Codex hook configs are emitted at plugin root"
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
    if is_harness_gated_out "$skill_src" "$harness"; then
      gated_out=$((gated_out + 1))
    fi
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

  # Agent count parity (accounting for 'harness:' gate in source frontmatter)
  agent_source_total=$(find "$PLUGINS_DIR" -path "*/agents/*" -name "*.common.md" 2>/dev/null | wc -l | tr -d ' ')
  agent_gated_out=0
  while IFS= read -r agent_src; do
    if is_harness_gated_out "$agent_src" "$harness"; then
      agent_gated_out=$((agent_gated_out + 1))
    fi
  done < <(find "$PLUGINS_DIR" -path "*/agents/*" -name "*.common.md" 2>/dev/null)
  agent_expected_count=$((agent_source_total - agent_gated_out))

  agent_dist_count=$(find "$harness_dir" -path "*/agents/*" -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$agent_expected_count" -eq "$agent_dist_count" ]; then
    if [ "$agent_gated_out" -gt 0 ]; then
      ok "Agent count matches: $agent_expected_count expected (source=$agent_source_total, gated-out=$agent_gated_out) = $agent_dist_count $harness"
    else
      ok "Agent count matches: $agent_source_total source = $agent_dist_count $harness"
    fi
  else
    err "Agent count mismatch: expected $agent_expected_count (source=$agent_source_total, gated-out=$agent_gated_out) != $agent_dist_count $harness"
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
