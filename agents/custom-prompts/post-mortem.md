---
description: Run a post-mortem analysis
---

Run a blameless post-mortem on this entire conversation to improve future performance.

1. List problems face: failures, inefficiencies and mis-alignments. Examples (not exhaustive):
  - What commands failed or behaved unexpectedly?
  - What did you need to correct?
  - Where did the conversation take more steps than necessary? What could have been faster?
  - Where did you adhere to the letter but not the spirit of the instructions, or take shortcuts that compromised quality?
3. For each failure:
  - Dig deep to identify the root cause (max: 5 Whys).
  - Add "Scope: local/global" global (applies to all future tasks) or local (applies only to similar tasks, or this repo)
  - Add "Impact: high/medium/low" with reason: what's the PRACTICAL impact on the developer
  - Add "Frequency: high/medium/low" with reason
  - Share fixes to prompts (e.g. code samples, clear instructions, planning) or the environment (e.g. installing tools, set environment variables) would have prevented each failure
    - Fix at a root cause level, not a symptom level.
    - Suggest changes that are resolve **entire classes/patterns of failures**, not just a specific instance.
    - Write changes as prompts snippets we can add directly to future AGENTS.md / CLAUDE.md.
3. List successes: techniques / approaches you discovered that worked well. Examples: tools, code snippets, prompt structures, planning techniques.
  - Share what change to the environment / prompts will make it easier to repeat these successes in the future. Include scope, impact, frequency.

Use this style:

```markdown
# Post Mortem of {directory}

- 🔴 Problem: Leaking sensitive data
  - Why: I copied real data into tests.
    - Because it was easier than creating dummy data.
    - ...
  - Prompt fixes: Add "Replace PII in committed code, tests, docs with similar REALISTIC dummy data."
  - Environment fixes: NA
  - Scope: **Global**. Reason: Any code could leak PII
  - Impact: **High**. Reason: Affects trust, reputation, relationships
  - Frequency: **Medium**. Reason: The best tests are on real data, so this is a common temptation.
- 🟢 Success: ... (same structure)
```

Save as `post-mortem-{directory}.md`.
