# Cross-cutting: UI Checks (testflow)

> Used during P2 (or before P4) whenever the agent must see a web UI. Browsers run headless or inside Docker only — never on the user's display, mouse, or keyboard.

```
ui-check  /testflow:ui-check check                    → preflight: PROJECT_PLAYWRIGHT, BROWSER_CACHE, DOCKER, MCP_PLAYWRIGHT (headless|HEADED), WARN
          /testflow:ui-check <url> [--device ..] [--color-scheme dark] [--wait-for <sel>] [--full-page]
                                                      → scripts/capture.sh → .testflow/screenshots/*.png → Read
          /testflow:ui-check vr test|update|build|clean [--dir <subdir>] [--platform linux/amd64] [-- <pw args>]
                                                      → scripts/vr.sh: Playwright VR in Docker (image testflow-pw:<ver>-<arch>)
          /testflow:ui-check setup-mcp                → Playwright MCP --headless --isolated (per-harness config; next session)
```

**Interaction order** — (A) Playwright MCP if loaded and headless → (B) temporary `.testflow/tmp/explore.mjs` using the project's Playwright → (C) capture only, and tell the user what is missing.

**Ask first** — MCP config changes, browser downloads (~200MB), first Docker image build (~3.5GB), `vr update` (only after the user confirms the visual change was intended).

**Baselines** — always created and compared via `vr.sh` (`*-linux.png`). Running `npx playwright test` on the macOS host looks for `*-darwin.png` instead.

**Out of scope (guidance only)** — Xvfb headed browsers, macOS/Windows apps, cloud sandboxes, Android/iOS: `references/other-methods.md`.
