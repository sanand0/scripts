---
name: devtools
description: Use CDP at localhost:9222 to test/debug websites, automate browser tasks, and inspect/replay browser APIs
---

Use CDP at localhost:9222.
Use `agent-browser` (simpler than Playwright) where helpful. For human-visible UI interaction, start with `agent-browser snapshot -i`; prefer returned `@e*` references, then role + accessible name. Re-snapshot after meaningful UI state changes. Fall back to DOM/CSS only when AX lacks the target.
Playwright browsers are under `${HOME}/.local/share/playwright-browsers`; set `PLAYWRIGHT_BROWSERS_PATH` accordingly.

- For state-changing actions, verify the target and current state first, act once, then verify the observable postcondition before continuing or retrying; never blindly repeat a possibly committed action.
- For repeated structured reads, inspect fetch/XHR before building browser automation. Replay a stable request when it returns the required data; verify representative results against the browser.
- Match representation to problem: AX for semantic targeting; DOM/JS for exact extraction; Network/CDP for APIs/protocol state; screenshots/geometry for visual, canvas, SVG, drag/brush issues.
- On CSP-heavy sites such as WhatsApp or Google apps, inline script injection may fail. A `blob:` script URL created in page context is a useful fallback.
- Do not persist credentials or session headers.
