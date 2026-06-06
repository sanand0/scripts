---
name: post-mortem
description: If the task had failures or was inefficient or complex, ALWAYS run this post-mortem.
---

Run a blameless post-mortem on this conversation so far (post any previous post-mortems) to improve future performance.

List every:

- failure (commands, network, sandbox / permissions, ...)
- inefficiency (more steps, slow execution)
- mis-alignment (e.g. I needed something else, you took shortcuts, compromised quality / readability / completeness)

Ignore one-offs. Pick only those that'll likely recur.

For each, document for the user (who may forget the context later), in 1 line each:

- I ... (what you did, with context, and how)
- This ... (what happened, with practical impact)
- Instead, ... (what generalizable change should the USER make to the prompts, skills, tools, environment, ... to prevent similar issues)

Write into `~/Documents/data/agents/post-mortem-${date -u -Iseconds}.md`.

Example:

```markdown
---
task: Verify the WhatsApp scraper using CDP
agent: codex (or copilot or claude)
path: /home/sanand/...
session: session ID
---

- I initially relied too much on ad hoc live scripts.
  This was fast, but let to repeated custom scripts, inconsistent metrics across runs, extra time spent distinguishing true parser issues from script-quality issues.
  Instead, instruct me to create dedicated verification scripts up-front and prefer it over inline shell heredocs for future CDP validation.
- I added inline JS tests for media before I updated the shared HTML fixture.
  This conflicts with the user’s explicit “HTML test set first” request and was less representative than the parser/test surface.
  Instead, create a pre-check SKILL.md that enforces a checklist before executing user actions.
 - ...
```

NOTE: The "Instead, ..." changes are:

- meant for the USER to make - not for you.
- focused on the root cause / general problem, not the specific instance.
