#!/usr/bin/env python3
"""One-time migration: Claude-native SKILL.md → SKILL.common.md

Converts Claude Code plugin files to harness-neutral common format.
- Renames SKILL.md → SKILL.common.md, agent .md → .common.md
- Transforms frontmatter: allowed-tools → abstract tools list
- Abstracts body text: ${CLAUDE_SKILL_DIR} → ${SKILL_DIR}, etc.
- Creates plugin.meta.json from .claude-plugin/plugin.json
- Removes .claude-plugin/ directory
"""

import json
import os
import re
import shutil
import sys

# Claude → abstract tool name mapping (reverse of claude.adapter.json)
TOOL_REVERSE_MAP = {
    "Agent": "sub-agent",
    "Read": "file:read",
    "Write": "file:write",
    "Edit": "file:edit",
    "Grep": "search:grep",
    "Glob": "search:glob",
    "Bash": "shell",
    "Skill": "invoke-skill",
}

# Body text replacements: Claude-specific → abstract
BODY_REPLACEMENTS = {
    "${CLAUDE_SKILL_DIR}": "${SKILL_DIR}",
    "${CLAUDE_PLUGIN_ROOT}": "${PLUGIN_ROOT}",
    "Agent 도구로": "서브에이전트로",
    "Agent tool을": "서브에이전트를",
    "Agent({": "harness_spawn({",
    "subagent_type:": "agent_ref:",
}

# Bash(...) pattern in allowed-tools e.g. "Bash(npx*)" "Bash(git*)"
BASH_PATTERN = re.compile(r"Bash\([^)]*\)")


def parse_frontmatter(content):
    """Split content into (frontmatter_str, body_str). Returns (None, content) if no frontmatter."""
    if not content.startswith("---"):
        return None, content
    end = content.find("\n---", 3)
    if end == -1:
        return None, content
    fm_str = content[4:end]  # skip opening ---\n
    body = content[end + 4:]  # skip \n---
    return fm_str, body


def serialize_frontmatter(fm_str, body):
    return f"---\n{fm_str}\n---{body}"


def parse_allowed_tools(tools_str):
    """Parse 'Read Grep Glob Write' or 'Read Agent' into a list, handling Bash(...)."""
    tools = []
    i = 0
    while i < len(tools_str):
        if tools_str[i] == " ":
            i += 1
            continue
        m = BASH_PATTERN.match(tools_str, i)
        if m:
            tools.append(m.group(0))
            i = m.end()
        else:
            j = tools_str.find(" ", i)
            if j == -1:
                tools.append(tools_str[i:])
                break
            tools.append(tools_str[i:j])
            i = j + 1
    return tools


def abstract_tool(tool):
    """Convert a Claude tool name to abstract name."""
    if tool in TOOL_REVERSE_MAP:
        return TOOL_REVERSE_MAP[tool]
    if tool.startswith("Bash("):
        # Bash(npx*) → shell(npx*)
        inner = tool[5:-1]
        return f"shell({inner})"
    return tool


def transform_frontmatter(fm_str, is_agent=False):
    """Transform frontmatter lines from Claude-native to common format."""
    lines = fm_str.split("\n")
    new_lines = []
    skip_model = False

    for line in lines:
        stripped = line.strip()

        # Remove 'model: claude-opus-4-6' (or any model line)
        if stripped.startswith("model:"):
            skip_model = True
            continue

        # Transform 'allowed-tools:' → 'tools:'
        if stripped.startswith("allowed-tools:"):
            tools_val = stripped.split(":", 1)[1].strip()
            parsed = parse_allowed_tools(tools_val)
            abstract = [abstract_tool(t) for t in parsed]
            new_lines.append(f"tools: [{', '.join(abstract)}]")
            continue

        # Transform agent 'tools:' field (space-separated on same line)
        if is_agent and stripped.startswith("tools:") and not stripped.startswith("tools: ["):
            tools_val = stripped.split(":", 1)[1].strip()
            if tools_val and not tools_val.startswith("["):
                parsed = tools_val.split()
                abstract = [abstract_tool(t) for t in parsed]
                new_lines.append(f"tools: [{', '.join(abstract)}]")
                continue

        # Transform agent 'tools:' with list format (YAML list on following lines handled below)
        if is_agent and stripped == "tools:":
            new_lines.append(line)
            continue

        # Transform YAML list items under tools: for agents
        if is_agent and stripped.startswith("- ") and len(new_lines) > 0:
            prev = new_lines[-1].strip()
            if prev == "tools:" or (prev.startswith("- ") and any(
                l.strip() == "tools:" for l in new_lines
            )):
                tool_name = stripped[2:].strip()
                abstract = abstract_tool(tool_name)
                new_lines.append(f"  - {abstract}")
                continue

        new_lines.append(line)

    return "\n".join(new_lines)


def transform_body(body):
    """Apply body text replacements."""
    for old, new in BODY_REPLACEMENTS.items():
        body = body.replace(old, new)
    return body


def process_skill(filepath):
    """Process a single SKILL.md → SKILL.common.md."""
    with open(filepath, "r") as f:
        content = f.read()

    fm_str, body = parse_frontmatter(content)
    if fm_str is not None:
        fm_str = transform_frontmatter(fm_str, is_agent=False)
    body = transform_body(body)

    if fm_str is not None:
        content = serialize_frontmatter(fm_str, body)
    else:
        content = transform_body(content)

    # Write as .common.md
    new_path = filepath.replace("SKILL.md", "SKILL.common.md")
    with open(new_path, "w") as f:
        f.write(content)
    os.remove(filepath)
    return new_path


def process_agent(filepath):
    """Process an agent .md → .common.md."""
    with open(filepath, "r") as f:
        content = f.read()

    fm_str, body = parse_frontmatter(content)
    if fm_str is not None:
        fm_str = transform_frontmatter(fm_str, is_agent=True)
    body = transform_body(body)

    if fm_str is not None:
        content = serialize_frontmatter(fm_str, body)
    else:
        content = transform_body(content)

    # Rename: orchestrator.md → orchestrator.common.md
    # AGENT.md → AGENT.common.md
    base, ext = os.path.splitext(filepath)
    new_path = base + ".common" + ext
    with open(new_path, "w") as f:
        f.write(content)
    os.remove(filepath)
    return new_path


def create_plugin_meta(plugin_dir):
    """Create plugin.meta.json from .claude-plugin/plugin.json."""
    claude_manifest = os.path.join(plugin_dir, ".claude-plugin", "plugin.json")
    if not os.path.exists(claude_manifest):
        return

    with open(claude_manifest, "r") as f:
        data = json.load(f)

    meta = {
        "name": data.get("name", ""),
        "version": data.get("version", ""),
        "description": data.get("description", ""),
        "author": data.get("author", ""),
    }

    meta_path = os.path.join(plugin_dir, "plugin.meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Remove .claude-plugin/
    shutil.rmtree(os.path.join(plugin_dir, ".claude-plugin"))
    return meta_path


def migrate_plugin(plugin_dir):
    """Migrate a single plugin directory to common format."""
    plugin_name = os.path.basename(plugin_dir)
    print(f"\n{'='*60}")
    print(f"Migrating: {plugin_name}")
    print(f"{'='*60}")

    # 1. Process SKILL.md files
    skill_count = 0
    for root, dirs, files in os.walk(plugin_dir):
        for fname in files:
            if fname == "SKILL.md":
                fpath = os.path.join(root, fname)
                new_path = process_skill(fpath)
                rel = os.path.relpath(new_path, plugin_dir)
                print(f"  skill: {rel}")
                skill_count += 1

    # 2. Process agent .md files
    agent_count = 0
    agents_dir = os.path.join(plugin_dir, "agents")
    if os.path.isdir(agents_dir):
        for root, dirs, files in os.walk(agents_dir):
            for fname in files:
                if fname.endswith(".md") and not fname.endswith(".common.md"):
                    fpath = os.path.join(root, fname)
                    new_path = process_agent(fpath)
                    rel = os.path.relpath(new_path, plugin_dir)
                    print(f"  agent: {rel}")
                    agent_count += 1

    # 3. Create plugin.meta.json
    meta_path = create_plugin_meta(plugin_dir)
    if meta_path:
        print(f"  meta:  plugin.meta.json (created)")
        print(f"  removed: .claude-plugin/")

    # 4. Handle .mcp.json → mcp.common.json
    mcp_path = os.path.join(plugin_dir, ".mcp.json")
    if os.path.exists(mcp_path):
        new_mcp = os.path.join(plugin_dir, "mcp.common.json")
        os.rename(mcp_path, new_mcp)
        print(f"  mcp:   .mcp.json → mcp.common.json")

    # 5. Handle hooks (ghflow-specific)
    hooks_json = os.path.join(plugin_dir, "hooks", "hooks.json")
    if os.path.exists(hooks_json):
        # Remove the Claude-specific hooks.json; adapters provide these
        os.remove(hooks_json)
        print(f"  hooks: hooks.json removed (managed by adapters)")

    # 6. Handle settings.json (ghflow-specific)
    settings_json = os.path.join(plugin_dir, "settings.json")
    if os.path.exists(settings_json):
        os.remove(settings_json)
        print(f"  settings: settings.json removed (harness-specific)")

    print(f"\n  Summary: {skill_count} skills, {agent_count} agents migrated")
    return skill_count, agent_count


def main():
    if len(sys.argv) < 2:
        print("Usage: migrate-to-common.py <plugins-dir> [plugin-name]")
        print("  plugins-dir: path to plugins/ directory")
        print("  plugin-name: optional, migrate only this plugin")
        sys.exit(1)

    plugins_dir = sys.argv[1]
    target = sys.argv[2] if len(sys.argv) > 2 else None

    if not os.path.isdir(plugins_dir):
        print(f"Error: {plugins_dir} is not a directory")
        sys.exit(1)

    total_skills = 0
    total_agents = 0

    for entry in sorted(os.listdir(plugins_dir)):
        plugin_dir = os.path.join(plugins_dir, entry)
        if not os.path.isdir(plugin_dir):
            continue
        if target and entry != target:
            continue

        s, a = migrate_plugin(plugin_dir)
        total_skills += s
        total_agents += a

    print(f"\n{'='*60}")
    print(f"Total: {total_skills} skills, {total_agents} agents migrated")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
