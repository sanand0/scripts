Available tools:

fd, find
rg, ug, grep
git, gh
curl, w3m, lynx, websocat, wscat
jaq (faster than jq), qsv (), csvq, csvkit
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, ...
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pandoc
magick, cwebp, ffmpeg (avoid imgcat, prefer view_image / read tool)

/home/sanand/code/scripts/agents/tooldocs/$TOOL.md has usage examples - especially qsv, pdfcpu.

Increase timeouts proactively for longer tasks if you expect them to succeed.

<!-- skills -->

Refer relevant SKILL.md under /home/sanand/code/scripts/agents:

- [cloudflare](cloudflare/SKILL.md): For CloudFlare development, deployment, e.g. Python CloudFlare Workers
- [code](code/SKILL.md): ALWAYS follow this style when writing Python / JavaScript code
- [demos](demos/SKILL.md): Use when creating demos or POCs
- [design](design/SKILL.md): ALWAYS follow this design guide for any front-end work
- [devtools](devtools/SKILL.md): Use CDP at localhost:9222 to test/debug websites, automate browser tasks
- [llm](llm/SKILL.md): Call LLM via CLI for transcription, vision, speech/image generation, piping prompts, sub-agents, ...
- [npm-packages](npm-packages/SKILL.md): Conventions for package.json, README.md, coding & testing styles
- [pdf](pdf/SKILL.md): Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF form or programmatically process, generate, or analyze PDF documents at scale.
- [plan](plan/SKILL.md): How to plan & break down large, complex tasks
- [vitest-dom](vitest-dom/SKILL.md): Use vitest + jsdom for fast, lightweight unit tests for front-end apps
- [webapp-testing](webapp-testing/SKILL.md): Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.

<!-- /skills -->
