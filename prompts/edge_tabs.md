# edge_tab.py

Originally created by ~/code/private-research/edge-tabs/

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
