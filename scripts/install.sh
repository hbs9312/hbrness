#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
DIST_DIR="$ROOT/dist"

usage() {
  echo "Usage: install.sh <claude|codex> [plugin-name]"
  echo ""
  echo "  Builds and installs plugins for the specified harness."
  echo "  If plugin-name is omitted, installs all plugins."
  echo ""
  echo "  install.sh claude              # Install all to Claude Code"
  echo "  install.sh codex               # Install all to Codex CLI"
  echo "  install.sh codex specflow      # Install specflow only"
  echo ""
  echo "Other commands:"
  echo "  install.sh uninstall <claude|codex> [plugin-name]"
  echo "  install.sh list <claude|codex>"
  exit 1
}

# --- Claude Code ---

claude_install() {
  local plugin_name="$1"
  local src="$DIST_DIR/claude/$plugin_name"

  if [ ! -d "$src" ]; then
    echo "  ERROR: $src not found. Run build.sh claude first."
    return 1
  fi

  echo "  Installing $plugin_name to Claude Code..."
  echo "  → claude --plugin-dir $src"
  echo ""
  echo "  Claude Code does not support persistent local plugin paths."
  echo "  Use one of these methods:"
  echo ""
  echo "  1) Per-session: launch with --plugin-dir flag"
  echo "     claude --plugin-dir $src"
  echo ""
  echo "  2) Persistent: add to project .claude/settings.local.json"
  echo "     {\"plugins\": [\"$src\"]}"
  echo ""
}

claude_uninstall() {
  local plugin_name="$1"
  echo "  Claude plugins are loaded per-session via --plugin-dir."
  echo "  Remove the path from .claude/settings.local.json if configured."
}

claude_list() {
  echo "  Claude plugins in dist/claude/:"
  for d in "$DIST_DIR/claude"/*/; do
    [ -d "$d" ] && echo "    $(basename "$d")"
  done
}

# --- Codex CLI ---

CODEX_SKILLS_DIR="${HOME}/.codex/skills"

codex_install() {
  local plugin_name="$1"
  local src="$DIST_DIR/codex/$plugin_name"

  if [ ! -d "$src" ]; then
    echo "  ERROR: $src not found. Run build.sh codex first."
    return 1
  fi

  mkdir -p "$CODEX_SKILLS_DIR"

  local count=0
  for skill_dir in "$src/skills"/*/; do
    [ ! -d "$skill_dir" ] && continue
    local skill_basename
    skill_basename=$(basename "$skill_dir")
    local link_name="${plugin_name}-${skill_basename}"
    local target="$CODEX_SKILLS_DIR/$link_name"

    # Remove existing link/dir
    if [ -L "$target" ] || [ -d "$target" ]; then
      rm -rf "$target"
    fi

    ln -s "$skill_dir" "$target"
    count=$((count + 1))
  done

  # Install agents (if any) — symlink the agents dir
  if [ -d "$src/agents" ]; then
    local agents_link="$CODEX_SKILLS_DIR/${plugin_name}--agents"
    [ -L "$agents_link" ] && rm "$agents_link"
    ln -s "$src/agents" "$agents_link"
  fi

  # Install hooks (if any)
  if [ -d "$src/hooks" ]; then
    local hooks_link="$CODEX_SKILLS_DIR/${plugin_name}--hooks"
    [ -L "$hooks_link" ] && rm "$hooks_link"
    ln -s "$src/hooks" "$hooks_link"
  fi

  echo "  $plugin_name: $count skills symlinked to $CODEX_SKILLS_DIR/"
}

codex_uninstall() {
  local plugin_name="$1"
  local count=0

  for link in "$CODEX_SKILLS_DIR"/${plugin_name}-*; do
    if [ -L "$link" ]; then
      rm "$link"
      count=$((count + 1))
    fi
  done

  # Also remove agents/hooks links
  for link in "$CODEX_SKILLS_DIR"/${plugin_name}--*; do
    if [ -L "$link" ]; then
      rm "$link"
      count=$((count + 1))
    fi
  done

  if [ "$count" -gt 0 ]; then
    echo "  $plugin_name: removed $count symlinks"
  else
    echo "  $plugin_name: no symlinks found"
  fi
}

codex_list() {
  echo "  Installed Codex skills (symlinks in $CODEX_SKILLS_DIR/):"
  local found=0
  for link in "$CODEX_SKILLS_DIR"/*/; do
    if [ -L "${link%/}" ]; then
      local target
      target=$(readlink "${link%/}")
      if [[ "$target" == *"hbrness"* ]]; then
        echo "    $(basename "${link%/}") → $target"
        found=$((found + 1))
      fi
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo "    (none)"
  fi
}

# --- Main ---

CMD="${1:-}"
[ -z "$CMD" ] && usage

case "$CMD" in
  claude)
    PLUGIN="${2:-}"
    # Build first
    "$SCRIPT_DIR/build.sh" claude $PLUGIN
    echo ""
    if [ -n "$PLUGIN" ]; then
      claude_install "$PLUGIN"
    else
      for d in "$DIST_DIR/claude"/*/; do
        [ -d "$d" ] && claude_install "$(basename "$d")"
      done
    fi
    ;;

  codex)
    PLUGIN="${2:-}"
    # Build first
    "$SCRIPT_DIR/build.sh" codex $PLUGIN
    echo ""
    echo "Installing to Codex CLI..."
    if [ -n "$PLUGIN" ]; then
      codex_install "$PLUGIN"
    else
      for d in "$DIST_DIR/codex"/*/; do
        [ -d "$d" ] && codex_install "$(basename "$d")"
      done
    fi
    echo ""
    echo "Done. Restart Codex to pick up new skills."
    ;;

  uninstall)
    HARNESS="${2:-}"
    PLUGIN="${3:-}"
    [ -z "$HARNESS" ] && usage
    case "$HARNESS" in
      claude)
        if [ -n "$PLUGIN" ]; then
          claude_uninstall "$PLUGIN"
        else
          echo "  Specify a plugin name to uninstall."
        fi
        ;;
      codex)
        if [ -n "$PLUGIN" ]; then
          codex_uninstall "$PLUGIN"
        else
          # Uninstall all hbrness plugins
          for d in "$DIST_DIR/codex"/*/; do
            [ -d "$d" ] && codex_uninstall "$(basename "$d")"
          done
        fi
        ;;
      *) usage ;;
    esac
    ;;

  list)
    HARNESS="${2:-}"
    [ -z "$HARNESS" ] && usage
    case "$HARNESS" in
      claude) claude_list ;;
      codex) codex_list ;;
      *) usage ;;
    esac
    ;;

  *) usage ;;
esac
