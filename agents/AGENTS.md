For non-trivial tasks, define what done means. Verify before concluding.
Test what you need - permissions, credentials, network/write access - and surface blockers early.
My directives may be a draft of my real need. Infer my intent and reframe, if clearly required, VISIBLY.

Prefer:
uv, uv run, uv pip, uvx (avoid python/pip)
gws > gcloud > API
duckdb, sqlite3 > pandas, qsv, csvq
jaq > jq
just > bash scripts > npm
fd . PATH --max-depth 3 --type f (over find)
ug -il -Z1 --bool --files '"phrase" (x|y|z) -deprecated' "$DIR" (over rg, grep)
See tooldocs/README.md for more tools

Prefix supported, high-output commands with `rtk` to reduce tokens, e.g. `rtk read`, `rtk rg`, `rtk git status`, `rtk pytest -q`.
Skip `rtk` for already-bounded/exact output; use `rtk bash -lc '…'` for shell constructs.

Home ~ = /home/sanand/ = /home/vscode/ (symlinked).

For slow/large tasks, start small, test/benchmark a sample, optimize, THEN scale.
Increase timeouts proactively for commands will likely succeed.
