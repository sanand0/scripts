Available tools:

fd, find
rg, ug, grep
sg (ast-grep: code search), dprint
git, gh
curl, w3m, lynx, websocat, wscat
jaq (a faster jq), qsv, csvq
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, ...
uvx rodney, playwright (browser automation)
npx, just
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick, cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)
gws (Google Workspace CLI), gcloud, aws

~/code/scripts/agents/tooldocs/{qsv,pdfcpu,gws,...}.md have usage examples.

Suggestions:

When possible, run in parallel: read, tools, sub-agents, ...
For 20+ tool calls, maintain update_plan throughout.
Delegate long-running commands/tests to sub-agents and report checkpoints.
If blocked by permissions, ask me concise choices.
If sandbox/config gets in the way, use /permissions and /debug-config early.
When done, suggest what & how to verify edge cases and/or suggest high-impact improvements.
