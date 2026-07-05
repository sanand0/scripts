# backup_linkedin.py

## Observability, 03 Jul 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

<!-- Prompt via https://chatgpt.com/c/6a47117a-34c8-83ec-a808-115f56957951

On @LocalMCP take a look at ~/code/scripts/{backuplinkedin.py,backupwhatsapp.py} which use CDP to parse my LinkedIn and WhatsApp which have brittle DOMs - i.e. they change, and other stuff can go wrong.

I'd like to have them cache what an AI coding agent like Codex would need in the future to see if something's gone wrong, changed, or there are any opportunities for improvement.

What should I log in ~/.cache/sanand-scripts/{backupwhatsapp,backuplinkedin}/ for this and how should it be organized (e.g. monthly / yearly, ideally without subdirectories) so I can easily manually delete really old stuff?

Research AI agent observability best practices. Explore the DOM of these sites via CDP if required. Share a concise prompt I can use to steer Codex on what changes to make.

-->

Inspect `backuplinkedin.py` and `backupwhatsapp.py`. Add lightweight, local, privacy-conscious observability without changing their normal output files or CLI output format.

Use only the standard library plus existing Playwright/Typer dependencies.

Create flat caches under `~/.cache/sanand-scripts/{backuplinkedin,backupwhatsapp}/`:

- `latest.json`: atomic summary of the latest run.
- `YYYY-MM-runs.jsonl`: append-only events, grouped by `run_id`.
- `YYYY-MM-DDTHH-MM-SSZ-<6hex>-baseline.zip`: at most one successful structural baseline per month.
- `YYYY-MM-DDTHH-MM-SSZ-<6hex>-anomaly.zip`: on failures or suspicious results.
- Preserve WhatsApp’s existing `checked.json` separately as operational state.

Model each invocation as a trace with timed spans for CDP connection, page discovery/navigation, DOM validation, scanning, opening/expanding, scrolling, extraction, validation and writing. Log script/Git hash, runtime/browser versions, sanitized arguments, selector counts and fallback chosen, row counts, missing-field rates, scroll/click statistics, output before/after statistics, console/page/request errors, and exception type/message/stack.

Rich ZIPs should contain `manifest.json`, run events, a bounded redacted DOM outline and—when supported—a redacted AI-mode ARIA snapshot. Never persist cookies, tokens, headers, request/response bodies, URL query strings, WhatsApp message text, contact names or unredacted WhatsApp screenshots. Do not enable Playwright context tracing by default because the attached CDP context contains unrelated tabs.

Add anomaly rules, especially:

- LinkedIn found post containers but extracted zero/fewer post rows, core-field missing rates spike, or a selector candidate changes.
- WhatsApp selected/opened a chat but extracted zero messages despite existing local history or newer chat-list activity.
- Expected and opened conversation IDs differ.
- Parser DOM counts disagree, no history scroller is found unexpectedly, or all selected items are skipped.

Do not mark a WhatsApp conversation checked when zero messages may indicate a scraper/DOM failure.

Keep individual JSONL writes crash-resilient and bounded. Add tests for naming, redaction, anomaly classification and atomic `latest.json` updates. Run non-destructive live CDP diagnostics against the currently open LinkedIn and WhatsApp tabs and summarize the resulting cache files and any DOM assumptions discovered.

Run and test as required.

---

I deleted sanand-observability.py (and possibly the associated tests) accidentally. Recreate and test.

<!-- codex resume 019f25ce-634c-7532-b2b8-7df8ff2363e5 --yolo -->

## Initial script, 19 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly script `backup_linkedin.py` that allows sub-commands to use CDP to scrape and back up my LinkedIn data that are not exported by default.

Let's start with posts.

```bash
backup_linkedin.py posts --username sanand0
```

... should visit https://www.linkedin.com/in/sanand0/recent-activity/all/ on CDP 9222 and:

- Click on the "More" button of each post to copy the content, along with
  - links to all media (images, videos, documents) in the post.
  - when it was posted - converting 2h, 1d, 1w, etc. into best effort timestamps.
  - number of links, comments, reposts, impressions, etc.
  - timestamp of when the post was scraped.
  - click on the "comments" button to list all comments, including
    - who commented: name, profile link, description, type (e.g. verified, premium, etc.)
    - when they commented - converting 2h, 1d, 1w, etc. into best effort timestamps.
    - content of the comment - clicking on "more" if required
    - whether it was edited
    - how many reactions it received and of what types
    - number of replies to the comment if any
    - number of impressions if available
    - parent comment - if it is a comment to a comment
    - click on the load more comments button / see previous replies button until all comments are loaded.
- Scrolling down to repeat the above, loading more posts as it scrolls or clicking the "Show more results" button

Wait till relevant content is loaded, as you scroll, before scraping.
Use robust DOM selectors that are least likely to change with UI updates and add fallbacks where you think they'll be required.
Log errors/warnings for unexpected page structures, missing elements, etc. to help with debugging when LinkedIn updates their UI.
Review and apply best practices from other scripts like `backupwhatsapp.py`, etc.

Save the output as a JSONL file `/home/sanand/Documents/data/linkedin-posts.jsonl` with one JSON object per post or comment (use "type" to distinguish, include a parent id to identify which post a comment belongs to), containing all the scraped information.

When the script is run again, it should update or append new posts/comments to the same file without duplicating existing ones. Updates are required because statistics like number of reactions, comments, impressions, etc. can change over time. Even content can change if the post/comment is edited. Use post/comment IDs to check for duplicates.

Run this for 100 posts. Review the content and output and suggest improvements, e.g. what additional fields are easy to capture and are worth capturing, how to better handle timestamps, how to speed up the capture, how easy is it to capture who reposted and is it worth it, how easy is it to sort comments by recency rather than relevance and is it worth it, etc.

---

Copy the output to ./linkedin-posts.jsonl in the local directory and use that as the output going forward to test and ensure that (a) the output file can be anywhere and (b) will be updated in place rather than content getting deleted or duplicated.

Did the script capture all replies - e.g. "See previous replies" in comments, etc. Review the DOM and validate. If it didn't fix that before you re-run.

Review the DOM to see if there are any other useful pieces of information that need to be captured. Document them - no need to re-run. I'll guide you on which ones to prioritize.

---

Update the script to capture these additional fields:

- `analyticsUrl`
- `authorMiniProfileUrn`
- `commenterMiniProfileUrn`
- `reactionTypesVisible`
- `commenterDegree`
- `premiumVerifiedBadges`

Test on a sample and make sure it updates ./linkedin-posts.jsonl in place without duplication.

Tell me how to run it for all posts.

<!-- codex resume 019e401d-968d-7112-a82e-a2e6bf03edae --yolo -->

---

NOTE: I renamed `backup_linkedin.py` to `backuplinkedin.py` for consistency.
