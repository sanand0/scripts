# Email AI

## Revise to use online email, 09 Jul 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Revise `emailai` to use `gws` directly rather than `~/Documents/data/...` to ensure that it accesses the latest emails. Use this as an opportunity to simplify the script and remove anything unnecessary.

<!-- codex resume 019f4752-32af-70a1-af8b-b7800be79be6 -->

## Create script, 08 Jul 2026

<!--
cd ~/code/scripts
codex --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly uv Python script titled `emailai` that takes the arguments, e.g.

```
emailai review "john doe" 2026-06
```

... and

- Finds the first line in `~/Documents/data/s.anand@straive.com/mail*.jsonl` that matches ALL the arguments as case-insensitive phrases (e.g. "john doe" matches "John Doe" but not "doe john")
- Fetches the email + attachments + past emails in the thread using the `gws` CLI
- Creates a new prompt asking it to create a reply to the email by concatenating a standard prompt with the email context. Include the phrase "Use @LocalMCP as required" in the prompt. Make the standard prompt easy for me to edit in the script.
- Opens ChatGPT in the browser (see `chatgpt`, delegate to a system call if appropriate), pastes the prompt + attachments if any and exits (without running ChatGPT)
- In the future, I will likely ask to submit to ChatGPT - i.e. press the submit button. I will likely ask for a similar feature for Claude instead of ChatGPT. Make sure the script is designed so I can pass a flag to choose.

Run and test with the email IDs 19f3b8b815819f2c and 19f3d7a0188cb817 to see if the files and text are sent to ChatGPT - but don't submit to ChatGPT until I tell you to.

<!-- codex resume 019f41b3-1a3a-73b2-b6cc-f20ff140efe7 -->
