# Skills

This directory lists has an [AGENTS.md](AGENTS.md), custom prompts, and a bunch of skills, for AI Code Agents.

- [AGENTS.md](AGENTS.md) is the entry point.
- [prompts/](prompts/) has custom prompts for various agents.
- Directories with a SKILL.md are skills.
- [agents_gen.sh](agents_gen.sh) updates external skills.

## Usage

Link for:

- [Codex CLI](https://github.com/openai/codex): `~/.codex/AGENTS.md`
  ```bash
  ln -s ~/code/scripts/agents/AGENTS.md ~/.codex/AGENTS.md
  ln -s ~/code/scripts/agents ~/.codex/skills
  ```
- [Claude Code](https://docs.anthropic.com/en/docs/claude-code/memory): `~/.claude/CLAUDE.md`
  ```bash
  printf "Claude stalls when generating large text at one shot (e.g. HTML). Generate as chunks or layered edits of max 100KB, save, check, iterate.\n\n" > ~/.claude/CLAUDE.md
  printf "@$HOME/code/scripts/agents/AGENTS.md\n\n@AGENTS.md\n" >> ~/.claude/CLAUDE.md
  ln -s ~/code/scripts/agents ~/.claude/skills
  ```
- [GitHub Copilot](https://code.visualstudio.com/docs/copilot/copilot-customization#_custom-instructions): `~/.copilot/copilot-instructions.md`
  ```bash
  ln -s ~/code/scripts/agents/AGENTS.md ~/.copilot/copilot-instructions.md
  # Skills
  ```
- [OpenCode](https://opencode.ai/docs/config/): `~/.config/opencode/opencode.jsonc`
  ```bash
  jq ".instructions = [\"$HOME/code/scripts/agents/AGENTS.md\", \"AGENTS.md\"]" ~/.config/opencode/opencode.jsonc | sponge ~/.config/opencode/opencode.jsonc
  ```
- [Cline](https://docs.cline.bot/features/cline-rules): `~/Cline/Rules`

Manually update at:

- [Cursor](https://docs.cursor.com/en/context/rules#user-rules): Copy-paste into Settings > Rules.
- [ChatGPT Codex](https://chatgpt.com/codex): Codex Settings > Custom instructions

# Prompts

The `custom-prompts` directory has custom prompts for Codex, etc. Install via:

```bash
ln -s ~/code/scripts/agents/custom-prompts ~/.codex/prompts
```

# Skills

The skills here are relevant to coding agents.
But some skills are also relevant to my online usage and are uploaded to Claude.ai (16 Jul 2026):

- data-analysis
- data-story
- data-viz
- design
- expert-lens
- interactive-storytelling

`archive/` has outdated or under-used skills.
