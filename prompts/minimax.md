# Minimax

## Toggle Minimax in Claude Code, 23 Mar 2026 (Codex Yolo - GPT 5.4 medium)

Update setup.fish to include a function `claudeuse`. Running `claudeuse minimax` will add/update these environment variables in `~/.claude/settings.json`.

```
  "env": {
    "ANTHROPIC_BASE_URL": "https://api.minimax.io/anthropic",
    "ANTHROPIC_AUTH_TOKEN": "(... get the secret from the fish function 'secret MINIMAX_API_KEY')",
    "API_TIMEOUT_MS": "3000000",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": 1,
    "ANTHROPIC_MODEL": "MiniMax-M2.7",
    "ANTHROPIC_SMALL_FAST_MODEL": "MiniMax-M2.7",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "MiniMax-M2.7",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "MiniMax-M2.7",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "MiniMax-M2.7"
  }
```

Running `claudeuse anthropic` will remove all of these (and only these) environment variables from `~/.claude/settings.json`.

Runing `claudeuse` (with or without the options above) prints the env.ANTHROPIC_BASE_URL and ANTHROPIC_MODEL settings after the toggle (blank if off, the minimax values if on).

Make the minimal changes required for this.

<!-- codex resume 019d19c9-7337-7260-81bf-b85fadb9679f -->
