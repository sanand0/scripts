---
name: code
description: ALWAYS follow this style when writing Python / JavaScript code
---

Coding style

- Prefer libraries to writing code. Prefer popular, modern, minimal, fast libraries exist
- Write readable code. Keep happy path linear and obvious. Begin by writing the flow, then fill in code. Name intuitively
- Keep code short. Skip error handling unless required. Use early returns
- Change existing code minimally. Retain existing comments. Follow existing style
- Add failing tests first if tests exists (or in new code). Keep tests fast
- Use type hints and single-line docstrings
- Cache LLM/API/HTTP requests in .cache/ when looping

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

`typer` not `argparse`
`httpx` not `requests`
`orjson` not `json`
`lxml` not `xml`
`tenacity` for retries
`pytest`

Preferred JS style:

- Bootstrap. Minimize custom CSS
- Hyphenated HTML class/ID names (id="user-id" not id="userId")
- ESM2022+. No TypeScript. But enable `// @ts-check`
- Modern browser APIs
- Loading indicator while awaiting fetch()
- Error handling only at top level. Render errors for user
- Helpers: `const $ = (s, el = document) => el.querySelector(s); $("#id")...`
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

Use `npm view package-name readme` for docs
Read https://context7.com/org/repo/llms.txt for docs about https://github.com/org/repo
