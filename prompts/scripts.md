# Scripts

Overall repository-level prompts.

## Review, 10 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.1-sol --config model_reasoning_effort=high
-->

Read this entire project and find everything that’s broken, inconsistent, inefficient, or no longer needed. Fix what you’re sure about and list the rest for me to review.

---

Move improvements.md to prompts/improvements.md. Commit all files. Then:

- archive the following, mentioning the reason in README.md
  - backupmeet.py - I use ChatGPT when required, even to automate bulk downloads
  - emailai - I use ChatGPT because it has more context
  - codexlist - I use agentlog.py
  - githubscore.py - I use ChatGPT because it evaluates on broader (evolving) criteria
  - gwslog.py - I use ChatGPT weekly (if required) to summarize, not just list
  - q - I don't query ChatGPT / Claude / ... from the CLI
- Delete download.xml, sent.csv, archive/asu
- See if you can replace copy-to-markdown.sh with rofi-clip.sh in media-keys.dconf. If so, delete copy-to-markdown.sh and update README.md.

Then update prompts/improvements.md moving the completed items into `## Fixed` and updating other items as required.
