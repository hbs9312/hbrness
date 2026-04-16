#!/usr/bin/env python3
"""Build harness-specific plugin packages from common sources.

Usage:
    build-plugin.py <harness> <plugin-dir> <adapter-json> <output-dir>

Example:
    build-plugin.py claude plugins/specflow adapters/claude.adapter.json dist/claude/specflow
"""

import json
import os
import re
import shutil
import sys


def load_adapter(adapter_path):
    with open(adapter_path, "r") as f:
        return json.load(f)


def parse_frontmatter(content):
    """Split content into (frontmatter_lines, body_str)."""
    if not content.startswith("---"):
        return None, content
    end = content.find("\n---", 3)
    if end == -1:
        return None, content
    fm_str = content[4:end]
    body = content[end + 4:]
    return fm_str, body


def serialize_frontmatter(fm_str, body):
    return f"---\n{fm_str}\n---{body}"


def parse_tools_value(val):
    """Parse tools value: '[file:read, sub-agent]' or YAML list."""
    val = val.strip()
    if val.startswith("["):
        inner = val[1:-1]
        return [t.strip() for t in inner.split(",") if t.strip()]
    return [val]


def transform_tool(tool, tool_map):
    """Transform abstract tool name to harness-specific name."""
    # Handle shell(npx*) pattern
    m = re.match(r"shell\((.+)\)", tool)
    if m:
        inner = m.group(1)
        bash_name = tool_map.get("shell", "shell")
        if bash_name == "Bash":
            return f"Bash({inner})"
        return f"shell({inner})"
    return tool_map.get(tool, tool)


def transform_frontmatter(fm_str, adapter, is_agent=False):
    """Transform common frontmatter to harness-specific format."""
    cfg = adapter["frontmatter"]
    tool_map = cfg["tool_map"]
    strip_keys = set(cfg.get("strip", []))
    add_fields = cfg.get("add", {})
    keep_keys = set(cfg.get("keep", []))
    transform_tools_to = cfg.get("transform_tools_to")

    lines = fm_str.split("\n")
    new_lines = []
    tools_list = None
    in_yaml_list = False
    yaml_list_key = None

    for line in lines:
        stripped = line.strip()

        # Handle YAML list continuation (for agent tools/skills)
        if in_yaml_list:
            if stripped.startswith("- "):
                if yaml_list_key == "tools":
                    tool_name = stripped[2:].strip()
                    mapped = transform_tool(tool_name, tool_map)
                    new_lines.append(f"  - {mapped}")
                else:
                    new_lines.append(line)
                continue
            else:
                in_yaml_list = False

        # Parse key from line
        if ":" in stripped and not stripped.startswith("-"):
            key = stripped.split(":")[0].strip()
        else:
            key = None

        # Skip stripped keys
        if key and key in strip_keys:
            continue

        # Transform 'tools:' field
        if key == "tools":
            val = stripped.split(":", 1)[1].strip()
            if not val:
                # YAML list follows
                in_yaml_list = True
                yaml_list_key = "tools"
                if transform_tools_to:
                    new_lines.append(f"{transform_tools_to}:")
                else:
                    continue  # skip tools entirely for this harness
                continue
            tools = parse_tools_value(val)
            mapped = [transform_tool(t, tool_map) for t in tools]
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for t in mapped:
                if t not in seen:
                    seen.add(t)
                    deduped.append(t)
            if transform_tools_to:
                new_lines.append(f"{transform_tools_to}: {' '.join(deduped)}")
            # else: skip tools for this harness
            continue

        # Handle 'skills:' for agents
        if key == "skills":
            if "skills" in strip_keys:
                val = stripped.split(":", 1)[1].strip()
                if not val:
                    in_yaml_list = True
                    yaml_list_key = "skills_skip"
                continue
            new_lines.append(line)
            val = stripped.split(":", 1)[1].strip()
            if not val:
                in_yaml_list = True
                yaml_list_key = "skills"
            continue

        if in_yaml_list and yaml_list_key == "skills_skip":
            if stripped.startswith("- "):
                continue
            in_yaml_list = False

        new_lines.append(line)

    # Add extra fields (like model)
    for k, v in add_fields.items():
        # Check if already present
        if not any(l.strip().startswith(f"{k}:") for l in new_lines):
            new_lines.append(f"{k}: {v}")

    return "\n".join(new_lines)


def transform_body(body, adapter):
    """Apply body text replacements."""
    replacements = adapter.get("body_replacements", {})
    for old, new in replacements.items():
        body = body.replace(old, new)
    return body


def transform_file(src_path, dst_path, adapter, is_agent=False):
    """Transform a single .common.md file to harness-specific output."""
    with open(src_path, "r") as f:
        content = f.read()

    fm_str, body = parse_frontmatter(content)
    if fm_str is not None:
        fm_str = transform_frontmatter(fm_str, adapter, is_agent=is_agent)
    body = transform_body(body, adapter)

    if fm_str is not None:
        content = serialize_frontmatter(fm_str, body)
    else:
        content = transform_body(content, adapter)

    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
    with open(dst_path, "w") as f:
        f.write(content)


def generate_manifest(plugin_dir, output_dir, adapter):
    """Generate harness-specific plugin manifest from plugin.meta.json."""
    meta_path = os.path.join(plugin_dir, "plugin.meta.json")
    if not os.path.exists(meta_path):
        return

    with open(meta_path, "r") as f:
        meta = json.load(f)

    manifest_dir_name = adapter["manifest_dir"]
    manifest_dir = os.path.join(output_dir, manifest_dir_name)
    os.makedirs(manifest_dir, exist_ok=True)

    manifest = {
        "name": meta["name"],
        "version": meta["version"],
        "description": meta["description"],
        "author": meta.get("author", ""),
    }

    manifest_path = os.path.join(manifest_dir, "plugin.json")
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


def convert_mcp_to_toml(mcp_data):
    """Convert MCP JSON to TOML format for Codex."""
    lines = []
    servers = mcp_data.get("mcpServers", {})
    for name, config in servers.items():
        lines.append(f"[mcp_servers.{name}]")
        if "command" in config:
            lines.append(f'command = "{config["command"]}"')
        if "args" in config:
            args_str = ", ".join(f'"{a}"' for a in config["args"])
            lines.append(f"args = [{args_str}]")
        if "env" in config:
            lines.append(f"")
            lines.append(f"[mcp_servers.{name}.env]")
            for k, v in config["env"].items():
                lines.append(f'{k} = "{v}"')
        lines.append("")
    return "\n".join(lines)


def handle_mcp(plugin_dir, output_dir, adapter):
    """Copy/convert MCP configuration."""
    mcp_src = os.path.join(plugin_dir, "mcp.common.json")
    if not os.path.exists(mcp_src):
        return

    mcp_cfg = adapter.get("mcp", {})
    fmt = mcp_cfg.get("format", "json")
    output_file = mcp_cfg.get("output_file", ".mcp.json")

    with open(mcp_src, "r") as f:
        mcp_data = json.load(f)

    dst_path = os.path.join(output_dir, output_file)
    if fmt == "toml":
        content = convert_mcp_to_toml(mcp_data)
        with open(dst_path, "w") as f:
            f.write(content)
    else:
        with open(dst_path, "w") as f:
            json.dump(mcp_data, f, indent=2, ensure_ascii=False)
            f.write("\n")


def handle_hooks(plugin_dir, output_dir, adapter, repo_root):
    """Copy harness-specific hook configuration."""
    hooks_source = adapter.get("hooks_source")
    if not hooks_source:
        return

    # Check if this plugin has hooks
    hooks_dir = os.path.join(plugin_dir, "hooks")
    if not os.path.isdir(hooks_dir):
        return

    src = os.path.join(repo_root, hooks_source)
    if not os.path.exists(src):
        return

    dst_hooks_dir = os.path.join(output_dir, "hooks")
    os.makedirs(dst_hooks_dir, exist_ok=True)
    shutil.copy2(src, os.path.join(dst_hooks_dir, "hooks.json"))


def load_agent_definitions(plugin_dir):
    """Load all agent .common.md files into a dict keyed by agent ref name."""
    agents = {}
    agents_dir = os.path.join(plugin_dir, "agents")
    if not os.path.isdir(agents_dir):
        return agents

    plugin_name = os.path.basename(plugin_dir.rstrip("/"))
    for root, dirs, files in os.walk(agents_dir):
        for fname in files:
            if not fname.endswith(".common.md"):
                continue
            fpath = os.path.join(root, fname)
            with open(fpath, "r") as f:
                content = f.read()
            # Extract name from frontmatter
            fm_str, body = parse_frontmatter(content)
            agent_name = None
            if fm_str:
                for line in fm_str.split("\n"):
                    if line.strip().startswith("name:"):
                        agent_name = line.split(":", 1)[1].strip()
                        break
            if agent_name:
                ref = f"{plugin_name}:{agent_name}"
                # Store body only (strip frontmatter for inlining)
                agents[ref] = body.strip()
    return agents


def inline_agent_into_skill(skill_content, agent_defs, adapter):
    """For harnesses that need inline agents (like Codex), append referenced agent
    definitions to the skill body so spawn_agent has full instructions."""
    # Find agent references: `plugin:agent-name` pattern
    refs_found = re.findall(r'`([a-z][-a-z]+:[a-z][-a-z]+)`', skill_content)
    # Also check harness_spawn / spawn_agent agent_ref patterns
    refs_found += re.findall(r'agent_ref:\s*"([^"]+)"', skill_content)

    # Deduplicate while preserving order
    seen = set()
    unique_refs = []
    for ref in refs_found:
        if ref not in seen and ref in agent_defs:
            seen.add(ref)
            unique_refs.append(ref)

    inlined = []
    for ref in unique_refs:
        agent_body = agent_defs[ref]
        agent_body = transform_body(agent_body, adapter)
        inlined.append((ref, agent_body))

    if not inlined:
        return skill_content

    # Append agent definitions section
    parts = [skill_content.rstrip()]
    parts.append("\n\n---\n")
    parts.append("## 참조 에이전트 정의\n")
    parts.append("아래는 이 스킬이 spawn_agent로 호출하는 에이전트의 전체 지침입니다.\n")
    parts.append("spawn_agent 호출 시 이 내용을 프롬프트로 전달하세요.\n")
    for ref, body in inlined:
        parts.append(f"\n### `{ref}`\n")
        parts.append(body)
        parts.append("\n")

    return "\n".join(parts)


def build_plugin(harness, plugin_dir, adapter_path, output_dir):
    """Build a harness-specific plugin from common sources."""
    adapter = load_adapter(adapter_path)
    repo_root = os.path.dirname(os.path.dirname(adapter_path))
    plugin_name = os.path.basename(plugin_dir.rstrip("/"))
    should_inline_agents = adapter.get("inline_agents", False)

    print(f"  Building {plugin_name} for {harness}...")

    # Pre-load agent definitions if inlining is needed
    agent_defs = {}
    if should_inline_agents:
        agent_defs = load_agent_definitions(plugin_dir)
        # Also load agents from other plugins (for cross-plugin refs like xreview)
        plugins_root = os.path.dirname(plugin_dir.rstrip("/"))
        for entry in os.listdir(plugins_root):
            other_dir = os.path.join(plugins_root, entry)
            if os.path.isdir(other_dir) and entry != plugin_name:
                agent_defs.update(load_agent_definitions(other_dir))

    # Clean output
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)

    # Walk source and process files
    for root, dirs, files in os.walk(plugin_dir):
        rel_root = os.path.relpath(root, plugin_dir)

        for fname in files:
            src_path = os.path.join(root, fname)
            rel_path = os.path.join(rel_root, fname) if rel_root != "." else fname

            # Skip plugin.meta.json (will generate manifest)
            if fname == "plugin.meta.json":
                continue

            # Skip mcp.common.json (handled separately)
            if fname == "mcp.common.json":
                continue

            # Transform SKILL.common.md → SKILL.md
            if fname == "SKILL.common.md":
                dst_name = "SKILL.md"
                dst_path = os.path.join(output_dir, rel_root, dst_name) if rel_root != "." else os.path.join(output_dir, dst_name)
                transform_file(src_path, dst_path, adapter, is_agent=False)
                # Inline agents if needed
                if should_inline_agents and agent_defs:
                    with open(dst_path, "r") as f:
                        content = f.read()
                    content = inline_agent_into_skill(content, agent_defs, adapter)
                    with open(dst_path, "w") as f:
                        f.write(content)
                continue

            # Transform agent .common.md → .md
            if fname.endswith(".common.md") and "agents" in rel_path:
                dst_name = fname.replace(".common.md", ".md")
                dst_path = os.path.join(output_dir, rel_root, dst_name) if rel_root != "." else os.path.join(output_dir, dst_name)
                transform_file(src_path, dst_path, adapter, is_agent=True)
                continue

            # Copy all other files as-is
            dst_path = os.path.join(output_dir, rel_path)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src_path, dst_path)

    # Generate manifest
    generate_manifest(plugin_dir, output_dir, adapter)

    # Handle MCP
    handle_mcp(plugin_dir, output_dir, adapter)

    # Handle hooks
    handle_hooks(plugin_dir, output_dir, adapter, repo_root)

    # Count outputs
    skill_count = sum(1 for r, d, f in os.walk(output_dir) for fn in f if fn == "SKILL.md")
    agent_count = sum(1 for r, d, f in os.walk(os.path.join(output_dir, "agents")) for fn in f if fn.endswith(".md")) if os.path.isdir(os.path.join(output_dir, "agents")) else 0
    print(f"    → {skill_count} skills, {agent_count} agents")


def main():
    if len(sys.argv) != 5:
        print("Usage: build-plugin.py <harness> <plugin-dir> <adapter-json> <output-dir>")
        sys.exit(1)

    harness, plugin_dir, adapter_path, output_dir = sys.argv[1:5]
    build_plugin(harness, plugin_dir, adapter_path, output_dir)


if __name__ == "__main__":
    main()
