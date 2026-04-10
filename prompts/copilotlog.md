# Prompts

<!--

cd ~/code/scripts/
dev.sh
codex --yolo --model gpt-5.4 --config model_reasoning_effort=medium

-->

## Refactor

Currently, ./claudelog helps list an read Claude logs.

Create a ./copilotlog that does the same for GitHub Copilot logs from ~/.copilot/

The information and format of claudelog is fine - but adding colors to `copilotlog ls` (in case the output is not piped) would help make the output more readable.

We already have a ./copilotlog.jq and ./copilotlist that don't quite do the job. Read but feel free to ignore what's irrelevant.

The Copilot logs are stored for a month in a SQLite DB but older history is available in the logs. Prefer the DB and use the logs only for the rest of the history.

Do not edit anything in ~/.copilot/ - only read from it.

Run and test.

---

Similarly, synthesize codexlist and codexlog.jq into a single codexlog that lists sessions and converts to Markdown.

There will be overlap in code between codexlog, copilotlog, and claudelog.
Rewrite to maximize reuse.
Rewrite to standardize interface and features across all three tools.
Move all common code into a shared Python script in this directory. Ensure that it gets imported wherever the script is run from.

Run and test.

<!-- codex resume 019d4779-5f10-75b2-bf71-38e9d72454b1 -->

## Optimize

<!-- copilot --yolo --model gpt-5.4 --effort medium -->

codexlog ls is VERY slow. How can we have it send responses as it reads instead of processing everything?
The same principle applies for `copilotlog ls` and `claudelog ls`, too.
Benchmark and optimize whatever takes more than a second to start responding.
Run and test.

---

Wow - almost the entire code is in sessionlog.py. So let's do this.
Rename `sessionlog.py to` `agentlog.py`.
Make sure `agentlog.py claude ls` etc. work from the CLI.
Modify tests accordingly.
Then I will delete codexlog, claudelog and copilotlog and just use agentlog.py instead.

--- <!-- 06 Apr 2026 -->

Add a `--kind user,system` filter to `agentlog.py`. Any combination of "kind" is possible: user, assistant, system, any future value.
`--kind user --kind system` should do the same.

---

Allow `agentlog.py md` to accept multiple session IDs and combine them into a single Markdown output.

Also allow `agentlog.py ls --search REGEX` to only list sessions that match the regex anywhere in their content.

Keep changes minimal and run and test.

---

This is too slow: `agentlog.py codex ls --search auth`. Make sure its faster AND that it streams results.

Modify --search so that `/auth./i` does a case-insensitive regex search for "auth." but `--search /auth./` does a case-sensitive regex search for "auth" and "--search auth." does a fast substring search for "auth." (case-insensitive).

---

`--search` should output (instead of the current user content) only lines with matching content (indented as they are currently). If the lines are too long, truncate with ellipses to fit in 80 characters (customizable with `--width`). Make sure this is fast, too.

<!-- copilot --resume=5fa5faac-c23e-4ba4-8e0f-f7e312080ca2 -->
