---
name: agent-friendly-cli
description: Use when writing command-line scripts agents will control
---

- Support JSON input via `--json` or `--params` and output via `--output json` or `--format json`. Prefer structured output as default for non-TTY.
- Validate all inputs aggressively. Humans and agents make mistakes or can be adversarial. Support `--dry-run` for writes. Confirm before destructive actions
- Add a schema or `--describe` capability that returns machine-readable method signatures: params, request body, response types, ...
- Fail fast showing reason and correct invocation.
- Design for context-window efficiency. Document and support filters, field masks, NDJSON pagination, etc. so agents can request only needed data
- Support environment-variable-driven, headless execution for unattended use (tokens, credential file paths)
- Log state/progress BEFORE actions and flush - so agents can monitor, write errors that help agents debug, warn agents of unexpected input, data, configs, etc.
- Document with compact, explicit instructions and examples
