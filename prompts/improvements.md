# Project review — 10 November 2026

The executable verification gate now passes. The highest-priority remaining decision is how to tie Meet archives to Drive file IDs before permanent source deletion. The next priorities are complete filtered Drive results and complete Discourse topic extraction.

## Coverage and limits

All 281 tracked files were inventoried and searched. The review combined repository-wide static checks with manual inspection of scripts, configuration, existing tests, prompt specifications, and especially failure/data-loss paths. This is a broad audit, not a claim that every line or every external integration has been semantically verified.

- Parsed/scanned 83 non-archived Python files, including tests and extensionless Python commands; syntax-checked 33 shell scripts, Fish configuration, and tracked JavaScript.
- Ran every focused test recipe independently to expose failures hidden by the fail-fast aggregate recipe, then ran the repaired aggregate gate.
- Used temporary Git repositories, fake API responses, mock clipboard/voice tools, and synthetic archives for destructive-path checks.
- Preserved the existing LinkedIn work and `prompts/scripts.md`. The branch advanced concurrently during this audit; no commits were created by this review.
- Did not run live archiving/deletion, send mail, change calendar events, sync phones/Plutonium, install services, rebuild the development image, or exercise paid inference. Browser tests used the existing offline fixtures. GNOME behavior was checked with the existing stand-ins, not on a desktop session.

## Fixed

| Area | Concrete change and evidence |
| --- | --- |
| [justfile](../justfile) | Added the existing Twitter, translation, and AI Usage tests to the complete gate. The archived Python LinkedIn test path was also repaired and now passes; that path correction is already included in the concurrent branch changes. |
| [backupchatgpt.py](../backupchatgpt.py) | Repaired `--describe` under installed Typer 0.29, which no longer exposes the old parameter `.type`. Regression asserts types, defaults, and repeated arguments. |
| [transcribe](../transcribe) | Restored default `--prompt "Transcribe"`, matching both `prompts/transcribe.md` and the existing tests. Custom prompts still work. |
| [ai-usage/format.js](../ai-usage/format.js) | Restored documented seven-day reset thresholds: amber within 24 hours, red within 12 hours. The previously omitted widget suite caught this mismatch. |
| [backupmeet.py](../backupmeet.py) | Enforced the personal-account-only contract; validate fresh downloads before replacing prior local copies; re-check archive completion before deletion; regenerate stale Opus output; detect name collisions before applying `--limit`. Mocked tests prove truncated/non-DOCX downloads and incomplete archives cannot reach deletion. |
| [google_oauth.py](../google_oauth.py), [htmlemail.py](../htmlemail.py) | Shared private, atomic token writes: temporary files have mode 0600, failed replacement preserves previous credentials, and temporary files are cleaned. Existing permissive token files are secured on their next successful write. No real credentials were changed. |
| [git-stage-repo](../git-stage-repo) | Refuse to overwrite dirty separate snapshot directories by default, including untracked and ignored files. A disposable reproduction previously lost both tracked edits and an untracked file. `--force` now explicitly describes the discard behavior. |
| [gitget](../gitget) | Copy dotfiles and hidden directories, fail on clone/copy errors, reject malformed mappings, clean temporary clones on failure, and make `--help` succeed. Tested with spaces and multiple failure paths. |
| [tsv.jq](../tsv.jq) | Use the first row's header order for every row; handle empty input. Previously reversed-key objects silently put values under the wrong columns. Checked with both jq and jaq. |
| [rgb](../rgb) | Validate hexadecimal input and interpret decimal components with leading zeros correctly, including padded values; reject oversized/out-of-range input without partial stdout. |
| [chars](../chars) | Avoid crashing on unnamed Unicode code points. Checked unnamed, control, and supplementary characters. |
| [copy-to-markdown.sh](../copy-to-markdown.sh) | Stop before writing either clipboard if HTML capture or conversion fails. Added failure-preservation coverage to the existing clipboard test module. |
| [ask](../ask) | Pass `ask.md` as an actual system-prompt argument instead of embedding `-s` inside the user prompt; preserve multiword CLI prompts. All external tools were mocked for verification. |
| [daily-activities](../daily-activities) | Publish tab snapshots through a private temporary file. Browser/JSON failures now preserve the previous snapshot instead of truncating it. |
| [dev.test.sh](../dev.test.sh) | Register temporary directories in the parent shell, so the EXIT cleanup can actually remove them. Previously command substitutions lost every registration. Checked the actual extracted allocation/cleanup helpers. |
| [aboutmerge.py](../aboutmerge.py) | Refuse generated person headings containing path separators or NUL, preventing headings such as `../escape` from writing outside the notes directory. |
| [discourse.py](../discourse.py) | Require `--since` only for category mode; emit topics containing only an original post; include newly created original posts in category output even without replies. Tested with fake responses. |
| [backuptwitter.py](../backuptwitter.py) | Respect explicit `complete: false` even when the saved week contains no tweets, allowing incomplete empty weeks to be retried. Added an existing-module regression. |
| [emailai](../emailai) | Prevent generated attachment names from colliding with real numbered names, e.g. `report.pdf`, another `report.pdf`, and `report-2.pdf`. Verified distinct names and bytes. |
| [githubscore.py](../githubscore.py) | Escape strings in YAML output, send API progress to stderr, and pass test-tree cache parameters explicitly rather than depending on CLI-created globals. Checked YAML round-trip and stdout isolation. |
| [codexerrors.py](../codexerrors.py) | Honor relative `--log-dir` paths without changing cwd; recognize modern `exec_command`/`cmd` records and top-level exit codes; enforce short detail limits. Tested old and new log shapes. |
| Configuration/docs | Include `dev.dockerfile` in the hadolint filename pattern; fix six broken local links, invalid `q` examples, references to retired units, the MCP startup order/timeout text, and incomplete Plutonium sync documentation. Removed four unused test imports. |

## Remaining issues for review

Priorities reflect potential harm and misleading output, not implementation size. “Confirmed” means executed fixture or directly traced code behavior; integration concerns below are explicitly unverified.

### 1. Meet archive identity and stronger verification — high priority, confirmed

[backupmeet.py](../backupmeet.py): `Archive.for_file()`, `Archive.complete()`, `avoid_output_collisions()`.

Two distinct Drive IDs with the same normalized title/date, size, and modification time map to the same local path. A synthetic copy belonging to the first ID was considered complete for the second ID. Current collision handling sees only the current discovery set, so it cannot establish identity across separately filtered or historical runs.

Verification also remains size/mtime for binary files and a two-byte ZIP signature for native Docs exports. Equal-size corruption, a wrong existing copy, or an invalid ZIP with that signature can still pass. This matters because the normal workflow permanently deletes old Drive originals.

**Decision:** use a persistent Drive-ID/version/checksum manifest, or include IDs in every archive filename and migrate existing copies. Add DOCX ZIP/media validation according to the desired strength. The new checks close the proven truncated-download path; they do not establish cryptographic or source-identity equivalence.

### 2. Filtered Drive queries can miss valid results — confirmed

[gwslog.py](../gwslog.py): `fetch_files()` and `log()`.

Files are capped at `limit * 3` before path/user/owner/folder filters run. A fixture with the only matching item at position 301 returned no matches after a 300-row cap. A small cached result can also be reused for a larger request sharing the same cache key. The implementation buffers paginated output and can request far more data than it ultimately retains.

**Decision:** stream pages until enough matching rows are emitted or the API is exhausted; record cache coverage/cursors instead of treating a sliced list as a complete response. This needs a coordinated pagination/cache change, not simply a larger multiplier.

### 3. Discourse completeness and edited-post semantics — confirmed code gaps

[discourse.py](../discourse.py): `collect_topic_posts()` and `stream_markdown()`.

Extraction consumes only the posts supplied in the initial topic response; it does not follow the complete post stream. Filtering uses `created_at` and topic `last_posted_at`, despite documentation promising created/edited posts. Old posts edited recently can be omitted, and the 60-old-topic stopping heuristic has no explicit completeness proof.

**Decision:** define whether the output includes creations, edits, or both, then implement full post pagination and fixture-test long topics and edits. The repaired single-post/topic CLI behavior does not solve these broader completeness issues.

### 4. Email context cache needs source identity — confirmed design gap

[emailai](../emailai): `prepare_context()` and `download_attachments()`.

The cache is keyed by message ID without an account namespace; attachment reuse is based on generated filename and size. Filename collisions are fixed, but a same-size stale attachment can still be reused without verifying its attachment identity. Cached mail, attachments, and prompts also use ordinary file writes.

**Decision:** namespace by the verified Google account and stable message/attachment IDs, and use private atomic writes. Define how to migrate existing cache directories before changing their layout.

### 5. GitHub scores can silently understate evidence — confirmed

[githubscore.py](../githubscore.py): `test_paths()` and `get_user_data()`.

Bare exception handlers turn authentication, rate-limit, network, and parsing failures into absent README/license/tests/CI evidence. Distinct review repositories are counted from only the first 100 search results. Serial per-repository API/tree calls are also expensive on cold caches. Output formatting is fixed; score completeness/reliability is not.

**Decision:** distinguish expected absence from failed retrieval, report coverage with the score, paginate the distinct-repository calculation, and decide which expensive checks are worth keeping. Do not change the scoring weights merely to hide missing evidence.

### 6. Shared context rebuild temp path — confirmed concurrency hazard

[context.py](../context.py): `rebuild_database()`.

All rebuilds use the same `<database>.tmp` and unlink it at startup. Concurrent manual/scheduled rebuilds can interfere with each other's in-progress database. Rebuilding every source from scratch also repeats parsing of unchanged archives.

**Decision:** serialize rebuilds with a lock or introduce independently named temporary databases with a defined publication policy. Benchmark actual rebuild time before designing incremental indexing.

### 7. Music-history writers can race — code-level risk, not live-reproduced

[phonemusic](../phonemusic): `merge_history()`/`sync()` and [services/vlc-history.sh](../services/vlc-history.sh).

Phone sync reads and later replaces the laptop history while the VLC service appends to that same file. An append between the read and replacement can disappear. Current MP3 resume checks also verify remote size, not content, and select the first mounted MTP phone.

**Decision:** coordinate history writers or re-merge under a shared lock, then decide whether explicit device selection and content verification are needed. Requires an MTP/VLC integration test before calling the whole workflow verified.

### 8. Twitter completeness depends on upstream assumptions — integration unverified

[backuptwitter.py](../backuptwitter.py): `fetch()`, `complete_from_fetch()`, `existing_data_complete()`.

A short fetched batch is treated as exhaustion; legacy archives without completion metadata are trusted by default. The adapter subclasses a private initializer and changes a private package count constant. The explicit incomplete-empty-week bug is fixed, but current live pagination/completeness was not validated against X.

**Decision:** retain these documented shortcuts, or make completeness explicit from upstream pagination and add adapter contract tests before upgrading the dependency.

### 9. Metered-network policy differs between wrappers — confirmed inconsistency

[daily-activities](../daily-activities): `is_unmetered_connection()` returns on the first known unmetered device. [services/sync-plutonium.sh](../services/sync-plutonium.sh) rejects a known metered device even if another device is unmetered.

**Decision:** select the effective/default route, or define a consistent policy for multiple connected interfaces. Neither current check proves which interface a transfer will actually use. Live network routing was not changed.

### 10. Validation tooling needs a supported scope — confirmed

The targeted Python correctness/unused-code checks pass. The broader configured Ruff scan still reports **331 diagnostics**, many being style suggestions, intentional Typer defaults, or explicit broad error handling. ShellCheck reports **22 warnings/errors**: ten in legacy `setup.bash`, four in `rofi-files.sh`, two each in `rofi-picker`/`codexusage`, and one each in `dev.sh`, `git-stage-repo`, `ask`, and `vlc-history.sh`.

Some findings are intentional: Bash supplies the coprocess PID, the picker uses a literal tilde for display, and `git-stage-repo` already validates its path. The old Windows helpers do contain unquoted argument forwarding and unchecked directory changes. The pre-commit mypy/formatting hooks and the complete container build were not exercised; `just verify` is a test gate, not proof that every hook passes.

**Decision:** identify maintained shell aliases, then fix or archive those groups; define which style/type checks should gate isolated single-file scripts. Avoid a repository-wide automated formatter/fix pass without agreeing on that scope.

### 11. Integration coverage remains uneven — confirmed coverage gap

There are no dedicated persistent test modules for several substantial tools, including `activities.py`, `backupmeet.py`, `gwslog.py`, `phonesync`, `phonemusic`, `emailai`, and `git-stage-repo`. Some repaired paths were verified with disposable fixtures in this review. In particular, the large phone migration/retirement path should have retained fixture coverage before further refactoring.

**Decision:** add small, offline regression modules for the maintained tools, then selected live tests for CDP selectors, Android/MTP, GNOME, systemd, and container/image behavior. New permanent test files were not added during this review, following the repository preference.

## Retirement candidates — confirm use before deletion

- [download.xml](../download.xml) is actually a valid **646,120-byte DOCX ZIP**, not XML. ZIP integrity and Word components were checked without exposing its content. It has no script references found in this checkout. Confirm its provenance, then move it to the appropriate document archive or remove it from the repository.
- [sent.csv](../sent.csv) is empty and has no script references found. [.qdrant-initialized](../.qdrant-initialized) is an empty marker; the global ignore file mentions it. Confirm whether external tools still use these before removing them.
- [archive/asu](../archive/asu) explicitly said to delete after 20 April 2026. [archive/viz.py](../archive/viz.py) is Python 2 code and fails Python 3 parsing. These are already archived; decide whether the repository should retain historical artifacts.
- [codexlist](../codexlist), [codexerrors.py](../codexerrors.py), [codextools.py](../codextools.py), [codextags.py](../codextags.py), and [agentlog.py](../agentlog.py) overlap. They expose different contracts, so usage evidence is needed before consolidation.
- [copy-to-markdown.sh](../copy-to-markdown.sh) overlaps the HTML-to-Markdown transform in [rofi/rofi-clip.sh](../rofi/rofi-clip.sh). Keep both keybinding contracts or consolidate explicitly.
- [q](../q) overlaps the maintained [chatgpt](../chatgpt) CLI for ChatGPT but also supports other sites. Its selectors, foreground behavior, and tab lifecycle need a live check before retiring or redirecting it.
- [setup.bash](../setup.bash) contains many Windows/Cygwin-era aliases and one-off project commands. Archive by actual use rather than assuming all Windows support is obsolete.
- `backupmeet.py --yes` is a compatibility no-op still passed by `daily-activities`; removing it is an optional CLI cleanup, not a correctness fix.

## Verification evidence

- `just verify`: **730 Python tests + 103 Node tests passed**, plus the offline AI Usage adapter/widget suite. No failures.
- All **17** standalone `--describe` smoke checks returned valid JSON successfully.
- **15** groups of disposable utility regressions passed, covering happy paths and preservation on failure. Git repositories and inputs were synthetic; external actions were mocked.
- Targeted static checks: `E9,F63,F7,F82,F401,F841,B006,B012,B023` passed across the 83 non-archived Python files, including extensionless commands.
- Shell/Fish/JavaScript syntax checks and ten structured configuration/asset parses passed. The apparent XML parse failure was diagnosed as the misnamed DOCX listed above.
- `git diff --check` passed. The hadolint filename pattern was checked against `dev.dockerfile`, `Dockerfile`, and variant/nested names; the image itself was not built.

Temporary evidence, available for this session:

- `/tmp/scripts-review-final-verify.log`: final canonical test output.
- `/tmp/scripts-review-fixtures.py` and `.log`: executable disposable regressions and results.
- `/tmp/scripts-review-describe.json`: CLI metadata smoke-test results.
- `/tmp/scripts-review-final-shellcheck.json`: remaining shell diagnostics with exact locations.

For reproduction, use `just verify` for the durable test gate. The temporary fixture runner declares its required packages in the review tool invocation rather than adding a test requirements file to this repository.
