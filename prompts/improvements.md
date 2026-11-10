# Project review — 10 November 2026

The executable verification gate passes. The requested retirements and clipboard consolidation are complete. The remaining priorities are complete Discourse extraction, safe concurrent context rebuilds, and music-history writer coordination.

## Coverage and limits

In the initial audit, all 281 tracked files were inventoried and searched. The review combined repository-wide static checks with manual inspection of scripts, configuration, existing tests, prompt specifications, and especially failure/data-loss paths. This is a broad audit, not a claim that every line or every external integration has been semantically verified.

- Parsed/scanned 83 non-archived Python files, including tests and extensionless Python commands; syntax-checked 33 shell scripts, Fish configuration, and tracked JavaScript.
- Ran every focused test recipe independently to expose failures hidden by the fail-fast aggregate recipe, then ran the repaired aggregate gate.
- Used temporary Git repositories, fake API responses, mock clipboard/voice tools, and synthetic archives for destructive-path checks.
- Preserved the existing LinkedIn work and `prompts/scripts.md`. The branch advanced concurrently during the initial audit. The follow-up committed the complete reviewed tree as `73d2169` before making the requested retirements.
- Did not run live archiving/deletion, send mail, change calendar events, sync phones/Plutonium, install services, rebuild the development image, or exercise paid inference. Browser tests used the existing offline fixtures. GNOME widget behavior was checked with the existing stand-ins. The follow-up updated and read back the single live Ctrl+Alt+C command; an actual desktop keypress was not simulated.

## Fixed

### Retirements and consolidation — 10 November 2026

These items are resolved by retirement from the active workflow, rather than by repairing every known limitation in the archived code. The archived files are retained unchanged as historical references.

| Completed item | Outcome and reason |
| --- | --- |
| Meet archival and its remaining identity/integrity risks | Moved `backupmeet.py` to [archive/backupmeet.py](../archive/backupmeet.py). I use ChatGPT when required, including bulk-download automation. Removed the daily job and its obsolete `--yes` caller. |
| Drive result truncation/cache concerns | Moved `gwslog.py` to [archive/gwslog.py](../archive/gwslog.py). I use ChatGPT weekly, when required, to summarize Drive activity rather than just list it. |
| Email context cache/attachment identity concerns | Moved `emailai` to [archive/emailai](../archive/emailai). I use ChatGPT because it has more context. |
| GitHub scoring reliability/completeness concerns | Moved `githubscore.py` to [archive/githubscore.py](../archive/githubscore.py). I use ChatGPT because it evaluates developers on broader, evolving criteria. |
| Duplicate Codex session listing | Moved `codexlist` to [archive/codexlist](../archive/codexlist). I use [agentlog.py](../agentlog.py). |
| CLI queries to assistant websites | Moved `q` to [archive/q](../archive/q). I do not query ChatGPT, Claude, or other assistants from the CLI. |
| Duplicate rich-text conversion wrapper | Deleted `copy-to-markdown.sh`. [rofi/rofi-clip.sh](../rofi/rofi-clip.sh) now supports `--html-to-markdown`, retaining direct conversion, failure preservation, and clipboard/primary-selection writes. Updated Ctrl+Alt+C in [setup/media-keys.dconf](../setup/media-keys.dconf); Ctrl+Alt+M retains its menu. |
| Unneeded artifacts | Deleted the misnamed DOCX `download.xml`, empty `sent.csv`, and expired one-off `archive/asu`, as requested. |
| Documentation and review organization | Documented every archive reason in [README.md](../README.md), removed stale daily-service documentation, and moved this review from the repository root into `prompts/`, preserving working relative links. |

### Earlier audit fixes

| Area | Concrete change and evidence |
| --- | --- |
| [justfile](../justfile) | Added the existing Twitter, translation, and AI Usage tests to the complete gate. The archived Python LinkedIn test path was also repaired and now passes; that path correction is already included in the concurrent branch changes. |
| [backupchatgpt.py](../backupchatgpt.py) | Repaired `--describe` under installed Typer 0.29, which no longer exposes the old parameter `.type`. Regression asserts types, defaults, and repeated arguments. |
| [transcribe](../transcribe) | Restored default `--prompt "Transcribe"`, matching both `prompts/transcribe.md` and the existing tests. Custom prompts still work. |
| [ai-usage/format.js](../ai-usage/format.js) | Restored documented seven-day reset thresholds: amber within 24 hours, red within 12 hours. The previously omitted widget suite caught this mismatch. |
| [backupmeet.py](../archive/backupmeet.py) | Enforced the personal-account-only contract; validate fresh downloads before replacing prior local copies; re-check archive completion before deletion; regenerate stale Opus output; detect name collisions before applying `--limit`. Mocked tests prove truncated/non-DOCX downloads and incomplete archives cannot reach deletion. |
| [google_oauth.py](../google_oauth.py), [htmlemail.py](../htmlemail.py) | Shared private, atomic token writes: temporary files have mode 0600, failed replacement preserves previous credentials, and temporary files are cleaned. Existing permissive token files are secured on their next successful write. No real credentials were changed. |
| [git-stage-repo](../git-stage-repo) | Refuse to overwrite dirty separate snapshot directories by default, including untracked and ignored files. A disposable reproduction previously lost both tracked edits and an untracked file. `--force` now explicitly describes the discard behavior. |
| [gitget](../gitget) | Copy dotfiles and hidden directories, fail on clone/copy errors, reject malformed mappings, clean temporary clones on failure, and make `--help` succeed. Tested with spaces and multiple failure paths. |
| [tsv.jq](../tsv.jq) | Use the first row's header order for every row; handle empty input. Previously reversed-key objects silently put values under the wrong columns. Checked with both jq and jaq. |
| [rgb](../rgb) | Validate hexadecimal input and interpret decimal components with leading zeros correctly, including padded values; reject oversized/out-of-range input without partial stdout. |
| [chars](../chars) | Avoid crashing on unnamed Unicode code points. Checked unnamed, control, and supplementary characters. |
| Clipboard conversion | Failure-preservation coverage originally added for `copy-to-markdown.sh` now exercises the replacement direct mode in [rofi/rofi-clip.sh](../rofi/rofi-clip.sh). |
| [ask](../ask) | Pass `ask.md` as an actual system-prompt argument instead of embedding `-s` inside the user prompt; preserve multiword CLI prompts. All external tools were mocked for verification. |
| [daily-activities](../daily-activities) | Publish tab snapshots through a private temporary file. Browser/JSON failures now preserve the previous snapshot instead of truncating it. |
| [dev.test.sh](../dev.test.sh) | Register temporary directories in the parent shell, so the EXIT cleanup can actually remove them. Previously command substitutions lost every registration. Checked the actual extracted allocation/cleanup helpers. |
| [aboutmerge.py](../aboutmerge.py) | Refuse generated person headings containing path separators or NUL, preventing headings such as `../escape` from writing outside the notes directory. |
| [discourse.py](../discourse.py) | Require `--since` only for category mode; emit topics containing only an original post; include newly created original posts in category output even without replies. Tested with fake responses. |
| [backuptwitter.py](../backuptwitter.py) | Respect explicit `complete: false` even when the saved week contains no tweets, allowing incomplete empty weeks to be retried. Added an existing-module regression. |
| [emailai](../archive/emailai) | Prevent generated attachment names from colliding with real numbered names, e.g. `report.pdf`, another `report.pdf`, and `report-2.pdf`. Verified distinct names and bytes. |
| [githubscore.py](../archive/githubscore.py) | Escape strings in YAML output, send API progress to stderr, and pass test-tree cache parameters explicitly rather than depending on CLI-created globals. Checked YAML round-trip and stdout isolation. |
| [codexerrors.py](../codexerrors.py) | Honor relative `--log-dir` paths without changing cwd; recognize modern `exec_command`/`cmd` records and top-level exit codes; enforce short detail limits. Tested old and new log shapes. |
| Configuration/docs | Include `dev.dockerfile` in the hadolint filename pattern; fix six broken local links, invalid `q` examples, references to retired units, the MCP startup order/timeout text, and incomplete Plutonium sync documentation. Removed four unused test imports. |

## Remaining issues for review

Priorities reflect potential harm and misleading output, not implementation size. “Confirmed” means executed fixture or directly traced code behavior; integration concerns below are explicitly unverified.

### 1. Discourse completeness and edited-post semantics — confirmed code gaps

[discourse.py](../discourse.py): `collect_topic_posts()` and `stream_markdown()`.

Extraction consumes only the posts supplied in the initial topic response; it does not follow the complete post stream. Filtering uses `created_at` and topic `last_posted_at`, despite documentation promising created/edited posts. Old posts edited recently can be omitted, and the 60-old-topic stopping heuristic has no explicit completeness proof.

**Decision:** define whether the output includes creations, edits, or both, then implement full post pagination and fixture-test long topics and edits. The repaired single-post/topic CLI behavior does not solve these broader completeness issues.

### 2. Shared context rebuild temp path — confirmed concurrency hazard

[context.py](../context.py): `rebuild_database()`.

All rebuilds use the same `<database>.tmp` and unlink it at startup. Concurrent manual/scheduled rebuilds can interfere with each other's in-progress database. Rebuilding every source from scratch also repeats parsing of unchanged archives.

**Decision:** serialize rebuilds with a lock or introduce independently named temporary databases with a defined publication policy. Benchmark actual rebuild time before designing incremental indexing.

### 3. Music-history writers can race — code-level risk, not live-reproduced

[phonemusic](../phonemusic): `merge_history()`/`sync()` and [services/vlc-history.sh](../services/vlc-history.sh).

Phone sync reads and later replaces the laptop history while the VLC service appends to that same file. An append between the read and replacement can disappear. Current MP3 resume checks also verify remote size, not content, and select the first mounted MTP phone.

**Decision:** coordinate history writers or re-merge under a shared lock, then decide whether explicit device selection and content verification are needed. Requires an MTP/VLC integration test before calling the whole workflow verified.

### 4. Twitter completeness depends on upstream assumptions — integration unverified

[backuptwitter.py](../backuptwitter.py): `fetch()`, `complete_from_fetch()`, `existing_data_complete()`.

A short fetched batch is treated as exhaustion; legacy archives without completion metadata are trusted by default. The adapter subclasses a private initializer and changes a private package count constant. The explicit incomplete-empty-week bug is fixed, but current live pagination/completeness was not validated against X.

**Decision:** retain these documented shortcuts, or make completeness explicit from upstream pagination and add adapter contract tests before upgrading the dependency.

### 5. Metered-network policy differs between wrappers — confirmed inconsistency

[daily-activities](../daily-activities): `is_unmetered_connection()` returns on the first known unmetered device. [services/sync-plutonium.sh](../services/sync-plutonium.sh) rejects a known metered device even if another device is unmetered.

**Decision:** select the effective/default route, or define a consistent policy for multiple connected interfaces. Neither current check proves which interface a transfer will actually use. Live network routing was not changed.

### 6. Validation tooling needs a supported scope — confirmed

The targeted Python correctness/unused-code checks pass. The broader configured Ruff scan still reports **305 diagnostics** after these retirements, many being style suggestions, intentional Typer defaults, or explicit broad error handling. ShellCheck reports **22 warnings/errors**: ten in legacy `setup.bash`, four in `rofi-files.sh`, two each in `rofi-picker`/`codexusage`, and one each in `dev.sh`, `git-stage-repo`, `ask`, and `vlc-history.sh`.

Some findings are intentional: Bash supplies the coprocess PID, the picker uses a literal tilde for display, and `git-stage-repo` already validates its path. The old Windows helpers do contain unquoted argument forwarding and unchecked directory changes. The pre-commit mypy/formatting hooks and the complete container build were not exercised; `just verify` is a test gate, not proof that every hook passes.

**Decision:** identify maintained shell aliases, then fix or archive those groups; define which style/type checks should gate isolated single-file scripts. Avoid a repository-wide automated formatter/fix pass without agreeing on that scope.

### 7. Integration coverage remains uneven — confirmed coverage gap

There are no dedicated persistent test modules for several substantial tools, including `activities.py`, `phonesync`, `phonemusic`, and `git-stage-repo`. The retired tools are no longer active coverage priorities. Some repaired paths were verified with disposable fixtures in this review. In particular, the large phone migration/retirement path should have retained fixture coverage before further refactoring.

**Decision:** add small, offline regression modules for the maintained tools, then selected live tests for CDP selectors, Android/MTP, GNOME, systemd, and container/image behavior. New permanent test files were not added during this review, following the repository preference.

## Retirement candidates — confirm use before deletion

- [.qdrant-initialized](../.qdrant-initialized) is an empty marker; the global ignore file mentions it. Confirm whether external tools still use it before removing it.
- [archive/viz.py](../archive/viz.py) is Python 2 code and fails Python 3 parsing. It is already archived; decide whether the repository should retain historical artifacts.
- [codexerrors.py](../codexerrors.py), [codextools.py](../codextools.py), [codextags.py](../codextags.py), and [agentlog.py](../agentlog.py) still overlap. They expose different contracts, so usage evidence is needed before further consolidation. `codexlist` has already been retired.
- [setup.bash](../setup.bash) contains many Windows/Cygwin-era aliases and one-off project commands. Archive by actual use rather than assuming all Windows support is obsolete.

## Verification evidence

### Retirement and shortcut follow-up

- `just verify`: **735 Python tests + 103 Node tests passed**, plus the offline AI Usage adapter/widget suite. No failures. Output: `/tmp/scripts-retire-verify.log`.
- All **16** focused clipboard tests passed, including direct conversion, the existing menu, failure preservation, X11/Wayland selection writes, and the dconf command.
- Ran the real shared converter on synthetic HTML; it produced `**Hello** [world](https://example.test/)` as expected. No real clipboard contents were read or changed.
- Updated only the live Ctrl+Alt+C command to `rofi/rofi-clip.sh --html-to-markdown`, read it back, and confirmed the binding remains `<Control><Alt>c`.
- Targeted Python syntax/correctness checks pass across the **78** remaining non-archived Python files. ShellCheck passes for `rofi/rofi-clip.sh` and `daily-activities`.

- Direct conversion and interactive-menu tests cover X11 and Wayland using mock clipboard/converter tools; failures preserve existing content and direct mode skips the menu.
- Archive moves preserve the six scripts byte-for-byte. Active callers and README links were checked; historical prompt specifications are retained.
- The earlier temporary fixture/metadata counts below describe the initial audit before retirement and are historical, not reruns of the archived commands.

### Initial audit, committed as `73d2169`

- `just verify`: **730 Python tests + 103 Node tests passed**, plus the offline AI Usage adapter/widget suite. No failures.
- All **17** standalone `--describe` smoke checks returned valid JSON successfully.
- **15** groups of disposable utility regressions passed, covering happy paths and preservation on failure. Git repositories and inputs were synthetic; external actions were mocked.
- Targeted static checks: `E9,F63,F7,F82,F401,F841,B006,B012,B023` passed across the 83 non-archived Python files, including extensionless commands.
- Shell/Fish/JavaScript syntax checks and ten structured configuration/asset parses passed. The apparent XML parse failure was diagnosed as the misnamed DOCX, which has since been deleted.
- `git diff --check` passed. The hadolint filename pattern was checked against `dev.dockerfile`, `Dockerfile`, and variant/nested names; the image itself was not built.

Initial-audit temporary evidence, available for this session:

- `/tmp/scripts-review-final-verify.log`: final canonical test output.
- `/tmp/scripts-review-fixtures.py` and `.log`: executable disposable regressions and results.
- `/tmp/scripts-review-describe.json`: CLI metadata smoke-test results.
- `/tmp/scripts-review-final-shellcheck.json`: remaining shell diagnostics with exact locations.

For reproduction, use `just verify` for the durable test gate. The temporary fixture runner declares its required packages in the review tool invocation rather than adding a test requirements file to this repository.
