# skilluse

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

skilluse.py doesn't detect the use of `vitest-dom` in the Codex session 6a545187-1e10-83ee-b084-871c4cf69da3 on 13 July, I think.
Maybe other recent sessions aren't being captured either.
It's also possible that it isn't capturing other skills' uses in Claude sessions.
Review, find what's missing, and fix it.

It's a slow script that streams --format text but waits till the end to generate --format json - which can take a few minutes. Factor that in.

---

This seems to report that the "interactions" skill was never used. But I think it might have been used in

~/.codex/sessions/2026/03/04/rollout-2026-03-04T10-43-01-019cb6ba-2f20-7583-9959-7f374f85458b.jsonl
~/.codex/sessions/2026/03/02/rollout-2026-03-02T15-37-13-019cad7a-d144-7bc2-aea6-a73841671826.jsonl

If that's so, are there similar gaps for other skills? Find and fix.

<!-- codex resume 019f6a2c-11b3-7e53-b69c-911b4ff0f788 --yolo -->
