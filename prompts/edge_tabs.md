# edge

- Originally created by ~/code/private-research/edge-tabs/
- Then migrated to ~/code/scripts/edge_tabs.py

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
