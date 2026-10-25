# backupchatgpt.py

## Revisions, 23 Oct 2026

A few changes:

- If the conversation ID / URL is already open in the browser and accessible via CDP, re-use that tab by scrolling instead of opening a new one. That saves requests.

## Initial build, 19 Oct 2026

<!--
cd ~/code/scripts
dev.sh -p ~/code/tools,~/Documents/data -- codex --yolo --model gpt-6.1-sol --config model_reasoning_effort=medium
-->
<!-- Source: https://chatgpt.com/c/6ad58a38-3bcc-83ec-bb30-487b5553de6e -->

Implement `~/code/scripts/backupchatgpt.py`, modeled on `backupwhatsapp.py`.

First inspect `scripts/AGENTS.md`, `backupwhatsapp.py`, and `tools/aiscrapers/{chatgptscraper.js,chatgpt-sidebar-scraper.js,aiscrapers.test.js}`. Plan first, test on a small input, then implement.

**Critical requirement:** Reuse the existing JavaScript scrapers directly through CDP (prefer background activity like backupwhatsapp.py rather than bringing the window / tab into focus), loading their source from the sibling `tools` repo on every run. Do not copy, translate, vendor, or reimplement the scraping logic in Python. Make minimal refactors to the bookmarklets only if necessary, preserving their behavior and regression tests.

Requirements:

- Use an existing authenticated Edge CDP session on port 9222. Open only an automation-owned tab; do not disturb existing tabs. Fail clearly if CDP or authentication is unavailable.
- Discover conversation URLs using the existing sidebar scraper. Scroll to reveal virtualized links, deduplicate by immutable conversation ID, and persist discovered URLs across runs.
- Visit new/changed conversations and periodically recheck known ones. Use `chatgptscraper.captureMessages()` while scrolling through virtualized history. Preserve full message IDs, roles, timestamps, Markdown, and rich `parts`.
- Save under `~/Documents/data/chatgpt/`, with per-conversation JSONL as the canonical store and Markdown derived using `chatgptscraper.messagesToMarkdown()`. Use stable IDs, content hashes, atomic writes, and non-destructive revision history. Re-runs must be idempotent.
- Provide daily incremental mode, bounded rescan, `--limit`, `--conversation`, `--name`, `--dry-run`, `--cdp-url`, `--out-dir`, `--format jsonl`, and `--describe`. Follow the script's Typer/uv/PEP-723 conventions and reuse existing observability.
- Detect suspiciously incomplete extractions, unstable message IDs, scrolling plateaus, and missing chats. Never silently mark incomplete scans as complete or overwrite valid backups with empty results.
- Do not claim exhaustive history coverage from sidebar discovery. Document the limitations and how an official ChatGPT export plus the existing `chatgpt-to-markdown` tool could reconcile omissions.

Test the existing scraper fixtures, then approximately five diverse live chats: short, long, edited, project, and old/archived. Verify message counts, ordering, no duplication, resume after interruption, and JSONL/Markdown consistency. Verify that changing JavaScript in the `tools` checkout changes Python extraction on the next run without edits to `scripts`.

Keep it minimal. Report any unresolved coverage gaps rather than introducing undocumented ChatGPT APIs as dependencies.

--- <!-- steering -->

Keep in mind that the bookmarklet does not scroll to reveal all messages - you might need to incorporate that in backupchatgpt.py

--- <!-- steering -->

Also keep in mind that ChatGPT might refuse to load chat lists or chats if we open too many too frequently.
Make sure we don't make redundant requests.
Make sure we flag what's incomplete so that we can re-run later.
Make sure we don't mark something incomplete or missing as complete.

--- <!-- steering -->

I might rename chat messages (but their IDs = URLs won't change). Handle this gracefully. I'd like to make sure that the file names match the latest titles and also to never lose information.

---

<!--
cd ~/code/scripts
dev.sh -p ~/code,~/Documents/ -- codex --yolo resume 01a15280-cbce-7fe3-8e1f-f9829805973c
-->

Here's another thought. On ~/Documents/chatgpt/ I dump the exports from ChatGPT. Maybe we could use the same folder and save things as Markdown there, using the same convention for filenames? Later on, when I re-export from ChatGPT (I use ~/code/chatgpt-to-markdown/ for this) it will just overwrite the Markdown files with the exported content. (The exported content might be a little bit out of date, but that's OK for now.)

What do you think? Any design problems you foresee that can't easily be solved? If not, try implementing this non-destructively (i.e. don't lose existing information), test if it's fine, and let me know if you need help or if I need to do anything or be careful or aware of anything.

---

I ran this. Check the output. Based on that, are there any clear improvements that need to be made?

A few points from me:

The log reports ID - number - True / False. It's not clear what these mean. Make them clearer with concise labels, e.g. ID=$ID ... (you've done this with direction=-1, step=0, etc. but doing this for the headers will help.)
It helps to get a sense of progress, e.g. scanning ID=... (1/10) so I know how long to wait for.
It also helps to get a sense of time taken and number of conversation turns, prompts, file size, e.g. Publishing local Markdown for ID=... (2m 30s, 3 prompts, 230 KB).
It would also help to log any details from scans to allow investigation of failures in the future - you may decide what's relevant.

BTW, ~/code/scripts/ might be write-able - check.

---

Chats aren't immutable but if a user prompt or ChatGPT output is the same, I think it's safe to assume that all previous content is identical.
Can this be used to speed up updating EDITS to existing chats? [Weekly Market Prediictions Request](https://chatgpt.com/c/6a364e7f-0494-83ee-9dcc-22e584767cbe) is a great example of this. It took a 3m49s to capture.

But also keep in mind that I'll be updating several old chats - so when these appear near the top of the list, it IS worth checking to see what's changed. You're probably already doing that.

Logging improvements:
For direction, it'll help to use "direction=up" and "direction=dn" instead of "down" - so that the logs are aligned.
For step, might be good to use step=000/300, captured=007, elapsed=00:00:30, etc., again - to ensure that logs align.
No need to repeat history ID=... on each line when "Scanning ID=..." mentions that in the first place.

The last scan stopped with the below. Let's leave the window open in such cases - so that I can inspect and see what went wrong. Also report how many were completed and are pending, so that I can make a decision on whether and when to re-run.

Incomplete ID=6a87d052-1948-83ee-a2a2-fd7e8304d2e5 (3/20) stage=validation completed=2 unattempted=17 elapsed=15s logs=/home/sanand/.cache/sanand-scripts/backupchatgpt/2026-10-runs.jsonl
backupchatgpt: Suspiciously incomplete roles/history

Also, is there merit in waiting longer?
Or is it better to just let me run the script again later?

---

I ran backupchatgpt.py.
Check https://chatgpt.com/c/6ad050ce-c694-83ec-8847-2b0a3b928a2f
It just stopped - and the tab is open now.
What happened?

Also, when this happens, does it make sense to maybe skip and proceed with other chats?
How many chats are pending? Does "Selected conversations=20 known=241 skipped=221" mean that of the scanned 241, only 20 need to be scanned / backed up?

---

OK, improve as you suggested

--- <!-- steering -->

Be careful of chats that may still be running and make sure you don't stop them

<!-- NOTES

- [backupchatgpt.py](backupchatgpt.py) backs up rendered ChatGPT conversations through authenticated Edge CDP at port 9222. It creates/closes only its own background tab and loads the sibling `../tools/aiscrapers/{chatgptscraper,chatgpt-sidebar-scraper}.js` directly on each page. Python drives scrolling; JavaScript captures, orders, and renders messages.
  - Daily: `uv run backupchatgpt.py --limit 20 --format jsonl`. Sidebar discovery is cached for 15 minutes to catch old chats moving up the list during the day. New/title-changed/rising chats get priority, including chats already checked today; falling ranks alone do not trigger a recheck. Other known chats rotate oldest-check first within the limit. Changes without a title/rank signal are found by daily rechecks or an explicit `--conversation` check. No content API is used. Navigation is spaced by at least 10 seconds, including after switching automation tabs. Chat-local extraction failures and isolated conversation load timeouts stay pending while the batch continues. Two consecutive conversation load failures (timeouts or an explicit “Could not load this ChatGPT conversation” error) stop further requests; a successfully loaded chat resets that count, even if validation later fails. Authentication, rate-limit/challenge, CDP, write, and unexpected errors stop immediately. No automatic navigation retries.
  - Weekly bounded refresh: `uv run backupchatgpt.py --rescan --limit 5`. `--rescan` disables incremental anchors and traverses the full rendered history; combine it with `--conversation URL` to audit one chat. `--scroll-steps 300` bounds each direction; reaching a budget or plateau is incomplete, never successful. `--name SUBSTRING` filters titles. `--dry-run` extracts and validates without changing backups/discovery state; observability logs still record the attempt.
  - Retry/add an omitted chat: `uv run backupchatgpt.py --conversation 'https://chatgpt.com/c/UUID' --format jsonl` (repeatable; project `/g/.../c/UUID` URLs also work). Explicit URLs skip sidebar discovery and bypass the daily schedule/retry delay. Otherwise failed chats wait at least 15 minutes before retrying. Already committed chats survive interruption; an interrupted/pending chat is scanned again from the beginning.
  - Files: `~/Documents/data/chatgpt/Title [UUID].jsonl` is canonical, with scraper fields (`id`, `role`, Markdown `content`, optional DOM `timestamp` and rich `parts`), `conversationId`, exact scraper `conversation` metadata (full title, date, final redirected source URL), and a SHA-256 `contentHash`. `.md` is derived by the JavaScript formatter with a stable export date. Titles are sanitized for filenames, with full titles retained in Markdown/state. Successful rechecks rename files to the latest title. Prior JSONL/Markdown snapshots live under `.revisions/UUID/`; writes are atomic per file, and replay repairs an interrupted pair. Empty results, positional IDs, unexplained missing prior IDs, conflicting order, streaming, and scroll gaps cannot replace valid backups. A changed suffix after a confirmed incremental anchor can replace the active branch, with the prior branch archived first. Without an anchor, the full-scan safeguards still apply and missing IDs require reconciliation. Failed captures are retained separately under `.incomplete/UUID/` with their error reason and never treated as canonical backups.
  - State/logs: `~/.cache/sanand-scripts/backupchatgpt/` contains monthly `YYYY-MM-runs.jsonl`, `latest.json`, and per-output-directory `catalog.json`/`discovery.json`. Catalog entries retain URLs, the last successful check, pending attempts, and error reasons. A pending attempt never advances its successful check date. An interrupted discovery remains flagged. JSONL stdout includes conversation summaries and a final run record indicating partial/incomplete coverage. A chat absent from a sidebar scan is only **not observed**, never deleted or marked successfully checked.
  - Incremental updates: for an existing backup, start at the bottom, capture the tail, and scroll up only until its oldest captured message matches a saved message by full ID, role, Markdown, and rich parts. Confirm the match over stable captures, reuse the earlier prefix, and archive the old snapshot before replacing an edited suffix. This uses the assumption that the prefix before an unchanged message is unchanged; independent earlier edits that preserve later IDs/content require `--rescan`. If no anchor matches, traverse back to the top and apply the full-scan guards. Captures made before prompt expansion was verified get a full traversal on their next check before their prefixes can be reused. JavaScript still performs all extraction and ordering.
  - Progress: text output labels `ID`, position/total, `messages`, `prompts`, `elapsed`, Markdown size, `canonical=updated|unchanged`, and `shared=updated|unchanged|disabled`. Messages count individual user/assistant messages; prompts count user messages. Selection logs distinguish `known`, `due` within the current filters, `deferred_limit` (eligible chats beyond `--limit`), `cooldown` (failed chats waiting 15 minutes), `not_due`, and `filtered`. A selected batch of 20 does not imply only 20 chats need backups. Scroll lines use `direction=up|dn`, `step=000/300`, `captured=007`, and `elapsed=00:00:30`; result rows distinguish captured versus reused messages. Publication logs include counts and size, and `--format jsonl` adds exact byte sizes and millisecond durations. Existing JSONL `changed` still means private JSONL/Markdown changed; `shared_status` describes the shared Markdown separately.
  - Diagnostics: events record conversation starts, active stage/position, navigation readiness/counts/challenge flags, scroll geometry and boundaries, anomalous IDs, validation counts, and loaded JavaScript hashes. Python script path/hash are also retained to identify the implementation used by each run. They contain no conversation text/HTML or credentials. `latest.json` identifies a failed ID, completed/unattempted counts, stage, and timing; incomplete-capture sidecars include that context and run ID. The private archive's `.backupchatgpt-state` marker pins its cache namespace across host/container home aliases; keep it with the archive when moving between mounts. Before each capture, the owned tab unfolds only user-prompt “Show more” controls; generation controls, assistant reasoning, and existing user tabs are untouched. A prompt that remains collapsed stays incomplete. Expansion counts are logged, and the confirmed scraper snapshot is used for final validation so a later collapsed remount cannot replace full text. Readiness uses the JavaScript scraper rather than assuming every reply has a text block; generated-image-only replies retain their message IDs and image parts. A chat-local failure keeps its automation tab open in the background, then continues in a fresh owned tab. Active generation is deferred without clicking Stop, navigating that tab away, or publishing unfinished content. Fatal errors also retain the current tab. `inspection_tabs` lists retained targets in `latest.json`; `inspection_target_id`/`inspection_url` identify the latest. Close inspection tabs manually; idle successful tabs are closed. The CLI exits nonzero after any deferred/failed chat, even when the rest of the batch succeeds. Final summaries report `completed`, `failed`, `unattempted`, and `due_remaining` across the known catalogue. `failures` retains each incomplete ID/stage/reason. `pending_count` (text `pending`) includes the failed and unattempted chats in this selection; `flagged_pending_count` (text `flagged_pending`) counts all known chats explicitly flagged incomplete. No automatic navigation retries were added. Waiting is bounded by the existing load/settling checks; persistent missing content remains incomplete for later inspection/retry.
  - Coverage: the sidebar is **not an exhaustive history inventory**. History-load errors, virtualized links, archived chats, and project lists can hide conversations. A validated chat covers only the current rendered branch, using either observed scroll boundaries or a matched saved prefix plus the rendered tail; unloaded turns, in-progress fragments without stable IDs, Canvas/editor lines, closed previews, attachments, and widgets may be unavailable. No missing timestamps are invented. Renamed chats outside the observed sidebar are renamed locally when next visited.
  - Reconciliation: periodically request an [official ChatGPT data export](https://help.openai.com/en/articles/7260999), retain its ZIP/JSON unchanged, and use the existing `chatgpt-to-markdown` converter for a separate readable archive. Compare exported conversation IDs and message IDs/counts with these backups; explicitly visit missing URLs or retain export-only conversations/branches separately. Never replace rich JSONL with converted Markdown. Export availability/contents depend on the account/workspace; inspect what it contains. The converter checkout is not mounted here, so its invocation was not verified.

-->

<!-- codex resume 01a15280-cbce-7fe3-8e1f-f9829805973c --yolo -->
