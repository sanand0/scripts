---
name: devtools
description: Use CDP at localhost:9222 to test/debug websites, automate browser tasks
notes:
  - https://claude.ai/chat/8324c6ba-7c96-475f-b215-31070b5b0b96
  - https://chatgpt.com/c/6912fbeb-c26c-8322-a633-091f5ef067fb
---

Use CDP at localhost:9222.
For exploration, use `tmux` with websocat, or wscat, or `uv run --with playwright,markdownify,httpx,readability python -m asyncio` (starts Python REPL with top-level await).
For automation, `npm install playwright` and code in `node`.

Capabilities:

- For DOM HTML to Markdown: turndown, markdownify, or `uvx markitdown file.html`
- Log progress via console: `page.on("console", msg => console.log("LOG:", msg.type(), msg.text()))`. Use CDP's `Console.enable` for replay
- Log screenshots via `(page||locator).screenshot({ path, fullPage, type, quality, ... })`
- Intercept fetch/XHR, parse JSON directly, cache for repeat runs
- HAR traces: `context.tracing.start({ screenshots: true, snapshots: true })` ... `context.tracing.stop({ path: "trace.zip" })`
- Inject JS into existing tabs via a `blob:` URL created in the page context. CSP may block inline scripts.
  - `url = URL.createObjectURL(new Blob([code], { type: "text/javascript" }))`
  - Append `<script src="blob:...">`
  - Avoid `page.addScriptTag({content: ...})` on CSP-heavy sites (e.g. WhatsApp, Google apps).

Uses:

- Debug/test using inspection (DOM, cookies, storage), screenshots, console logs, breakpoints, JS execution, network intercepts (modify headers, mock responses)
- Automate (research, scrape, ...) using navigation, form-filling, print to PDF
- Refactor: remove dead/unused JS, CSS, HTML
- Replay test/automation scripts: capture flow as scripts
- Monitor performance, audit using Lighthouse, axe-core
- Emulate devices, screen size, dark mode, network speed, geo, time zone, color blindness, touch devices
- Harden via cookie audits, pen-testing
- Parallelize using multiple tabs
- Browse safely using separate profiles / incognito mode

Tips:

- When scraping, collect 8-10 diverse variants of the target structure to cover edge cases before implementing selectors.
- Generate a selector bundle per element. Include role+name, text substring, stable attributes, and a fallback position. Try them in order and remember which one works.
- Combine screenshots with DOM snapshots and accessibility tree (since CSS can be brittle) for better context.
- Annotate with colored borders, labels, or numbers before full-page screenshot and use that for visual context.
- On failure, use screenshot, console logs, recent network requests, localStorage/cookies, DOM for diagnosis.
- Record golden HAR/screenshots/state. Helps spot regression errors, missing headers, caching quirks, and third-party blockers quickly.
