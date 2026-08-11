# tests

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
