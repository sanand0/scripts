For non-trivial tasks, define what done means and verify before claiming success.
Test what you need - permissions, credentials, network/write access - and surface blockers early.
Treat constraints as soft preferences unless told otherwise (or it impacts safety, privacy, data loss, etc.). Push back if you disagree. Tell me when constraints filter, skip, block, or delete.

Prefix supported, high-output commands with `rtk`, e.g. `rtk read`, `rtk rg`, `rtk git status`, `rtk pytest -q`.
Skip `rtk` for already-bounded/exact output; use `rtk bash -lc '…'` for builtins, pipes, redirects, loops, compound `find`, or tricky quoting.

Home ~ = /home/sanand/ or /home/vscode/ (symlinked).
Paths may contain spaces / special characters.

Available tools:

fd . PATH --max-depth 3 --type f (not `fd PATH`), ug -n PATTERN PATH --glob '!node_modules/**', rga, sd
sg (ast-grep: code search), dprint
git, gh (check repo first; `git log --follow` only one path)
curl, w3m, lynx, websocat, wscat
jaq (faster jq; quote filters; use `? // empty` for nullable fields; validate JSONL line-by-line), qsv, csvq
uv, uv run, uv pip, uvx (avoid python/pip)
uvx ruff, uvx yt-dlp, uvx markitdown
agent-browser (use stable tab IDs like t45; inspect visible DOM before clicking), uvx browser-use, uvx --from playwright python -c 'import playwright' (no npm playwright)
npx, just
duckdb, sqlite3
pdfcpu, qpdf, pdftoppm, pdfplumber, pandoc
magick (~/.local/overrides/magick), cwebp, ffmpeg, melt (avoid imgcat, prefer view_image / read tool)
Prefer gws > gcloud > API

~/code/scripts/agents/tooldocs/{qsv,pdfcpu,gws,...}.md have usage examples

Execution:

For slow/large tasks, start small, verify/benchmark a sample, optimize, THEN scale
Prefer PARALLEL reads/searches/checks when safe
Delegate to sub-agents for smarter/cheaper models, less input/output context accumulation, parallel/independent testing
Increase timeouts proactively for commands will likely succeed
For 20+ tool calls or long tasks, maintain a short visible progress log or checklist

After execution:

Report files/items skipped when sampling/chunking
If a tool/command fails UNEXPECTEDLY _and_ this may reveal a reusable pattern, log via log-tool-failure skill.
If it was a complex task, apply the post-mortem/SKILL.md
