---
name: devtools
description: Use CDP at localhost:9222 to test/debug web apps and automate browser tasks
notes:
  - https://claude.ai/chat/8324c6ba-7c96-475f-b215-31070b5b0b96
  - https://chatgpt.com/c/6912fbeb-c26c-8322-a633-091f5ef067fb
---

Use CDP at localhost:9222 to:

- Debug/test using inspection (DOM, cookies, storage), screenshots, console logs, breakpoints, JS execution, network intercepts (modify headers, mock responses)
- Automate (research, scrape, ...) using navigation, form-filling, print to PDF
- Log using screenshots, console logs, HAR traces
- Refactor: remove dead code
- Replay test/automation scripts: capture flow as scripts
- Monitor performance, audit using Lighthouse, accessibility with axe-core
- Emulate devices, screen size, dark mode, network speed, geo, time zone
- Harden via cookie audits, pen-testing
- Parallelize using multiple tabs
- Browse safely using separate profiles / incognito mode

Tools: websocat, wscat, uv, node, puppeteer, playwright, cdp-cli, chrome-remote-interface, devtools-protocol

Tips:

- Generate a selector bundle per element. Include role+name, text substring, stable attributes, and a fallback position. Try them in order and remember which one works.
- Combine screenshots with DOM snapshots and accessibility tree (since CSS can be brittle) for better context.
- Annotate with colored borders, labels, or numbers before full-page screenshot and use that for visual context.
- On failure, use screenshot, console logs, recent network requests, localStorage/cookies, DOM for diagnosis.
- Record golden HAR/screenshots/state. Helps spot regression errors, missing headers, caching quirks, and third-party blockers quickly.
