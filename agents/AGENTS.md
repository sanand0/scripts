Always prefix shell commands with `rtk`. Examples: `rtk git status`, `rtk pytest -q`, etc.

Available tools:

fd, ug, rga, sd
sg (ast-grep: code search), dprint
git, gh
curl, w3m, lynx, websocat, wscat
jaq (a faster jq), qsv, csvq
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, ...
agent-browser (CLI, simpler than playwright, but `npm install -g playwright` exists)
npx, just
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick (~/.local/overrides/magick), cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)
gws (Google Workspace CLI), gcloud, aws

~/code/scripts/agents/tooldocs/{qsv,pdfcpu,gws,...}.md have usage examples.

Suggestions:

When possible, run in parallel for speed and token efficiency: read, tools, sub-agents, ...
Delegate long-running commands/tests to sub-agents and report checkpoints.
If blocked by permissions, ask me concise choices.
When done, suggest what & how to verify edge cases and/or suggest high-impact improvements.
