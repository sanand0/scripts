# Test-suite diagnosis — 11 August 2026

<!-- codex resume 019ff07d-e257-72c0-b704-c1b1f4ce6daa -->

> **Follow-up completed:** `just test` now provides the canonical, lockfile-free test runner. The stale, paid-call, cache-isolation, dependency, and Playwright issues below have been repaired; the complete gate passes 239 tests.

## Executive summary

The reported command completed with **31 failed, 207 passed** (238 tests) in 28.14 seconds. The failures are seven clusters, not 31 independent defects.

- **No observed failure demonstrates that production code is wrong.** Twenty-four failures are caused by test-runner, environment, or isolation problems; seven are stale assertions or mocks.
- The largest cascade comes from one package-name typo: `--with frontmatter` must be `--with python-frontmatter`. The typo directly breaks 13 HTML-email tests and indirectly breaks five MCP tests by forcing uv to select an old FastMCP.
- Four local-browser tests need a matching Playwright Chromium installation.
- Two transcription tests incorrectly use the real home cache instead of a temporary test cache.
- Seven assertions/mocks are stale after intentional podcast and summarizer changes.
- The most urgent issue is not a failure: two summarizer tests have stale Gemini mocks after OpenAI became the default. They can make **three real, likely billable OpenAI requests per full suite run**, including one test that passes.

## How the suite should be run

The current command is understandable, but it is not a reliable suite definition:

1. There is no root `pyproject.toml`, lockfile, requirements file, `pytest.ini`, tox configuration, or equivalent test manifest.
2. Pytest does not consume the PEP 723 dependency blocks in imported scripts. Only the environment around pytest determines what can be imported.
3. `frontmatter` is the wrong distribution name. `htmlemail.py` and its test explicitly require `python-frontmatter`.
4. The command omits direct test dependencies such as Typer, orjson, markdownify, tenacity, Google client packages, and others. They happen to arrive transitively in the current Python 3.12 resolution. Running the same abbreviated dependency list on Python 3.14 caused six collection errors.
5. The dependency versions are not locked. A fresh resolution can silently change behavior.
6. The default interpreter was Python 3.12.3, although `mcpserver.py` declares Python `>=3.14`.

At minimum, replace:

```text
--with frontmatter
```

with:

```text
--with python-frontmatter
```

The canonical whole-suite runner is now:

```bash
just test
```

Each `tests/test_*.py` module has a focused `just test-*` recipe with its direct dependencies. Recipes use isolated, cached uv environments, avoiding both accidental transitive dependencies and a maintained test lockfile. Compatibility-sensitive Playwright and FastMCP versions are pinned in the `justfile`.

The summarizer recipes route OpenAI to a closed localhost endpoint as a fail-closed guard, while the tests mock the provider-neutral call and client constructor. The ChatGPT recipe verifies the pinned Chromium executable and installs it only when absent.

## Failure catalog

| Count | Tests | Classification | Diagnosis | Likely fix effort |
|---:|---|---|---|---|
| 13 | `tests/test_htmlemail.py` | Runner dependency error; code and tests right | `frontmatter==3.0.8` is a different PyPI project and has no `load`. The intended `python-frontmatter==1.3.0` does. | Trivial |
| 5 | `tests/test_mcpserver.py` Bash-tool tests | Cascading resolver error; code and tests right | Wrong `frontmatter` pins PyYAML 5.1. FastMCP 3.4.7 requires PyYAML 6.x, so uv backtracks to FastMCP 2.14.7, whose `ToolResult` lacks `is_error`. | Easy |
| 4 | `tests/test_chatgpt_cli.py` browser tests | Environment provisioning; code and tests likely right | Playwright 1.62 expects Chromium headless-shell revision 1234, which is not installed. Only older revisions are cached. | Easy–medium |
| 2 | `tests/test_transcribe_calls.py` chunk tests | Test isolation plus restricted environment; code right | Tests write the default cache under `~/.cache/sanand-scripts/...`; that path is read-only here and is shared state on a normal host. | Trivial |
| 2 | `tests/test_podcast.py` default-output tests | Stale tests; code right | Tests still require an always-timestamped name, contradicting the later explicit prompt to use `INPUT.mp3` unless it already exists. | Trivial |
| 3 | `tests/test_summarize_transcript.py` `process_file` tests | Stale tests; code right | Calls use the old positional signature. Added `provider` and `client` parameters shift a `set` into the `content_set` position, hence `set.meta_keys`. | Easy |
| 1 | `tests/test_summarize_transcript.py` prompt wording test | Brittle/stale test; current prompt intentional | It asserts fragments from an older prompt (`usually 0`, later-turn wording) that was deliberately replaced and subsequently benchmarked. | Trivial |
| 1 | `tests/test_summarize_blog_tags.py` worker/ledger test | Stale and unsafe mock; code right | Test mocks Gemini, but CLI default is now OpenAI, so the mock is bypassed and returned proposals differ. | Easy, urgent |

### 1. Wrong `frontmatter` package: 18 cascading failures

`htmlemail.py:6` and `tests/test_htmlemail.py:6` declare `python-frontmatter>=1.0.0`; `htmlemail.py:407` calls `frontmatter.load`. The user's command instead installs `frontmatter==3.0.8`, which exports the same module name but lacks that API. This causes the 13 HTML-email failures.

The same typo explains the apparently unrelated MCP failures:

```text
frontmatter 3.0.8 -> PyYAML == 5.1
FastMCP 3.4.7 server extra -> PyYAML >= 6.0, < 7
uv backtracks to FastMCP 2.14.7
FastMCP 2.14.7 ToolResult -> no is_error argument
```

`mcpserver.py:620-624` intentionally returns `ToolResult(..., is_error=...)`, matching the structured-error contract in `prompts/mcpserver.md`. With `python-frontmatter`, the shared environment resolves PyYAML 6.0.3 and FastMCP 3.4.7; the HTML-email and MCP suites pass **50/50**. FastMCP 3.4.0 is the first compatible release, so a later code fix should change the currently unbounded dependency to `fastmcp>=3.4,<4`. The focused test comment should also specify Python 3.14.

### 2. Missing Playwright browser: four failures

Four tests at `tests/test_chatgpt_cli.py:94-216` launch a real local Chromium process. They do not navigate to ChatGPT or submit anything; three use `page.set_content`, and the target-ID test uses a blank page. The Python Playwright package is installed, but its matching browser binary is not.

This is an environment failure, not an assertion or product-code failure. The durable answer is to pin Playwright and install its matching Chromium during test bootstrap/CI. Marking these tests (for example, `browser`) would let fast unit tests run separately and produce a clear preflight skip/error. A system Edge fallback is less reliable here because Edge's crash handler also needs a writable profile/config path.

### 3. Home-cache leakage: two failures

`transcribe_calls.py:38` defaults chunk cache state to the user's home directory. The failing tests at `tests/test_transcribe_calls.py:1112` and `:1248` construct otherwise-hermetic fake Gemini, ffmpeg, and pricing dependencies but do not set `TRANSCRIBE_CALLS_CACHE_DIR`. They fail when `write_cached_chunk` reaches the read-only real cache.

Setting the cache to a temporary directory made both tests pass (**2/2 in 0.58s**). The test fix is to set `TRANSCRIBE_CALLS_CACHE_DIR=tmp_path / "cache"`, as the neighboring resume-cache test already does. This also prevents cross-run cache hits and pollution on unrestricted machines.

### 4. Intentional contract changes with stale tests: six failures

The two podcast failures are stale. `prompts/podcast.md:15-25` explicitly says the default should be the Markdown basename with `.mp3`, adding a timestamp only on collision. Commit `48a095e` implements this in `podcast.py:108-114`; the old tests were not updated. Assert `script.mp3` and `weekly.notes.mp3`, and add a collision test for the timestamp fallback.

Three transcript-summary failures call `process_file` using its old positional layout. Commit `24423fe` added `provider` and `client` at `summarize.py:772-775` and updated production callers, but not these tests. Use keyword arguments and mock the provider-neutral `call_ai` boundary.

The fourth transcript-summary failure hard-codes old prompt prose. `prompts/summarize.md` and commits `266650d` and `24423fe` show intentional prompt replacement and later benchmarking. Test stable behavioral requirements or schema properties, not exact sentence fragments from an obsolete prompt.

### 5. Stale mocks that can incur API cost: one failure plus one passing test

Commit `24423fe` changed the summarizer's default provider to OpenAI (`summarize.py:855-911`). These tests still set a Gemini key and patch `call_gemini`/`google.genai.Client`, then invoke the CLI without `--provider gemini`:

- `test_summarize_merges_proposals_once_after_workers` processes two files and can make two real OpenAI calls. It fails because the real results do not match the fake `agent-memory` proposal.
- `test_summarize_dry_run_does_not_write_proposal_ledger` can make one real OpenAI call and still pass because it checks only exit status and absence of a written ledger.

The current environment has a configured OpenAI credential, so the exercised path was real and apparently succeeded. Broad and focused diagnostic runs in this investigation may therefore have incurred a small cost. The test output does not retain enough usage data to calculate it reliably.

Fix these first: either invoke explicitly with `--provider gemini` and keep the Gemini mock, or preferably mock `call_ai` and the active client construction so the test remains provider-neutral. Assert the emitted per-file status/result, not just exit code. Add a network-denial guard for unit tests so a missed mock fails before reaching a paid endpoint.

Also clarify the CLI contract: `summarize --dry-run` currently avoids writes but still performs paid inference. That may be intentional preview behavior, but it is surprising for a flag commonly understood to avoid paid side effects. Either document it prominently, add a no-inference planning mode, or change the behavior in a later task.

## API, network, privacy, and performance audit

- Podcast's Gemini HTTP test patches `httpx.post`.
- Transcript summarization normally uses fake clients; the stale blog-provider mocks above are the exception.
- Transcription tests inject a fake `google.genai` package and local `file://` pricing. They do not call Gemini.
- MCP upload tests patch `urlopen`; they do not contact OpenAI.
- Edge CDP HTTP/WebSocket tests are mocked.
- ChatGPT browser tests use only local HTML and blank pages; the CLI submission path is tested only with `--dry-run`.
- LinkedIn's cache CLI test is intended to remain offline, but a cache regression could fall through to the user's authenticated CDP browser. Mock `fetch_profile`/browser access or use an explicitly unreachable CDP endpoint to make this guarantee enforceable.
- Some integration tests spawn nested `uv run` commands. On a cold cache these can contact PyPI and repeatedly resolve unpinned PEP 723 dependencies. Lock/prewarm them, use uv offline mode after bootstrap, or call the CLI in-process when dependency resolution is not itself under test.
- The four ChatGPT tests launch a new browser each time. A session-scoped browser fixture could reduce runtime while retaining a fresh context/page per test.

## Recommended repair order

1. **Stop unintended paid calls:** repair both blog-summary mocks and add a network-denial guard.
2. **Fix the runner typo:** use `python-frontmatter`; this removes 18 failures at once.
3. **Isolate transcription caches:** point every subprocess test at `tmp_path`.
4. **Update stale assertions/calls:** podcast and summarizer tests only; production behavior is supported by prompts/history.
5. **Provision/mark browser tests:** pin Playwright plus Chromium and separate browser tests from the fast unit gate.
6. **Create a canonical suite runner:** use explicit Python 3.14 and direct per-module dependencies without a shared lockfile.
7. **Harden remaining external boundaries:** ensure LinkedIn cannot fall through to authenticated CDP and reduce nested uv resolution/network work.

## Verification performed

- Exact reported command: **31 failed, 207 passed, 1 warning in 28.14s**.
- Final safe gate with correct `python-frontmatter`, isolated transcription cache, browser tests excluded, and the eight stale/unsafe tests deselected: **218 passed, 8 deselected in 11.71s**.
- Correct `python-frontmatter` environment, excluding ChatGPT browser tests and isolating transcription cache: **7 failed, 219 passed in 25.87s**. These seven are the stale tests catalogued above.
- Correct shared dependency environment for HTML-email plus MCP: **50 passed**.
- MCP on Python 3.14 with FastMCP 3.4.7: **32 passed**; FastMCP 3.4.1 also passed all 32.
- Two transcription cache failures with a temporary cache: **2 passed in 0.58s**.
- ChatGPT CLI focused suite without the matching browser: **4 failed, 8 passed**.
- Complete direct dependency union on Python 3.14: **238 tests collected**.
- Implemented `just test` after repairs: **239 passed** (one new podcast collision regression test accounts for the increase).

No implementation or test code was changed during this diagnosis.
