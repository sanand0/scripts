- Name readably; keep happy path linear. Optimize for clarity; shorten after that.
- For new code, or if tests exist:
  - Start by writing tests: 1–2 failing tests/feature.
  - Keep tests fast; prefer small fixtures and deterministic seeds.
- Minimize lines of production code. Tests and logging code are exempt from "minimize".
- Reuse code with loops, functions, and libraries.
- Prefer popular, modern, minimal, fast libraries; avoid hand-rolling when a stable lib exists.
- Name intermediate conditions/values.
- Keep the "happy path" obvious.
- Use early returns.
- Handle only predictable errors (network/input/timeouts). In web/CLI, show a user-visible message; otherwise avoid defensive code.
- Prefer functions over classes.
- Keep config > 30 lines in config files (config.json, config.toml).
- Keep code files under ~500 lines. Split logically.
- Minimize code changes. Retain comments that explain the code.
- Follow existing code & comment style.
- Include type hints and single-line docstrings.
- On completion, suggest further improvements.

Python:

- Use `uv run` not `python` or `python3`.
- If `pyproject.toml` is missing, add dependencies as inline script metadata like this:
  ```
  #!/usr/bin/env -S uv run --script
  # /// script
  # requires-python = ">=3.12"
  # dependencies = ["scipy>=1.10", "httpx"]
  # ///
  ```
- Prefer `typer` over `argparse`, `httpx` over `requests`, `orjson` over `json`, `lxml` over `xml`, `tenacity` for retries

HTML/CSS/JS:

- Use ESM2022+. No TypeScript.
- Enable type checking for JS files.
- Use modern browser APIs (e.g. `navigator.clipboard.writeText`)
- Use hyphenated HTML class/ID names (id="user-id" not id="userId").
- Show a loading indicator while awaiting fetch().
- Follow existing CSS framework; if none, use Bootstrap (include CDN CSS) with Bootstrap class styling, minimizing custom CSS.

Preferred libraries: (for docs, run `npm view package-name readme`)

```js
import { render, html } from "https://cdn.jsdelivr.net/npm/lit-html@3/+esm"; // for DOM updates
import { unsafeHTML } from "https://cdn.jsdelivr.net/npm/lit-html@3/directives/unsafe-html.js";
import { marked } from "https://cdn.jsdelivr.net/npm/marked@16/+esm"; // render Markdown
import hljs from "https://cdn.jsdelivr.net/npm/highlight.js@11/+esm"; // highlight Markdown code; link CDN CSS
import { num, num0, num2, pc, pc0, pc1, dmy, mdy, dm, md, wdmy } from "https://cdn.jsdelivr.net/npm/@gramex/ui@0.3/dist/format.js"; // number & date formatting
import { bootstrapAlert } from "https://cdn.jsdelivr.net/npm/bootstrap-alert@1"; // for notifications. `bootstrapAlert({ title: "Success", body: "Toast message", color: "success" })`
import saveform from "https://cdn.jsdelivr.net/npm/saveform@1.2"; //  to persist form data. `saveform("#form-to-persist")`
import { openaiConfig } from "https://cdn.jsdelivr.net/npm/bootstrap-llm-provider@1"; // LLM provider modal. `const { baseUrl, apiKey, models } = await openaiConfig()`
import { asyncLLM } from "https://cdn.jsdelivr.net/npm/asyncllm@2"; // streams LLM responses. `for await (const { content, error } of asyncLLM(baseURL, { method: "POST", body: JSON.stringify({...}), headers: { Authorization: `Bearer ${apiKey}` } }`
import { parse } from "https://cdn.jsdelivr.net/npm/partial-json@0.1/+esm"; // parse streamed JSON. `const { key } = parse('{"key":"v')`
import { csvParse, csvFormat } from "https://cdn.jsdelivr.net/npm/d3-dsv@3/+esm"; // parse CSV
import { fileOpen, directoryOpen, fileSave } from 'https://cdn.jsdelivr.net/npm/browser-fs-access/+esm'; // FS access ponyfill. `await fileSave(blob, { fileName })`
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm"; // for visualizations
import { network } from "https://cdn.jsdelivr.net/npm/@gramex/network@2"; // for force-directed layouts
import { ky } from "https://cdn.jsdelivr.net/npm/ky@1/+esm"; // for fetch with retries / progress
```

Use helpers if functionality is needed 3+ times:

```js
const $ = (s, el = document) => el.querySelector(s);
function on(el, event, selector, handler) { el.addEventListener(event, (e) => { if (e.target.closest(selector)) handler(e); }); }
async function fetchJSON(input, init) { const r = await fetch(input, init); if (!r.ok) throw new Error(`${r.status} ${r.statusText}`); return r.json(); }
const query = (params) => new URLSearchParams(params).toString();
```

LLM models: Prefer gpt-5-mini for balance, gpt-5-nano for cost, gpt-4.1-nano for speed.
OpenAI /chat/completions supports `{ response_format: { type: "json_schema", json_schema: { name: "...", schema: { ... } } } }`.

Tools: Prefer `fd` over `find`, `rg` over `grep`, `uvx yt-dlp` for YouTube, `uvx markitdown` for PDF to Markdown
Also: `jq`, `duckdb`, `gh`, `ffmpeg`, `magick`,

Test with `npm test` and `uvx pytest` as appropriate.

Lint with `npm run lint` if available, else:

- PY: `uvx ruff format --line-length 100`
- JS, MD: `npx -y prettier@3.5 --print-width=120 '**/*.js' '**/*.md'`
- HTML: `npx -y js-beautify@1 '**/*.html' --type html --replace --indent-size 2 --max-preserve-newlines 1 --end-with-newline`

References:

- To [test browser JS apps](test-browser-js-apps.md) read @test-browser-js-apps.md
- For [npm-packages](npm-packages.md) read @npm-packages.md
