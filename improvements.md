# Repo Script Improvements

## Scope

This review covers the repo's first-party scripts with a usability/usefulness lens:

- top-level shell, Python, Perl, Deno, jq, and JS utilities
- `generate/`, `services/`, `pdbhook/`, `tests/`
- first-party helper scripts under `agents/.system/`, `agents/devtools/`, and `agents/webapp-testing/`

Excluded from this document:

- vendored code under `agents/devtools/node_modules/`
- static demo assets under `agents/demos/assets/`

## Highest-Leverage Improvements

### 1. Replace hard-coded personal paths with args/env/config

This is the single biggest portability issue in the repo.

- `askwin:21` hard-codes `/home/sanand/code/scripts` and `/home/sanand/apps/llm/.venv/bin`.
- `daydream:43-49,151` hard-codes `~/Dropbox/notes/daydream.jsonl` and `~/code/til-live/daydream.jsonl`.
- `recall:25-36` hard-codes note roots and assumes at least one matching file exists.
- `consolidate_transcripts.py:141-156` hard-codes source/output directories.
- `codexerrors.py:161-163` changes directory to `/home/sanand/.codex/sessions/`, which makes `--log-dir` misleading.
- `agents/devtools/check-page.py:41-49` and `agents/devtools/check-page.js:31-42` hard-code both the target URL and screenshot path.
- `agents/webapp-testing/examples/console_logging.py:31-35` and `static_html_automation.py:17-29` hard-code `/mnt/user-data/outputs/...`.

Recommended change:

- introduce a shared config convention: CLI flag first, then env var, then sane default
- prefer `Path.home()`, XDG dirs, or script-relative paths over author-specific absolute paths
- add `--config` or per-script `--root/--out/--notes-dir/--url` flags for anything stateful

### 2. Standardize the CLI contract across the repo

The repo mixes high-quality CLIs (`claudelog`, `gmail.py`, `rename_receipts.py`) with scripts that have no help, no structured flags, or hand-rolled parsing.

Missing or weak CLI surfaces show up in:

- `ask`, `askwin`, `daydream`, `git-uncommitted`, `update-files`, `agents/agents_gen.sh`
- `githubscore.py`, `slide.py`, `viz.py`, `mcpserver.py`
- jq filters like `tsv.jq`, `whatsappthread.jq`, `jsonpaths.jq` that only document usage in comments

Recommended baseline for all user-facing scripts:

- `--help` with one-line purpose, 2-3 examples, and dependency notes
- consistent `--json/--jsonl/--tsv` output where results are tabular
- `--dry-run` for destructive/network-heavy actions
- explicit exit codes and clear error messages
- `--version` or at least stable script metadata for tools that may be automated

### 3. Add dependency preflight and better failure messages

Many scripts assume local tools are installed and fail opaquely.

- `ask:12-45` assumes `ffmpeg`, `llm`, `fzf`, `xclip`.
- `askwin:19-33` assumes `mise`, `xdotool`, terminal integration, and X11 paste semantics.
- `rofi-chrome-tabs.sh:4-19` assumes `mise`, `curl`, `jq`, and a CDP browser on port `9222`.
- `copy-to-markdown.sh:10-22` assumes clipboard HTML is present and that `deno` is available through `mise`.
- `audiosync.py:21-25,66-85` assumes `ffprobe` and `ffmpeg`.
- `services/setup.sh:17-49` assumes user-systemd is available.

Recommended change:

- add a small shared `require_cmd` helper for shell scripts and a Python equivalent
- fail with "missing X; install via Y" instead of a raw subprocess error
- expose a `--check` mode for environment-sensitive scripts

### 4. Make more scripts composable in pipelines and automation

Several tools are useful interactively but awkward to compose because they only emit human text.

Best candidates for machine-readable output:

- `codexlist`, `copilotlist`, `claudelog ls/resolve`, `codexerrors.py`, `codextools.py`, `codextags.py`
- `git-uncommitted`, `githubscore.py`, `daydream`, `recall`
- `services/setup.sh` and `dev.test.sh`

Recommended change:

- default to human-readable text, but add `--json`/`--jsonl` consistently
- keep field names stable so the tools can be chained
- add `--quiet` and `--no-header` where TSV/CSV-like output is used

### 5. Build shared primitives instead of repeating ad hoc implementations

There are clear repeated domains in the repo:

- clipboard handling: `ask`, `copy-to-markdown.sh`, `rofi-clip.sh`, `rofi-files.sh`, `clean_markdown.py`
- log inspection: `codexlist`, `copilotlist`, `claudelog`, `codexerrors.py`, `codextools.py`, `codextags.py`, `codexlog.jq`, `copilotlog.jq`, `opencodelog.jq`
- browser/CDP automation: `q`, `rofi-chrome-tabs.sh`, `agents/devtools/check-page.py`, `agents/devtools/check-page.js`

Recommended change:

- factor clipboard access into one shared helper with X11/Wayland/macOS support
- converge log tools on a shared session-discovery/filtering library
- move site-specific browser selectors into config instead of embedding them inline

### 6. Add smoke tests for the scripts that users depend on most

Coverage is good for `codextags.py`, but most other scripts are untested.

High-value smoke-test targets:

- `ask` / `askwin` with mocked dependencies
- `daydream`, `recall`, `gitget`, `update-files`
- `codexerrors.py`, `codextools.py`, `codexlist`, `copilotlist`
- `rofi-prompts.sh`, `rofi-files.sh`, `copy-to-markdown.sh`
- `discourse.py`, `gmail.py`, `rename_receipts.py`

Recommended change:

- create fixture-based tests for log/file parsers
- add shell smoke tests for CLIs and exit codes
- add a small `just smoke` or `uv run` test harness for the repo

## Script-Specific Improvements

### Capture, prompt, and launcher tools

- `ask:20-45`
  - Replace string-based command assembly with real argument handling.
  - Add `--model`, `--prompt`, `--prompt-file`, `--copy=all|code`, `--no-copy`, and `--save-transcript`.
  - Detect clipboard backend instead of assuming `xclip`.
  - Offer `--device` / `--duration` / `--vad` controls for audio capture.

- `askwin:18-36`
  - Make it self-locating instead of depending on hard-coded PATHs.
  - Fold it into `ask --paste` so voice capture and paste logic are not separate scripts.
  - Add clearer behavior flags: `--enter`, `--activate-window`, `--clipboard-only`.

- `q:12-59`
  - Move brittle site selectors into a data file or adapter layer so UI changes are easier to update.
  - Add `--timeout`, `--cdp-url`, `--new-tab`, `--text-only`, and `--print-url`.
  - Validate browser/CDP availability before opening Playwright.

- `daydream:10-39`
  - The positional goal argument is effectively unreachable because `goal` starts non-empty and the parser only assigns when `[[ -z "$goal" ]]`.
  - Replace hand-rolled parsing with `--goal`, `--concept`, `--latest`, `--random`, `--out`.
  - Add `--json` and a configurable storage path.

- `recall:21-36`
  - Escape search terms by default and add an explicit `--regex` mode.
  - Handle "no matching files" gracefully instead of indexing `files[0]`.
  - Add `--sources`, `--seed`, `--list-files`, and `--json`.

### Clipboard, rofi, and local desktop helpers

- `rofi-files.sh:14-31`
  - #TODO First-run behavior is brittle: `tail "$FRECENT"` and `cat .../files*.txt` assume cache files already exist.
  - Use `xdg-open` on Linux instead of `open` in `rofi-files.sh:44`.
  - Add preview, file-type filters, and a cache-miss fallback to live search.

- `rofi-chrome-tabs.sh:7-19`
  - Add `--port`, `--browser`, and `--copy-url` / `--copy-title` actions.
  - Fail clearly when CDP is unavailable.
  - Consider listing window IDs or grouping by domain/profile.

- `rofi-prompts.sh:27-58,327-358`
  - Good caching design already; next step is usability polish.
  - Add preview of the extracted fenced block before paste/type.
  - Make the default prompt root configurable instead of hard-coding `~/code/blog/pages/prompts`.
  - Add source-open actions so the chosen prompt can be edited quickly.

- `rofi-clip.sh:147-190,303-417`
  - Split the giant menu into subcommands or plugin files so transforms are easier to add and test.
  - #TODO The "STUBS" comment is stale; the functions are implemented now.
  - #TODO Rich-text transforms bypass the clipboard abstraction and call `xclip` directly at `377-391`; that breaks Wayland support.
  - #TODO Add `--list` and `--run <transform>` so the script is usable outside rofi.
  - Preflight external tools like `unidown`, `pandoc`, `jq`, `notify-send`, `wl-copy`, `xclip`.

- `copy-to-markdown.sh:10-22`
  - #TODO Reuse the clipboard abstraction from `rofi-clip.sh`.
  - Fail clearly when clipboard HTML is absent.
  - #TODO Consider merging this into `rofi-clip.sh --run richtext-to-markdown`.

- `clean_markdown.py:167-225`
  - #TODO Merge this into `rofi-clip.sh`
  - Add stdin/stdout support so it can be used in pipes, not just files or `--xclip`.
  - Extend clipboard support beyond `xclip`.
  - Expose a `--check` mode for CI/editor integrations.

### Dev environment and services

- `dev.sh:73-146`
  - Break the huge baked-in mount/env set into profiles like `--profile minimal|agent|gpu|desktop`.
  - Print which optional mounts are missing instead of silently assuming they exist.
  - Move secrets/mount config into a `.env`/TOML file instead of embedding everything in one array.
  - Add `--print-command` / `--dry-run` for debugging container launches.

- `dev.info.sh:43-45`
  - It dumps the full environment, including secrets, by default.
  - Add `--redact`, `--section`, and `--json` so it is safer to share.

- SKIP: `dev.test.sh:50-152`
  - Let users select profiles (`--offline`, `--network`, `--gpu`, `--auth`) instead of running every probe every time.
  - Stream a concise summary table instead of only `ERROR:` lines.
  - Record skipped checks separately from failed checks.

- `services/setup.sh:17-49`
  - Add `--dry-run`, `--status-only`, and `--enable/--disable`.
  - Surface which units were linked/changed instead of only printing raw `systemctl` output.
  - Check that `systemd --user` is available before attempting setup.

### Git and filesystem utilities

- `gitget:26-37`
  - Add cleanup via `trap` so temp dirs are removed on failure.
  - Preserve dotfiles and empty directories; `cp -r "$tmpdir/$src/"* "$dst/"` skips them.
  - Add `--dry-run`, `--force`, and `--method sparse-checkout|archive`.

- `git-uncommitted:3-24`
  - It only inspects first-level directories and only reports `COMMIT` / `SYNC`.
  - Add `--path`, `--depth`, `--fetch`, `--json`, and separate statuses for ahead/behind/diverged/untracked/no-remote.

- `update-files:19-46`
  - Add status output, `--force`, `--mtime-days`, and configurable ignore lists.
  - Make the cache root configurable.
  - Consider subcommands: `rebuild`, `recent`, `list-targets`.

- `rename_receipts.py:317-336`
  - Duplicate detection uses file size only, which is unsafe for deletes.
  - Switch to content hashing or byte comparison before removing a "duplicate".
  - Add `--jsonl`, `--vendor`, `--move-to`, and an interactive review mode for skipped files.

- `chars:7-14`
  - Add `--json`, `--summary`, and `--ignore` patterns.
  - Allow stdin so it works in pipelines.

- `rgb:6-35`
  - Support `#RGB`, `#RRGGBBAA`, and CSS-style `rgb(...)` inputs.
  - Add `--lower`, `--prefix`, and `--json`.

### Log inspection and agent analytics

- `claudelog`
  - This is one of the repo's better CLIs; use it as the model for the other log tools.
  - Add `--json` output for `ls`/`resolve` so downstream tools do not have to parse formatted text.
  - Add search/filter shortcuts like `--contains`, `--tool`, and `--recent`.

- `codexlist:10-93`
  - #TODO The parser is regex-based and only offers a single optional filter argument.
  - #TODO Replace it with proper JSON parsing and give it parity with `claudelog`: `ls`, `resolve`, `md`, `dump`.
  - #TODO Add `--json` and time-based filters.

- `copilotlist:9-85`
  - #TODO Add `--json`, `--since`, `--limit`, and better filtering than a single path substring.
  - Promote the jq logic into a reusable shared parser for session summaries.

- `codexerrors.py:60-65,147-163`
  - Stop hard-coding the working directory.
  - Add grouped summaries by day/session/tool and `--json`/CSV output.
  - Surface how many logs were scanned/skipped so results are auditable.

- `codextools.py:216-259`
  - Add `--json`, `--top N`, `--tool`, `--shell-only`, and date filters.
  - Emit per-log detail optionally, not only the global aggregate.

- `codextags.py:43-141,2103-2154`
  - The generated schema is large and hard to discover; generate a companion field glossary from the column list.
  - Add `--stats-json`, `--since`, `--changed-only`, and a report mode for parse failures.
  - `REQUIRED_COLUMNS` includes duplicates (`skill_count`, `executable_count`), which makes the schema harder to reason about.

- `codexlog.jq`, `copilotlog.jq`, `opencodelog.jq`
  - #TODO Add a compact mode with timestamps and call IDs preserved.
  - Add a machine-readable mode instead of only Markdown conversion.
  - Make event filtering consistent across the three converters.

### API/data/network utilities

- `gmail.py:162-186`
  - Validate requested `--fields` and error on typos instead of silently dropping unknown names.
  - Add `--format table|tsv|jsonl`, `--threads`, and maybe `--body` / `--raw`.

- `google_oauth.py:24-72`
  - Add non-browser auth/device-code support for headless environments.
  - Improve the error text when Google client env vars are missing.

- `discourse.py:190-216`
  - #TODO `--since` is required even when `--topic-id` is used, although topic mode ignores it. Make `--since` required only for category mode.
  - Add JSONL output and richer filters (`--limit`, `--include-op-only`, `--include-images`).

- `githubscore.py:291-328`
  - Replace the hand-rolled CLI with Typer and add `--help`.
  - Expose score weights and component breakdown in the output.
  - Add JSON/CSV output, better rate-limit handling, and visible error accounting instead of bare `except` undercounting.

- `jsonpaths.jq`
  - Add a mode for JSONPath output in addition to jq-style paths.
  - Add depth filtering and maybe path frequency counts.

- `tsv.jq:7-11`
  - Row emission uses each row's `keys_unsorted[]`, which can misalign values with the header if object key order differs by row.
  - Reuse the header order for every row.
  - Add support for NDJSON input directly and empty-array handling.

- `whatsappthread.jq:22-27`
  - URL extraction is intentionally brute-force and misses punctuation/non-space separators.
  - Add better URL parsing plus media/attachment extraction.
  - Consider a thread-summary mode instead of only per-message JSONL.

### Media, presentation, and legacy tools

- `audiosync.py:26-86`
  - Add `--dry-run`, `--plot`, `--confidence`, and codec controls.
  - Preflight `ffprobe`/`ffmpeg` with actionable errors.
  - Emit a machine-readable timing summary.

- `slide.py:28-29,175-260`
  - The relative `.slide_state.json` makes state brittle across directories.
  - Move state under XDG cache or add `--state-file`.
  - Replace hand parsing with a proper CLI and add `--list`, `--search`, `--reset`, `--stdout`.
  - Use a safer screen-clear mechanism than `os.system(...)`.

- `viz.py`
  - This is effectively a legacy Python 2-era tool (`print`, `xrange`, `iteritems`).
  - Either modernize it fully and test it, or mark it as legacy/deprecated in the README.
  - If kept, add a modern CLI, better template discovery, and explicit dependency docs.

- `generate/heavy_pdfs.py:19-86`
  - Turn it into a real CLI with `--rects`, `--out-pdf`, `--out-lua`, `--force`.
  - Right now it is useful only as a one-shot script in the current directory.

- `unbrace.js:25-45`
  - Expand the transform to cover `else { ... }` and other single-statement brace cases.
  - Add a dry-run/check mode example to the usage docs.

### Agent/skill helper scripts

- `mcpserver.py:21-44`
  - Add auth, allowlists, workdir restrictions, configurable timeout, and readonly mode.
  - The current default is useful for personal experiments but too risky as a general-purpose server.
  - Support `stdio` transport and a clear `--bind` / `--port` CLI.

- `agents/.system/skill-creator/scripts/generate_openai_yaml.py`
  - Add `--stdout`, `--dry-run`, and dependency docs for `yaml`.
  - Return structured JSON on success/failure so other tooling can call it.

- `agents/.system/skill-creator/scripts/init_skill.py`
  - Add rollback/cleanup when `SKILL.md` is created but later steps fail.
  - Add `--dry-run` and `--template workflow|task|reference`.

- `agents/.system/skill-creator/scripts/quick_validate.py`
  - Return all validation failures, not just the first one.
  - Add `--json` output for editor/tool integration.

- `agents/.system/skill-installer/scripts/install-skill-from-github.py`
  - Add `--dry-run`, `--overwrite`, and upgrade semantics.
  - Print progress for multi-skill installs and report exactly what was copied.

- `agents/.system/skill-installer/scripts/list-skills.py`
  - Already has `--format json`; add filters like `--installed-only` and `--missing-only`.

- `agents/webapp-testing/scripts/with_server.py:63-102`
  - Stream server logs with prefixes so startup failures are debuggable.
  - Add health URL checks, not only port checks.
  - Avoid `shell=True` when possible, or at least document the risk and quoting rules more explicitly.

- `agents/devtools/check-page.py`, `agents/devtools/check-page.js`
  - Parameterize URL, selectors, screenshot path, and CDP endpoint.
  - These should be reusable debugging helpers, not one-page one-off scripts.

- `agents/webapp-testing/examples/*.py`
  - Examples should prefer temp/output args instead of fixed `/mnt/user-data/outputs` paths.
  - Add short comments showing the exact setup assumptions.

## Suggested Implementation Order

1. Build shared config/dependency helpers and remove hard-coded paths.
2. Standardize `--help`, `--json`, and `--dry-run` across the most-used scripts.
3. Refactor clipboard/browser helpers for cross-platform behavior.
4. Bring log tools to a common interface, using `claudelog` as the quality bar.
5. Add smoke tests around file-moving, network, and log-parsing scripts.
6. Modernize or explicitly deprecate legacy tools like `viz.py`.

## Agent-Log-Driven Dev Container Improvements

These recommendations come from repeated failures in past Codex, Claude, and GitHub Copilot logs under `~/.codex`, `~/.claude`, and `~/.copilot`. The priority order below is based on how often the issue recurred and how broadly it blocks agent workflows.

### 1. Stop mounting writable config/binary paths in ways that break updates

This is the highest-leverage `dev.sh` fix.

- Claude repeatedly hit `EROFS` while trying to update `/home/vscode/.local/bin/claude`, because the container sees that path as read-only.
- Claude also repeatedly hit `EBUSY` while trying to atomically rename `/home/vscode/.claude.json.tmp...` to `/home/vscode/.claude.json`, which is a classic symptom of bind-mounting a single mutable file.

Recommended change:

- keep a container-owned writable `~/.local/bin` on PATH ahead of any host-mounted bin directory
- if host binaries are needed, mount them somewhere else like `~/.host-local-bin:ro` and append that path later in `PATH`
- avoid bind-mounting single mutable files like `~/.claude.json`; mount the parent config directory or sync/copy the file into a writable container path on startup

Reason:

- agent CLIs increasingly self-update, rewrite symlinks, and use atomic file replacement for settings
- the current mount strategy causes avoidable environment failures even when the underlying tools are otherwise installed correctly

### 2. Install the full XML/SVG/ImageMagick validation stack by default

Past Copilot sessions failed on `rsvg-convert` and `xmllint`, and an `identify` run fell into an AppImage/FUSE path that failed with `No suitable fusermount binary found on the $PATH`, followed by `identify: command not found`.

Recommended change:

- add `libxml2-utils` so `xmllint` is always available
- keep `librsvg2-bin` / `rsvg-convert` in the image
- prefer distro `imagemagick` binaries over AppImage-style fallbacks so `identify`, `magick`, and related tools work without FUSE assumptions

Reason:

- SVG-heavy tasks routinely need both rendering and XML validation
- image-debugging workflows become fragile if they depend on host AppImages or partial ImageMagick installs

### 3. Add PDF build headers, not just end-user PDF CLIs

A Claude PDF-extraction session failed while building `pdftotext==3.0.0` via `uvx`: `pkg-config not found`, then `fatal error: poppler/cpp/poppler-document.h: No such file or directory`.

Recommended change:

- add `pkg-config`
- add `libpoppler-cpp-dev`
- keep the existing Poppler command-line tools as well

Reason:

- many agent workflows do not just call `pdftotext`; they install Python bindings on demand with `uv run --with ...`
- without the development headers, the container looks “PDF-ready” for humans but still fails for agent-driven extraction tasks

### 4. Keep browser automation ready-to-run, not just mostly installed

A Claude debugging session failed because Node could not import `playwright`, and the agent had to stop and ask the user to install it manually.

Recommended change:

- keep global `playwright` installed in the image
- keep the browser payloads in a container-owned path that is not shadowed by a host cache mount
- in `dev.sh`, consider warning when a host mount would hide the image-installed browsers

Reason:

- browser debugging is one of the most common agent workflows
- a missing package or hidden browser install wastes a lot of time before any actual debugging starts

### 5. Keep a few high-ROI “small” tools preinstalled

Several older sessions stalled on lightweight but useful tools such as `jaq` and `Pillow`/`PIL`.

Recommended change:

- keep `jaq` in the base CLI toolset
- keep `pillow` in the global `uv` environment
- prefer preinstalling a few of these small, frequently reused utilities over paying repeated ad hoc install/setup costs during sessions

Reason:

- these tools are cheap to carry in the image
- they unlock common JSON inspection and quick image-analysis tasks without forcing every agent to bootstrap its own mini-environment
