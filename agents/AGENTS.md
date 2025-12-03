Available tools:

fd, find
rg, ug, grep
git, gh
curl, w3m, lynx, websocat, wscat
jaq (faster than jq), qsv, csvq, csvkit
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, ...
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pandoc
magick, cwebp, ffmpeg

$HOME/code/scripts/agents/tooldocs/$TOOL.md has usage examples.
tealdeer $TOOL for quick reference.

Avoid tools:

imgcat: prefer view_image / read tool

<!-- skills -->

Refer relevant SKILL.md under $HOME/code/scripts/agents:

- [code](code/SKILL.md): ALWAYS follow this style when writing Python / JavaScript code
- [demos](demos/SKILL.md): Use when creating demos or POCs
- [design](design/SKILL.md): ALWAYS follow this design guide for any front-end work
- [devtools](devtools/SKILL.md): Use CDP at localhost:9222 to test/debug websites, automate browser tasks
- [llm](llm/SKILL.md): Call LLM via CLI for transcription, vision, image generation, piping prompts, ...
- [npm-packages](npm-packages/SKILL.md): Conventions for package.json, README.md, coding & testing styles
- [plan](plan/SKILL.md): How to plan & break down large, complex tasks
- [pdf](pdf/SKILL.md): Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF form or programmatically process, generate, or analyze PDF documents at scale.
- [webapp-testing](webapp-testing/SKILL.md): Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.

<!-- /skills -->
