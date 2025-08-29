# AI Code Rules

This directory lists guidelines for AI Code Agents.

[ai-code-rules.md](ai-code-rules.md) is the entry point and has the most important instructions. It references:

- [npm-packages](npm-packages.md) with detailed instructions for npm packages
- [test-browser-js-apps.md](test-browser-js-apps.md) for vitest + happy-dom testing

## Usage

Automatically linked at:

- [GitHub Copilot](https://code.visualstudio.com/docs/copilot/copilot-customization#_custom-instructions):
  - In `~/.config/Code/User/ai-code-rules.instructions.md`
  - Add `[Rules](/home/sanand/code/scripts/ai-code-rules/ai-code-rules.md)`
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/memory):
  - In `~/.claude/CLAUDE.md`
  - Add `@~/code/scripts/ai-code-rules/ai-code-rules.md`
- [Codex CLI](https://github.com/openai/codex):
  - Run `ln -s ~/code/scripts/ai-code-rules/ai-code-rules.md ~/.codex/AGENTS.md`
- [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/f21ff093897980a51a4ad1ea6ee167dee53416b6/docs/cli/configuration.md?plain=1#L40):
  - In `~/.gemini/settings.json`
  - Add `"contextFileName": "/home/sanand/code/scripts/ai-code-rules/ai-code-rules.md",`
- [Cline](https://docs.cline.bot/features/cline-rules): `~/Cline/Rules`
- [OpenCode](https://opencode.ai/docs/config/?utm_source=chatgpt.com): `~/.config/opencode/mode/`

Manually update at:

- [Cursor](https://docs.cursor.com/en/context/rules#user-rules): Copy-paste into Settings > Rules.
- [ChatGPT Codex](https://chatgpt.com/codex): Codex Settings > Custom instructions
- WindSurf: No documented global “rules” markdown
