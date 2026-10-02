For non-trivial tasks, define what done means. Verify before concluding.
Test what you need - permissions, credentials, network/write access - and surface blockers early.
Treat constraints as soft preferences unless told otherwise (or it impacts safety, privacy, data loss, etc.). Push back if you disagree. Tell me when constraints filter, skip, block, or delete.

Prefer:
uv, uv run, uv pip, uvx (avoid python/pip)
gws > gcloud > API
duckdb, sqlite3 > pandas, qsv, csvq
jaq > jq (quote filters; use `? // empty` for nullable fields; validate JSONL line-by-line)
just > bash scripts > npm
fd . PATH --max-depth 3 --type f (over find)
ug -il -Z1 --bool --files '"phrase" (x|y|z) -deprecated' "$DIR" (over rg, grep)
See tooldocs/README.md for more tools

Prefix supported, high-output commands with `rtk` to reduce tokens, e.g. `rtk read`, `rtk rg`, `rtk git status`, `rtk pytest -q`.
Skip `rtk` for already-bounded/exact output; use `rtk bash -lc '…'` for shell constructs.

Home ~ = /home/sanand/ or /home/vscode/ (symlinked).
Paths may contain spaces / special characters.

Execution:

For slow/large tasks, start small, test/benchmark a sample, optimize, THEN scale.
Prefer sub-agents for experiments, benchmarks, research, etc. to avoid bloating the main thread.
Increase timeouts proactively for commands will likely succeed.

After execution:

Report files/items skipped when sampling/chunking
