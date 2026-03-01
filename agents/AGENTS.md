Available tools:

fd, find
rg, ug, grep
git, gh
curl, w3m, lynx, websocat, wscat
jaq (a faster jq), qsv, csvq
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, ...
sg (ast-grep)
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick, cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)

/home/sanand/code/scripts/agents/tooldocs/$TOOL.md has usage examples - especially qsv, pdfcpu.

If prompt*.md is updated, the user might be editing it. Ignore it.

Suggestions:

Run multiple independent reads in parallel.
For 20+ tool calls, maintain update_plan throughout.
For long-running commands/tests, delegate via sub-agents and report checkpoints.
If blocked by permissions, ask me concise choices.
