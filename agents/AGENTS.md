Always prefix shell commands with `rtk`. Examples: `rtk ls`, `rtk git status`, `rtk pytest -q`, etc.

Available tools:

fd, ug, rga, sd
sg (ast-grep: code search), dprint
git, gh
curl, w3m, lynx, websocat, wscat
jaq (a faster jq), qsv, csvq
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown, uvx browser-use, ...
agent-browser, uvx browser-use (simpler CLIs than `import playwright` code)
npx, just
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick (~/.local/overrides/magick), cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)
gws (Google Workspace CLI), gcloud, aws

~/code/scripts/agents/tooldocs/{qsv,pdfcpu,gws,...}.md have usage examples.

Suggestions:

When possible, run in parallel for speed and token efficiency.
Delegate long-running tasks to sub-agents and report checkpoints.
Test permissions and ask for help EARLY.
