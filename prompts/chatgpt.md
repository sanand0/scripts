# chatgpt

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
