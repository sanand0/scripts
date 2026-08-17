# edge

- Originally created by ~/code/private-research/edge-tabs/
- Then migrated to ~/code/scripts/edge_tabs.py

## Contents filter, 18 Aug 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Update `~/code/scripts/edge` so that `edge contents google.com` will filter tabs whose URL or title match `google.com` and only return the contents for those.
Update tests.

<!-- codex resume 01a011e2-9cf0-71c0-bc81-cb4847ebe886 -->

## Contents, 17 Aug 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->
<!-- Source: https://chatgpt.com/c/6a831414-5fec-83ee-bc2d-39df6f5c71c4 -->

Update `~/code/scripts/edge` to add:

```bash
edge contents [--wake] [--cdp-url URL]
```

It should output agent-friendly JSON containing every Edge tab that is currently live/non-sleeping, with roughly:

```json
{"window": ..., "index": ..., "title": ..., "url": ..., "active": ..., "sleeping": ..., "content": "...Markdown..."}
```

Reuse the existing SNSS tab parsing, `cdp_tab_ids()`, `tab_html()`, and `html_to_markdown()` machinery. Prefer direct Chrome DevTools Protocol WebSockets, using `~/code/scripts/backupwhatsapp.py` as the model for clean WebSocket/CDP handling.

Requirements:

- Default: skip sleeping/discarded tabs rather than waking them.
- `--wake`: wake sleeping tabs, wait until usable, then extract their content.
- Determine sleeping/discarded status robustly from CDP/Edge state where possible; investigate `Target.getTargets`, `embedderData`, etc. before using absence of a page target as a heuristic.
- Prefer `Target.activateTarget` or another non-destructive wake mechanism; do not reload pages unnecessarily.
- Extract readable Markdown or text, not raw HTML.
- Include an `error` field per tab if extraction fails rather than failing the whole command.
- Enumerate targets once and use a small amount of concurrency rather than reconnecting serially for every tab.
- Keep `--cdp-url`, defaulting consistently with existing commands.
- Keep the implementation small and reuse/refactor existing functions rather than duplicating CDP code.
- Write failing tests first, then implement and verify.

<!-- codex resume 01a0100f-5cdd-7aa0-ac4b-cc4c38846896 --yolo -->

## Cookies, 11 Aug 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Update `~/code/scripts/edge` with a minimal `cookies` subcommand.

- `edge cookies google.com` returns all cookies whose domain is `google.com` or any subdomain such as `.google.com`, `accounts.google.com`, etc.
- `edge cookies https://www.linkedin.com` and `edge cookies www.linkedin.com` should more or less be equivalent to `edge cookies linkedin.com` (i.e. subset of cookies for the domain and its subdomains and protocol - if that's the case).
- Use the existing Edge CDP connection; do not read/decrypt the browser cookie database directly.
- Fetch cookies via CDP (`Storage.getCookies` is fine), then filter by parent domain. Or any more efficient mechanism is fine, too. Benchmark.
- Default output: curl-compatible cookie string, e.g. `name1=value1; name2=value2`.
- `edge cookies google.com --json` returns the matching cookie objects as JSON.
- Keep the implementation small and consistent with the existing script's style and CLI conventions. Preserve all existing behavior.
- Test it against at least one domain with cookies and show the commands/results.

<!-- codex resume 019ff19f-43a9-7922-8168-70923eb4c959 -->

## Switch profile, 17 Jul 2026

<!--
cd ~/code/scripts
dev.sh -- codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

In `edge`, allow multiple profiles to be specified, e.g. `--profile ~/.config/microsoft-edge-cdp/ --profile ~/.config/microsoft-edge/`.
The above should be the default.
`edge tabs` should show windows only from open browsers, e.g. if the browser with a profile is not running, it should not show any windows from that profile.
`edge md` should search across all profiles, and if there are multiple matches, list all matches with the profile name in the output.

<!-- codex resume 019f6eb8-f5f8-7783-96c6-3d91f7a89f43 --yolo -->

Modify `rofi-chrome-tabs.sh` to use `edge` instead of CDP

## Migrate to edge subcommands, 13 Jul 2026

<!--
cd ~/code/scripts
dev.sh -p ~/code/tools:ro -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Rewrite `edge_tabs.py` as `edge` with a `tabs` subcommand. `edge tabs` should behave exactly like the current `edge_tabs.py`.
Also rename `test_edge_tabs.py` to `test_edge.py`.
Revise daily-activities, setup.fish accordingly.

Add a sub-command `edge md` that extracts a specific tab as Markdown. Match in URL, title, or tab group name - case insensitive, partial match. If there are multiple matches, list all matches (title, tab group, URL) and exit. If there's only one match, output the main content of that tab as Markdown. Use ~/code/tools/page2md/ as inspiration for Markdown conversion - improving what you need, based on best practices. `edge md` may assume CDP on localhost:9222 where required.

Add tests first. Then run and test.

---

Test on a few diverse tabs from different domains (sorted by frequency) to ensure that you have captured the full relevant contents. For example: chatgpt.com, claude.ai, gemini.google.com, github.com, anthropic.com, openai.com, claude.com, x.com, etc. It's OK to skip primevideo.com, whatsapp.com, youtube.com, mail.google.com, etc.

--- <!--steering -->

Don't hard-code for sites. Keep it generic. It's OK to have extra content rather than miss important things.

---

If there are multiple CLI arguments, e.g. `edge md "phrase 1" "phrase 2" ...` then, if there are multiple matches for ANY of these, list all matches under the phrases with multiple matches, and exit. If there is only one match for ALL of these, output the main content of each of those tabs as Markdown, separated appropriately, with title, URL, and tab group name (if any) mentioned at the top of each tab's Markdown output.

---

If a phrase matches a tab group name fully (case-insensitive), then `edge md "group name"` should output the contents of all tabs in that group in order. Multiple group names, mixing group names with phrases/URLs, etc. is allowed.

--- <!-- steering -->

If there are any opportunities to simplify and shorten the code, making it more readable in the process, feel free. Keep things simple, short, and maintainable.

<!-- codex resume 019f593a-898f-7193-8935-d8abf4e10d42 --yolo -->

## Add group, pin, 12 Jul 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

In `edge_tabs.py`:

Is it possible to find out the name of the tab group the window is under?
Only if yes, add that as a field in the JSON output, suffix (in brackets) to the text output.

Is it possible to find out if a tab is pinned?
Only if yes, add that as a field in the JSON output, prefix `[PIN]` to the text output.

<!-- codex resume 019f5480-2f88-7543-be64-47460c00b68c --yolo -->

## Add timestamp, 05 Jul 2026

```bash
cd ~/code/scripts/
dev.sh -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium exec "Update edge_tabs.py to include a top level timestamp with the current time in UTC ISO time."
```
