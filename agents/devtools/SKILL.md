---
name: devtools
description: Use CDP at localhost:9222 to test/debug web apps and automate browser tasks
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

- Highlight relevant DOM elements, take a full-page screenshot, and use that for visual context.
- Snapshot the accessibility tree and highlight nodes by role and name. Then pick targets by role (CSS can be brittle).
- Draw intent on the page. Overlay labels on target elements, then capture a full-page screenshot. You get “what I planned vs what I clicked” proof in one image.
- Capture a DOM “storyboard.” Take narrow, cropped screenshots of every element you will interact with in order. It becomes a visual plan the model can reason about.
- Generate a selector bundle per element. Include role+name, text substring, stable attributes, and a fallback position. Try them in order and remember which one works.
- Add a canary element on each page. Before doing anything, assert the canary exists. If not, you know you are on the wrong state and can recover.
