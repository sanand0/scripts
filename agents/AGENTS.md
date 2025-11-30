Available tools:

fd, find
rg, ug, grep
git, gh
curl, w3m, lynx, websocat, wscat
jaq (faster than jq), qsv, csvq, csvkit
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, ...
pdfcpu, qpdf, pandoc
duckdb, sqlite3, psql, usql
magick, pdftoppm, imgcat, cwebp, ffmpeg

/home/sanand/code/scripts/agents/tooldocs/$TOOL.md has usage examples.
tealdeer $TOOL for quick reference.

<!-- skills -->

Refer relevant SKILL.md under /home/sanand/code/scripts/agents:

- [code](code/SKILL.md): ALWAYS follow this style when writing Python / JavaScript code
- [devtools](devtools/SKILL.md): Use CDP at localhost:9222 to test/debug websites, automate browser tasks
- [llm](llm/SKILL.md): Call LLM via CLI for transcription, vision, image generation, piping prompts, ...
- [npm-packages](npm-packages/SKILL.md): Conventions for package.json, README.md, coding & testing styles
- [pdf](pdf/SKILL.md): Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF form or programmatically process, generate, or analyze PDF documents at scale.
- [vitest-dom](vitest-dom/SKILL.md): Fast, lightweight testing for front-end apps. Uses vitest + jsdom instead to avoid heavy playwright.
- [webapp-testing](webapp-testing/SKILL.md): Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.

<!-- /skills -->
