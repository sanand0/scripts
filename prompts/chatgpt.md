# chatgpt

## Wait for response, 26 Jun 2026

<!--
cd ~/code/scripts/
dev.sh -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Minimally add an option `--temporary` to `chatgpt` that opens `https://chatgpt.com/?temporary-chat=true` instead of the default `https://chatgpt.com/`.

---

The `--save` doesn't seem to work. When I ran `chatgpt --temporary --save $FILE $PROMPT` it exited immediately after submitting, and $FILE had the same content as $PROMPT for both the user _and_ ChatGPT. It took quite some time for ChatGPT to respond thereafter. Find out why this is happening, see what you can do to prevent recurrance even if ChatGPT's UI changes (rely on what's robust), fix, and test.

<!-- codex resume 019f18e2-6578-7a50-94de-bf18d03a9c12 --yolo -->

## Wait for response, 26 Jun 2026

<!--
cd ~/code/scripts/
dev.sh -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Add a `--save TARGET` option to `chatgpt` that waits for ChatGPT to respond, then saves the response to a file and prints the file location.
If TARGET is a directory (or not specified), save it as `chatgpt-YYYY-MM-DD-HH-MM-SS.txt` in that directory (or the current directory).
If TARGET is a file, save it to that file.

Wait for ChatGPT to finish responding.
Copy the response to the clipboard using the "Copy" button in the ChatGPT UI. This copies it as Markdown.
Save the user input as well as the response to the file.
Format:

```markdown
---
link: https://chatgpt.com/c/...
---

## User

(user question)

## ChatGPT

(ChatGPT response)
```

Keep in mind that model names, connector names, project names, reasoning levels, and other options may change in the future. How best can you future proof these?

Keep everything simple and robust. Skip error handling for now.

Run and test on CDP on localhost:9222.

<!-- codex resume 019f027c-2a99-79e2-a9fc-5e55e2783aaa --yolo -->

## Initial version, 19 Jun 2026

<!--
cd ~/code/scripts/
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write and test an agent-friendly uv-based CLI `chatgpt` script that uses CDP on localhost:9222 to open a new https://chatgpt.com tab, type a prompt, attach files, change models, add connectors, switch projects, etc. and submit. ChatGPT might change the DOM structure slightly - so rely on what's robust, e.g. tags, ARIA attributes, robust element hierarchy, IDs or classes that feel semantic rather than auto-compiled, etc.

Run and test.

--- <!-- steering -->

Keep in mind that model names, connector names, project names, reasoning levels, and other options may change in the future. How best can you future proof these?

<!-- codex resume 019edd6c-fed3-77d1-9f0f-bc6bdd2b5f5b --yolo -->
