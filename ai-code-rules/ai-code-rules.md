Write readable code

- Keep happy path linear and obvious
- Name readably
- Name intermediates?
- Comment design choices?

Keep code short

- Use early returns
- Refactor into loops, higher-order functions
- Skip error handling unless required
- Web apps: trap errors only at top level. Render for user

Change existing code minimally

- Retain existing comments
- Follow existing style

Tests first if tests exists (or new code)

- Write failing tests/features
- Keep tests fast. Small fixtures; deterministic seeds

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

HTML/CSS/JS style:

- Use ESM2022+. No TypeScript
- Enable type checking for JS files
- Use modern browser APIs
- Use hyphenated HTML class/ID names (id="user-id" not id="userId")
- Show loading spinners while awaiting fetch()
- Prefer Bootstrap. Minimize custom CSS
- Use this helper: `const $ = (s, el = document) => el.querySelector(s);`

Prefer popular, modern, minimal, fast libraries
Don't code when good libs exists

Python libs:

`typer` over `argparse`
`httpx` over `requests`
`orjson` over `json`
`lxml` over `xml`
`tenacity` for retries

JS libs:

Use `npm view package-name readme` for docs

```js
import { render, html } from "https://cdn.jsdelivr.net/npm/lit-html@3/+esm"; // for DOM updates
import { unsafeHTML } from "https://cdn.jsdelivr.net/npm/lit-html@3/directives/unsafe-html.js";
import { marked } from "https://cdn.jsdelivr.net/npm/marked@16/+esm"; // render Markdown
import hljs from "https://cdn.jsdelivr.net/npm/highlight.js@11/+esm"; // highlight Markdown code; link CDN CSS
import { num, num0, num2, pc, pc0, pc1, dmy, mdy, dm, md, wdmy } from "https://cdn.jsdelivr.net/npm/@gramex/ui@0.3/dist/format.js"; // number & date formatting
import { bootstrapAlert } from "https://cdn.jsdelivr.net/npm/bootstrap-alert@1"; // for notifications. `bootstrapAlert({ title: "Success", body: "Toast message", color: "success" })`
import saveform from "https://cdn.jsdelivr.net/npm/saveform@1"; //  to persist form data. `saveform("#form-to-persist")`
import { openaiConfig } from "https://cdn.jsdelivr.net/npm/bootstrap-llm-provider@1"; // LLM provider modal. `const { baseUrl, apiKey, models } = await openaiConfig()`
import { asyncLLM } from "https://cdn.jsdelivr.net/npm/asyncllm@2"; // streams LLM responses. `for await (const { content, error } of asyncLLM(baseURL, { method: "POST", body: JSON.stringify({...}), headers: { Authorization: `Bearer ${apiKey}` } }`
import { parse } from "https://cdn.jsdelivr.net/npm/partial-json@0.1/+esm"; // parse streamed JSON. `const { key } = parse('{"key":"v')`
import { csvParse, csvFormat } from "https://cdn.jsdelivr.net/npm/d3-dsv@3/+esm"; // parse CSV
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm"; // for visualizations
import { network } from "https://cdn.jsdelivr.net/npm/@gramex/network@2"; // for force-directed layouts
```

Available tools:
fd / find
rg / grep
uvx yt-dlp
uvx markitdown (PDF to Markdown)
curl, w3m, lynx, jq, csvq, git, gh, pandoc, pdftotext, qpdf, csvkit, rclone, duckdb, sqlite3, psql, magick, cwebp, ffmpeg

Test with `npm test` and `uvx pytest` as appropriate

Lint with `npm run lint`. Else:

- PY: `uvx ruff check; uvx ruff format --line-length 100`
- JS, MD: `npx -y prettier@3.5 --print-width=120 '**/*.js' '**/*.md'` (skip HTML)

On completion, suggest further improvements
