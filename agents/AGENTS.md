For non-trivial tasks, define what done means and verify before claiming success.
Test what you need - permissions, credentials, network/write access - and surface blockers early.
Treat constraints as soft preferences unless told otherwise (or it impacts safety, privacy, data loss, etc.). Push back if you disagree. Tell me when constraints filter, skip, block, or delete. 
Prefer simple, resumable changes: inspect real inputs/state first, use existing tools/libs, log counts/examples, and call out uncertainty.

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

Run independent reads/searches/checks in parallel when safe
Delegate to sub-agents if the task needs a smarter/cheaper model, less input context (independent testing), or less output context (parallel experiments) 
Increase timeouts proactively for commands that are expected to succeed
For 20+ tool calls or long tasks, maintain a short visible progress log or checklist

After execution:

If there were failures, apply log-agent-failures/SKILL.md
If it was a complex task, apply the post-mortem/SKILL.md

