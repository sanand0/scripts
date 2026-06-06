---
name: log-tool-failure
description: If any tool call fails, log it IMMEDIATELY with this skill
---

Append each tool failure as single-line objects into `~/Documents/data/agents/tool-failure.jsonl`. Schema:

```jsonc
{
  "agent": "codex", // e.g. copilot, claude, ...
  "path": "/home/sanand/...", // project directory
  "session": "...", // session ID
  "summary": "...", // crisp 1-sentence summary of what you tried, what failed, AND **WHY**
  "request": {}, // complete tool call as JSON
  "response": {} // complete tool response as JSON, including error code, message, etc.
}
```
