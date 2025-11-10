# Skills

This directory lists has an [AGENTS.md](AGENTS.md) for AI Code Agents.

[AGENTS.md](AGENTS.md) is the entry point and has common instructions to refer to [skills](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) under this directory.
[agents_gen.sh](agents_gen.sh) updates it from external skills.

## Usage

Link for:

- [GitHub Copilot](https://code.visualstudio.com/docs/copilot/copilot-customization#_custom-instructions): `~/.copilot/copilot-instructions.md`
  ```bash
  ln -s ~/code/scripts/agents/AGENTS.md ~/.copilot/copilot-instructions.md
  ```
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/memory): `~/.claude/CLAUDE.md`
  ```bash
  printf "@$HOME/code/scripts/agents/AGENTS.md\n\n@AGENTS.md" > ~/.claude/CLAUDE.md
  ln -s ~/code/scripts/agents ~/.claude/skills
  ```
- [Codex CLI](https://github.com/openai/codex): `~/.codex/AGENTS.md`
  ```bash
  ln -s ~/code/scripts/agents/AGENTS.md ~/.codex/AGENTS.md
  ```
- [Gemini CLI](https://github.com/google-gemini/gemini-cli/blob/f21ff093897980a51a4ad1ea6ee167dee53416b6/docs/cli/configuration.md?plain=1#L40): `~/.gemini/settings.json`
  ```bash
  jq ".contextFileName = [\"$HOME/code/scripts/agents/AGENTS.md\", \"AGENTS.md\"]" ~/.gemini/settings.json | sponge ~/.gemini/settings.json
  ```
- [OpenCode](https://opencode.ai/docs/config/): `~/.config/opencode/opencode.jsonc`
  ```bash
  jq ".instructions = [\"$HOME/code/scripts/agents/AGENTS.md\", \"AGENTS.md\"]" ~/.config/opencode/opencode.jsonc | sponge ~/.config/opencode/opencode.jsonc
  ```
- [Cline](https://docs.cline.bot/features/cline-rules): `~/Cline/Rules`

Manually update at:

- [Cursor](https://docs.cursor.com/en/context/rules#user-rules): Copy-paste into Settings > Rules.
- [ChatGPT Codex](https://chatgpt.com/codex): Codex Settings > Custom instructions
- WindSurf: No documented global “rules” markdown

# Prompts

The `custom-prompts` directory has custom prompts for Codex, etc. Install via:

```bash
ln -s ~/code/scripts/agents/custom-prompts ~/.codex/prompts
```
