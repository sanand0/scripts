# AI Code Rules

This directory lists guidelines for AI Code Agents.

[ai-code-rules.md](ai-code-rules.md) is the entry point and has the most important instructions. It references:

- [npm-packages](npm-packages.md) with detailed instructions for npm packages
- [test-browser-js-apps.md](test-browser-js-apps.md) for vitest + happy-dom testing

## Usage

- [GitHub Copilot](https://code.visualstudio.com/docs/copilot/copilot-customization#_custom-instructions):
  - In `~/.config/Code/User/prompts/ai-code-rules.md`
  - Add `[Rules](/home/sanand/code/scripts/ai-code-rules/ai-code-rules.md)`
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/memory):
  - In `~/.claude/CLAUDE.md`
  - Add `@~/code/scripts/ai-code-rules/ai-code-rules.md`
- [Codex CLI](https://github.com/openai/codex):
  - Run `ln -s ~/code/scripts/ai-code-rules/ai-code-rules.md ~/.codex/AGENTS.md`
- [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/f21ff093897980a51a4ad1ea6ee167dee53416b6/docs/cli/configuration.md?plain=1#L40):
  - In `~/.gemini/settings.json`
  - Add `"contextFileName": "/home/sanand/code/scripts/ai-code-rules/ai-code-rules.md",`
- [Cursor](https://docs.cursor.com/en/context/rules#user-rules):
  - Copy-paste into Settings > Rules.
