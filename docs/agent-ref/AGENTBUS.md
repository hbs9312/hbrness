# Cross-cutting: Agent Messaging (agentbus)

> Not a pipeline phase — cross-session, tool-agnostic (claude / codex / shell). Fire-and-forget, not RPC: if you need a reply, the recipient sends one back with the same command.

```
agent-register   /agent-register <alias> [--tool claude|codex|shell] [--pane <%id>]  → bind current tmux pane to an alias
agent-list       /agent-list                                          → registry table (prunes dead panes; current pane starred)
agent-send       /agent-send <alias> <msg>                            → inject into recipient's prompt via tmux send-keys
                 /agent-send <alias> --file <path> | --json           → write to recipient inbox, inject notification only
agent-inbox      /agent-inbox [list|show <id>|mark <id>|clear]         → read own mailbox
agent-unregister /agent-unregister [alias]                            → release alias (defaults to current pane's)
```

**Delivery split** — short messages land directly in the recipient's prompt and leave no trace. Long or structured payloads (`--file` / `--json`) are stored under `~/.hbrness/agentbus/inbox/<recipient>/` and only a notification is injected; those are the only messages `agent-inbox` can show.

**Typical use** — split frontend and backend work into separate tmux sessions, register each, and notify across when a contract changes.
