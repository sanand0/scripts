---
name: log-tool-failure
description: If any tool call fails, log it IMMEDIATELY with this skill
---

Append one VALID JSON object per unexpected, reusable tool failure to `~/Documents/data/agents/tool-failure.jsonl`. Quote / escape JSON programmatically.

```jsonc
{
  "timestamp": "...",  // ISO time
  "agent": "codex", // e.g. copilot, claude, ...
  "path": "/home/sanand/...", // project directory
  "session": "...", // session ID
  "summary": "...", // crisp 1-sentence summary of what you tried, what failed, AND **WHY**
  "request": {}, // complete tool call as JSON
  "response": {} // complete tool response as JSON, including error code, message, etc.
}
```


Log only failures that can improve future agent behavior:

- recurring command misuse
- local environment/tool limitation
- dependency/auth/permission/rate-limit blocker
- brittle selector/API/version mismatch
- failed logging or failed recovery mechanism
- non-obvious test/tool behavior that caused rework

Skip:

- expected failing tests in TDD
- deliberate negative tests
- ordinary no-match searches
- user-approved skipped work
- project/content/process mistakes better suited to post-mortem
