# Preferences for CLI scripts

<!-- https://claude.ai/chat/41fb6c3d-014d-461b-ac37-a493af934ac7 -->

Prefer these defaults to new scripts unless overridden.

## Conventions (always)

- Single file. For Python scripts: `#!/usr/bin/env -S uv run --script` shebang, deps in PEP 723 `# /// script` header.
- `typer` for CLIs. `add_completion=False`. Module docstring becomes `--help`.
- Target ≤350 lines. No test scripts unless requested.
- Fail fast on first error. Do not wrap defensively.
- Cache: read-only API responses and state (tokens, cursors, per-account data) under `~/.cache/sanand-scripts/<tool>/`. For multi-account tools, use `~/.cache/sanand-scripts/<tool>/<email>/` and verify the auth token matches `--account` before any action.

<!-- #TODO Which tools use ~/.config/ that's not under sanand-scripts? Plan to migrate. -->

## Standard flags worth offering (in roughly this order of likely use)

Frequently used in practice — build these well:

- `--glob PATTERN` and `--name SUBSTR` for filtering inputs.
- `--since` / `--until` accepting `7d`, `2 months ago`, or ISO.
- `--limit / -n`, default ~20–100.
- `--dry-run` for any script that writes, deletes, or hits paid APIs.
- `--format text|json|jsonl` with auto = text. Streamed, never buffered.
- `--color=auto|always|never` for text output. Default to `auto`: color if stdout is a TTY, no color if piped.
- `--fields a,b,c` / `--fields "a b c"` for column selection — both separators parse (see `gmail.py`).
- `--search` with three modes: plain → fast case-insensitive substring; `/regex/` → case-sensitive regex; `/regex/i` → case-insensitive regex (see `agentlog.py`).

## Output

- Stream results as they arrive. Target: first row <1s even with 10k+ inputs. Page-stream paginated APIs.
- stdout is machine-parseable: TSV by default, JSONL with `--format jsonl`. Status, progress, and warnings go to stderr.
- Include a 3–4 line `Examples:` block in `--help`, with at least one piped-to-`xclip`/`moor`/`jaq` example.
- Markdown output for human artefacts (transcripts, session logs); TSV/JSONL for tabular.
- README gets one bullet per script + sub-bullets for daily/weekly invocations the author can run without thinking.

## Performance and idempotence

- Cache aggressively: 1h TTL for live data, 7d for slow-changing reference data. `--refresh` forces, `--no-cache` bypasses.
- Re-runs must be cheap: skip if output already exists and matches source (mtime, size, checksum, or marker section). Plan for re-runs against expanding date ranges.
- `tqdm` (or equivalent) on any loop processing >50 items.

## Things to push back on

The author over-specifies on first ask and refactors later. When the prompt includes these, ask whether v1 should defer them:

- Elaborate scoring formulas with per-field weights (`githubscore`-style).
- Custom auth flows when `gws`, `google_oauth.py`, or an existing connector covers the case.
- Multi-mode subcommands when one good default + `--format` covers real use.
- Edge-case escape hatches added in response to a single bug.

## Things to volunteer when unasked

- Extract a shared module (`sanand_scripts/`) once two scripts share an idiom: `day_start`, `Account.verify`, `Cache`, `format_columns`, `parse_search_pattern`, `auto_format`. Several scripts reimplement these.
- `--config FILE` or env-var defaults for parameters typed identically every run (e.g. `discourse.py --host … --category-id 34`).
- `--state FILE` for resumable batch jobs, since interrupts on long runs are common.
- A run-log (`~/.cache/sanand-scripts/<tool>/run.jsonl` with args, duration, exit code) — feeds future "what did I run last week" questions.
- Golden-file tests under `tests/` for tools producing reproducible output. The author skips these; they pay back by the third refactor.

## Workflow signals to recognise

- Design happens in `prompts/<script>.md`, not in the script. Treat that file as the spec; preserve its structure when iterating.
- Recurring edit verbs: "simplify", "remove legacy code paths", "more compact", "minimal change". Default to the smaller path; don't preserve dead options.
- Every prompt ends with some variant of "Plan first. Test on a small input. Then execute." Do this even when not asked.
- "Run for ~5 examples and iterate" is the author's preferred test loop. Pick diverse examples, not adjacent ones.
- The author types `--help` and `--describe | jaq .` to introspect tools. Make their output good.
