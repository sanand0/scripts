# activities

## Include fish scripts, 18 May 2026

<!--

cd ~/code/scripts/
codex --model gpt-5.5 --config model_reasoning_effort=high

-->

I'd like to modify `activities.py` to also include `fish` CLI history via `history --show-time`, condensing the commands into a single line, whitespace-compacted and trimmed, semicolon-merged, truncated in the middle to a reasonable length suitable for AI agents to understand and consistent with the rest of `activities.py`.

Think about whether it will make it too noisy to include all commands. If so, based on my history, what would be most apt to include that will give AI agents a good understanding of my activities, maximizing signal over noise - e.g. a summary along with relevant details of some kind?

Before modifying activities.py, implement and run your approach and show me what it looks like for a few diversely active days. I'll guide based on that. THEN you can patch activities.py to include this.

---

The burst-level approach seems fine. Maybe 15-minute instead of 25-minute bursts?
Should we trim in the middle, or at least preserve the last command? You decide.
As for `DEFAULT_SOURCES` vs `--sources shell` I leave that to you.

Go ahead, implement and test.
Revise/patch existing ~/Documents/activities/*.tsv files to include shell as well.

<!-- codex resume 019e39fa-027a-7533-836f-b194365f8381 -->

## Make it repeatable, 14 May 2026

<!--

cd ~/code/scripts/
codex --model gpt-5.5 --config model_reasoning_effort=high

-->

Modify `activities.py` so that by default, it doesn't run for the current day, but runs for all pending days since the last run (or the last 7 days if there is no previous run) until yesterday.
This ensures that I can run it at any point to update it, and it doesn't update the current day which may be incomplete.

Also, fill up all the gaps in the activity logs - specifically between 2026-04-01.tsv and 2026-05-01.tsv.

<!-- codex resume 019e358b-20d2-7333-a841-70c8b40ce0c4 -->

## Initial script, 14 May 2026

<!--

cd ~/code/scripts/
codex --model gpt-5.5 --config model_reasoning_effort=high

-->

Create an `activities.py` that generates a daily activities report.
Each activity is one line in ~/Documents/activities/YYYY-MM-DD.tsv. It begins with easy-to-parse metadata comment(s):

```
# TZ=+0800
# ...
```

and the following fields:

- Time, e.g. 10:30 am
- Type (of activity), e.g. "email", "meeting", "chat", "commit", "code-prompt", ...
- Activity, i.e. a short description summarizing the activity

Create it as follows:

- Use `gws` CLI to get calendar events and create a description using the most relevant metadata (e.g. title, attendees, trimmed description) for each event.
- Use `gws` CLI to get sent emails and create a description using the most relevant metadata (e.g. subject, recipients, trimmed body) for each email.
- Scan children of `~/code/` for all commits and add 1-line descriptions for each commit (e.g. "~/code/repo: trimmed commit message").
  - See ~/code/summary.py for how best to do this efficiently
  - See GitHub commits as well and de-duplicate: gh search commits --author "@me" --sort committer-date --order desc --limit ...
- Scan my Edge browser history and add 1-line descriptions for each URL visited (e.g. title, URL). See browser_history.py for how to do this efficiently.
- Scan my coding agent prompts and add 1-line descriptions for each prompt (e.g. directory, trimmed version of the prompt). See agentlog.py

In the future (not now), I will be adding:

- Chat messages I send
- Prompts I give to online AI agents (ChatGPT, etc.)
- Location history
- Fitness activities, etc.

The objective is to pass my daily activities (individually, aggregated) to an AI agent for analysis, to find out what I accomplished in a day/week/month, what aligns with my goals, etc. Keeping that lens in mind, plan like an expert. In this context, first think about:

- What patterns would an expert in this field check / recognize that beginners would miss?
- What questions would an expert ask that a beginner would not know to?
- What problems / failures would an expert anticipate that beginners may not be aware of?
- What powerful & relevant mental models would an expert apply in this context?

Use this thought process to guide you on:

- Should we break down the description into more granular components? What would they be that are common across types of activities?
- What should the activity include / exclude? I've given my suggestions - yours might be better.
- How long should "trimmed" be? What context would a coding agent need, what would make this unweildy, would this vary by source, would we need different structures for the sources, .... Use your judgment to find the right balance.

Analyze the sources first, run a scan, create a plan, and ask me if you have any questions or permissions. No need to implement just yet.

---

Keep the comments simple. TZ, GENERATED_AT will suffice. DATE is inferrable from the filename. SCHEMA, SOURCES, can be skipped.
Use the time zone of my system - I travel a lot and "day" will mean the local day, not a fixed time zone.

I've updated the gws access - you should be able to access sent items.

On your questions:

1. Yes, include a header row.
2. Yes, Include personal calendar blocks with calendar type - same as other calendar events.
3. Yes, implementation may run live gws reads, refresh token cache, etc.
4. Use browsing_history.py to extract browsing history first and then use ~/Documents/data/browsing-history.db.

Try implementing this by creating a scaffold and adding sources incrementally.
Design it so that adding new sources later is easy, and coding agents can understand how to do that well.
Generate it for a few days and let me see the output.
Feel free to use sub-agents for token-efficiency.

---

How can the Activity column be improved?

Use `copilot` (/home/sanand/.local/share/mise/installs/node/25.9.0/bin/copilot) with Claude 4.6 Sonnet as a model to review these three activities (together). Ask it to infer what I did that day - the most significant outcomes, accomplishments, etc. giving it whatever context is required. Look at the answer, compare that against the reality, and use this to identify how best the Activity can be improved to better capture what's important.

Remember: you just have 3 day's worth of activity - so don't overfit to these examples. Try and find general ways to do this.

Re-create the activities for another batch of three days and a batch of 1 week. Pass the revised output to `copilot` with Claude 4.6 Sonnet to see if it does better. Revise again.

---

Run the second copilot review. Send it the full batch of 1 week's activities. Revise based on what you learn from that. Regenerate for the week.

---

Replace `TZ=...` with `DATE=` with the format "Thu, 14 May 2026 +0800"
Make collecting code-prompt faster.
Run for all of May 2026 and check if all is OK.

<!-- codex resume 019e2426-cc66-7382-bac7-aeae16f2c475 -->
