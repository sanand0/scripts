---
name: webapp-testing
description: Test local web applications with Playwright
license: Complete terms in LICENSE.txt
---

Use Python Playwright for local web-app testing.
If a server must be managed, use `scripts/with_server.py`; run it with `--help` first and treat it as a black box rather than reading its source.

- For human-visible controls, prefer role/label/accessible-name locators. If unclear, inspect the accessibility tree before inventing CSS selectors. Re-inspect after meaningful UI changes.
- Use DOM for exact extraction/hidden attributes and screenshots for visual/layout diagnosis.
- Do not wait for `networkidle` by default; long-lived requests can prevent it. Wait for the specific observable UI state, selector, response, or event the task actually needs.
