# Prompts

## Initial script, 29 Jun 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Create an agent friendly CLI `backuptwitter.py` that uses `uvx twitter-cli` or the Python API of the package (whichever is easier) to back up tweets.

For now, I want to back up the result of `uvx --from twitter-cli twitter list 1778746851312783449` into `~/Documents/twitter/list-genai/`.
In the future, I may add other lists, searchers, people, etc. so plan for easy extensibility, e.g. via a dict.

The output should be a weekly JSON file in the form `~/Documents/twitter/list-genai/2026-06-28.json`. The date should always be a Sunday. All tweets between Sunday 12 AM UTC (i.e. Saturday-Sunday boundary) from the previous week should be in this file.

It should also create a corresponding `.md` file, e.g. `~/Documents/twitter/list-genai/2026-06-28.md` that contains the tweets in a human-readable format. Follow the implementation in `twittermarkdown.py` for this. The Markdown file should also resolve any t.co redirects - see `twitterredirect.py` for how to do this.

Later, I will be deleting `twittermarkdown.py` and `twitterredirect.py` - so make sure `backuptwitter.py` is self-contained and does not depend on them.

Make sure this script is compact and maintainable.

Run and test for a few weeks to ensure it works correctly.

When run without arguments, it should back up the most recent week, i.e. if today is 29 Jun 2026, it should create `2026-06-28.*` - the most recent Sunday's files.

--- <!-- steering -->

Make sure the `uv --from twitter-cli ...` runs with `~/Documents/twitter` as the working directory, so that the `config.yaml` is picked up from there.

---

Try finding ways of fetching older tweets (e.g. by updating the config) and see if you are able to back-fill the last 2 weeks. If it's proving hard or will involve complex workarounds, skip.

---

Also backup up people in the same way. The `@` before the folder name can indicate people.

- @petergostev
- @emollick
- @karpathy
- @simonw
- @sama
- @DarioAmodei
- @demishassabis
- @charliemarsh
- @ch402

Run for the last 3 weeks.

---

Try now?

---

Ensure that `backuptwitter.py` isn't harmful when re-run. For example:

- If I run it within a few minutes, hours, or days, it should know that it needn't update things from last week because they were already updated, and nothing new could have happened in the past.
- If I ask for an update for THIS week, i.e. 5 July 2026, it should fetch all the latest tweets and store it - but only since the last tweet it fetched
- If I ask for an update again next week, it should check the date of the last tweet it fetched and only fetch tweets since then - that too, only if required.

If it helps, the JSON can contain some additional metadata, e.g. when it was last run, etc.

In other words, sensibly minimize the number of tweets fetched and stored, merging sensibly, while ensuring that nothing is missed, lost, or duplicated.

---

When I ran it, it didn't fetch @simonw, etc - which are still incomplete. Factor that in. Completion means everything for that last week is complete. Skip what's done quickly, but continue what's pending.

<!-- codex resume 019f1116-788a-7eb3-9337-c5d80003d0df --yolo -->
