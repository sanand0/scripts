---
name: code
description: ALWAYS use this style when coding Python / JavaScript
---

Coding style

- Functions over classes
- Type hints and single-line docstrings
- Use config.{json,toml} if config > 30 lines?

Python style

- Only use `uv run`. Not `python` or `python3`
- Unless `pyproject.toml` is present, add dependencies to script
  ```
  #!/usr/bin/env -S uv run --script
  # /// script
  # requires-python = ">=3.12"
  # dependencies = ["scipy>=1.10", "httpx"]
  # ///
  ```

Python libs:

`typer` over `argparse`
`httpx` over `requests`
`orjson` over `json`
`lxml` over `xml`
`tenacity` for retries

HTML/CSS/JS style:

- Prefer Bootstrap. Minimize custom CSS
- Use hyphenated HTML class/ID names (id="user-id" not id="userId")
- Use ESM2022+. No TypeScript. But enable `// @ts-check`
- Use modern browser APIs
- Show loading status while awaiting fetch()
- Trap errors at the top rather than every level. Render errors for user
- Use helpers: `const $ = (s, el = document) => el.querySelector(s);`

Prefer popular, modern, minimal, fast libraries
Don't code when good libs exists

JS libs:

Use `npm view package-name readme` for docs

Use importmaps:

<script type="importmap">{ "imports": { "package-name": "https://cdn.jsdelivr.net/npm/package-name@version" } }</script>

```js
import { network } from "@gramex/network"; // @2 for force-directed layouts
import { dmy, mdy, wdmy, num, pc, ... } from "@gramex/ui@0.3/dist/format.js";
import { asyncLLM } from "asyncllm"; // @2 streams LLM responses. `for await (const { content, error } of asyncLLM(baseURL, { method: "POST", body: JSON.stringify({...}), headers: { Authorization: `Bearer ${apiKey}` } }`
import { bootstrapAlert } from "bootstrap-alert"; // @1 for notifications. `bootstrapAlert({ title: "Success", body: "Toast message", color: "success" })`
import { openaiConfig } from "bootstrap-llm-provider"; // @1 LLM provider modal. `const { baseUrl, apiKey, models } = await openaiConfig()`
import { csvFormat, csvParse } from "d3-dsv"; // @3/+esm parse CSV
import * as d3 from "d3"; // @7/+esm for visualizations
import hljs from "highlight.js"; // @11/+esm highlight Markdown code; link CDN CSS
import { html, render } from "lit-html"; // @3/+esm for DOM updates
import { unsafeHTML } from "lit-html@3/directives/unsafe-html.js";
import { marked } from "marked@16/+esm"; // render Markdown
import { parse } from "partial-json@0.1/+esm"; // parse streamed JSON. `const { key } = parse('{"key":"v')`
import saveform from "saveform@1"; //  to persist form data. `saveform("#form-to-persist")`
```

Test with `npm test` and `uvx pytest` as appropriate

Lint with `npm run lint`. Else use `dprint fmt -c https://raw.githubusercontent.com/sanand0/scripts/refs/heads/main/dprint.jsonc`.
