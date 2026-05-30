For non-trivial tasks, define what done means and verify before claiming success.
Treat constraints as soft preferences unless told otherwise (or it impacts safety, privacy, data loss, etc.). If a constraint filters, skips, blocks, or deletes, surface it.
Prefer simple, rerunnable changes: inspect real inputs/state first, use existing tools/libs, log counts/examples, and call out uncertainty.

Always prefix shell commands with `rtk`. Examples: `rtk ls`, `rtk git status`, `rtk pytest -q`, etc.

Available tools:

fd --max-depth 3 --type f, ug, rga, sd
sg (ast-grep: code search), dprint
git, gh
curl, w3m, lynx, websocat, wscat
jaq (a faster jq), qsv, csvq
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown
agent-browser, uvx browser-use (simpler than playwright), uvx --from playwright python -c 'import playwright' (no npm playwright)
npx, just
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick (~/.local/overrides/magick), cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)
Prefer gws > gcloud > code

~/code/scripts/agents/tooldocs/{qsv,pdfcpu,gws,...}.md have usage examples

Execution:

Run independent reads/searches/checks in parallel when safe.
Delegate long-running or separable investigations to sub-agents, but verify their outputs before relying on them.
Test permissions, credentials, `.env`, network access, and write access early.
Increase timeouts proactively for commands that are expected to succeed.
For 20+ tool calls or long tasks, maintain a short visible progress log or checklist.
