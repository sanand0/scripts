Available tools:

fd, find
rg, ug, grep
git, gh
curl, w3m, lynx, websocat, wscat
jq, csvq, csvkit
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff|yt-dlp|markitdown|...
qpdf, pandoc
duckdb, sqlite3, psql
magick, cwebp, ffmpeg

<!-- skills -->

Refer relevant SKILL.md under /home/sanand/code/scripts/agents:

- [code](code/SKILL.md): ALWAYS follow this style when writing Python / JavaScript code
- [devtools](devtools/SKILL.md): Use CDP at localhost:9222 to test/debug web apps and automate browser tasks
- [llm](llm/SKILL.md): Delegate LLM calls, e.g. `llm --attachment audio.opus --model gemini-2.5-flash --system 'Translate' 'Use German'`
- [npm-packages](npm-packages/SKILL.md): Conventions for package.json, README.md, coding & testing styles
- [pdf](pdf/SKILL.md): Comprehensive PDF manipulation toolkit for extracting text and tables, creating new PDFs, merging/splitting documents, and handling forms. When Claude needs to fill in a PDF form or programmatically process, generate, or analyze PDF documents at scale.
- [vitest-dom](vitest-dom/SKILL.md): Fast, lightweight testing for front-end apps. Uses vitest + jsdom instead to avoid heavy playwright.
- [webapp-testing](webapp-testing/SKILL.md): Toolkit for interacting with and testing local web applications using Playwright. Supports verifying frontend functionality, debugging UI behavior, capturing browser screenshots, and viewing browser logs.

<!-- /skills -->
