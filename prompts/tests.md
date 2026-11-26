# tests

## Run on plutonium, 26 Nov 2026

<!--
cd ~/code/scripts
claude --model opus --effort medium
-->

The tests in this repo run mostly fine on graphene (one test is skipped) but fails on plutonium.
See ~/code/scripts/setup/{windows,linux}.md for the setup. Feel free to use @Remote Desktop Commander to inspect the setup on graphene. You're running on plutonium.

What changes in the environment are required to get the tests to run?
This is a step towards my aim to have the plutonium environment match graphene - even though plutonium is Windows and graphene is Linux. I prefer native Windows stuff where possible, over Cygwin, over WSL, over Docker, etc.

Fix what you’re sure about and list the rest for me to review.

---

I don't care about testing Linux-only code on plutonium - like rofi, xclip, etc. So I guess the rest of it is skippable for now. No action required.

<!-- claude --model opus --effort medium --resume 465c91c9-b1bd-42ae-80da-bd97a0999b69 # plutonium -->

## Fix all tests, 11 Aug 2026

<!--
cd ~/code/scripts
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

I ran `uv run --with pytest --with ruamel.yaml --with mutagen --with playwright --with frontmatter --with fastmcp --with premailer pytest` and that reported a series of errors.

A few questions:

- Is this how I should be running the tests? Or is there a better way to run them?
- Which of these are failing test cases that are failing because the code is wrong? Can we fix it? How easy or difficult is it?
- Which of these are failing test cases where the test is wrong and the code is right? prompts/*.md and git history can help diagnose this.
- Which of these are failing test cases where the environment is failing, but the code and tests are both right? Is there a way to reduce brittleness?
- Which of these are failing test cases that can be optimized to avoid API calls that incur a cost? Is there a way to mock it?
- Any other categories to consider?

Just diagnose and catalog these as a first step. Document your findings in tests/diagnosis.md. Then, we can work on fixing them.

--- <!-- steering -->

Use sub-agents as required to conserve context window.

---

I'd rather not have a tests/requirements.lock - that'll require maintenance.
Instead, create a `justfile` with a `just test` command that runs all the tests. One line per test script is fine - each pinned to their version where required. If you think a separate `just test-...` for each script is a good idea, go ahead. Document this in README.md.

Fix these:

1. Stop unintended paid calls
2. Fix the environment for Playwright as required.
3. Fix the failures in the test cases when they are outdated or wrong.

Let me know if there are pending errors.

<!-- codex resume 019ff07d-e257-72c0-b704-c1b1f4ce6daa -->
