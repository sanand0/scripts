---
name: code
description: ALWAYS follow this style when writing Python / JavaScript code
---

Coding guidelines

- Prefer libraries to writing code. Prefer popular, modern, minimal, fast libraries
- Write readable code. Keep happy path linear and obvious. Write flow first, then fill in code. Name intuitively
- Keep code short
  - Data over code: Structures beat conditionals. Prefer config.{json|yaml|toml|...} if >= 30 lines
  - DRY: Helpers for repeated logic, precompute shared intermediates
  - Single expression: Skip intermediate variables when clear
  - Early returns fail fast and reduce nesting. Skip defensive fallbacks
  - YAGNI: Skip unused imports, variables, and code
- Change existing code minimally. Retain existing comments. Follow existing style
- If tests exists (or in new code), add failing tests first. Keep tests fast
- Use type hints and single-line docstrings
- Show status & progress for long tasks (>5s)
- Make re-runs efficient for long tasks (>1min). Cache & flush data, LLM/API/HTTP requests
- Read latest docs for fast moving packages: GitHub README, `npm view package-name readme`, ...
- For large/complex libraries, https://context7.com/$ORG/$REPO/llms.txt has docs for https://github.com/$ORG/$REPO

## Python

Only use `uv run`. Not `python` or `python3`

Unless `pyproject.toml` is present, add dependencies to script:

```py
#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["scipy>=1.10", "httpx"]
# ///
```

Preferred Python libs:

`typer`/`click` not `argparse`
`httpx` not `requests`
`lxml` not `xml`
`pandas` not `csv`
`orjson` over `json` if speed/datetime matters
`tenacity` for retries
`pytest`
`python-dotenv`

## JavaScript

Preferred JS style:

- Bootstrap. Minimize custom CSS
- Hyphenated HTML class/ID names (id="user-id" not id="userId")
- ESM2022+. No TypeScript. But enable `// @ts-check`
- Modern browser APIs
- Modern JS features: Use `?.`, `??`, destructuring, spread, implicit returns (`=>` over `=> { return }`)
- Loading indicator while awaiting fetch()
- Error handling only at top level. Render errors for user
- Helpers: `const $ = (s, el = document) => el.querySelector(s); $('#id')...`
- Import maps: `<script type="importmap">{ "imports": { "package-name": "https://cdn.jsdelivr.net/npm/package-name@version" } }</script>`

Preferred JS libs:

```js
import * as d3 from "d3"; // @7/+esm for visualizations
import hljs from "highlight.js"; // @11/+esm highlight Markdown code; link CDN CSS
import { html, render } from "lit-html"; // @3/+esm for DOM updates
import { unsafeHTML } from "lit-html@3/directives/unsafe-html.js";
import { marked } from "marked"; // @16/+esm
import { parse } from "partial-json"; // @0.1/+esm parse streamed JSON. `const { key } = parse('{"key":"v')`

import { asyncLLM } from "asyncllm"; // @2 streams LLM responses. `for await (const { content, error } of asyncLLM(baseURL, { method: "POST", body: JSON.stringify({...}), headers: { Authorization: `Bearer ${apiKey}` } }`
import { bootstrapAlert } from "bootstrap-alert"; // @1 for notifications. `bootstrapAlert({ title: "Success", body: "Toast message", color: "success" })`
import { geminiConfig, openaiConfig } from "bootstrap-llm-provider"; // @1 LLM provider modal. `const { baseUrl, apiKey, models } = await openaiConfig()`
import saveform from "saveform"; // @1 to persist form data. `saveform("#form-to-persist")`
```

Test front-end apps with Playwright (prefer CDP on localhost:9222) using .evaluate(), view_image / read tool for screenshots.

## Tmux

Use tmux outside the sandbox for interactive REPLs, TUIs; long running commands (servers, codex, sub-agents); persistent tasks

```bash
tmux new-session -d -s $SESSION 'uv run --with pandas,httpx,lxml python -iqu'
tmux pipe-pane -t $SESSION -o "cat >> /tmp/$LOG"
tmux send-keys -t $SESSION 'print(1 + 2)' C-m
cat /tmp/$LOG
tmux capture-pane -p -t $SESSION -S -5
```

## References

Under ../custom-prompts/

- git-commit.md: commit guidelines
