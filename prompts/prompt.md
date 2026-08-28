# Prompt

## Add use subcommand, 28 Aug 2026

<!--
cd ~/code/scripts
dev.sh -p ~/code/:ro,~/.cache/sanand-scripts,~/.local/share/sanand-scripts -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Modify `prompt` so that `prompt use --days 30` shows the prompts (and frequency) used in the last 30 days, sorted descending, with an option to reverse the sort order. --days defaults to 30. Make it agent friendly - but keep the code change concise.

<!-- codex resume 01a046ec-99f9-7840-b6af-2710dde8c260 --yolo -->

## Rewrite in Python, rename to `prompt`, 15 Jul 2026

<!--
cd ~/code/scripts
dev.sh -p ~/code/:ro,~/.cache/sanand-scripts,~/.local/share/sanand-scripts -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Is it possible to rewrite `rofi-prompts.sh` in Python in a way that's faster, shorter, AND simpler + readable?
If so, create an agent-friendly CLI called `prompts` that does that, writing test cases first (similar to other uv scripts in this directory).
I would also want to replace the `prompt` function in `~/code/scripts/setup.fish` to use this new Python script instead of `rofi-prompts.sh`.
Make sure that `prompts` will work with Ctrl+Alt+P via `~/code/scripts/setup/media-keys.dconf` instead of `rofi-prompts.sh` but will also be compatible with the `prompt` function in `setup.fish` (which is used in other functions live `livesync`).
I don't think the current positional argument of `rofi-prompts.sh`, i.e. `[PROMPTS_DIR_OR_FILE]` is used anywhere - check and verify - and if so, it's fine to replace that with a fuzzy prompt filter as the positional argument instead - roughly the equivalent of the first choice that would appear if we typed that in rofi.

---

Rename the script to `prompt` instead of `prompts`. Update wherever required.

--- <!-- steering -->

I mean, move bin/prompt to ./prompt

<!-- codex resume 01a0052d-80a5-7142-bb33-39b1ee575abd --yolo -->

## Save usage, 30 Jul 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Update `rofi-prompts.sh` minimally to log the prompt activated. Save in ~/.local/share/sanand-scripts/rofi-prompts-log.tsv with timestamp and the prompt name.

<!-- codex resume 019fb0bf-0297-72d2-b5d5-af4192616b5b --yolo -->

## Include descriptions, 29 Jul 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Modify rofi-prompts.sh to display the `description:` from `~/code/blog/pages/prompts/*.md` where available.

If possible, try to do this in a way that simplifies and shortens the overall code without changing functionality, rather than adding more (or much) code.

<!-- codex resume 019fabdc-367c-7902-9466-7ec7e257bd97 --yolo -->

## Wrap skills, 29 Jun 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify rofi-prompts.sh to include skills from `~/code/blog/pages/skills/*/SKILL.md` apart from `~/code/blog/pages/skills/*/SKILL.md`

All skills should have their YAML frontmatter stripped out and be wrapped inside a:

```
<skill name="folder-name">
...
</skill>
```

For example, `~/code/blog/pages/skills/anand-objectives/SKILL.md` should be wrapped as:

```
<skill name="anand-objectives">
Anand is building a ...
</skill>
```

Run and test.

--- <!-- 30 Jun 2026 -->

Modify to include a description=... based on the skill description if it exists. Quote it for HTML/XML.

<!-- codex resume 019f10fd-9243-7a03-8fc7-9165d6beb544 --yolo -->

## Include blog skills, 20 Jun 2026

<!--
cd ~/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Update rofi-prompts.sh to include ~/code/blog/pages/skills/*/SKILL.md. Run and test.

<!-- codex resume 019ee526-3d0e-7de3-bb9b-34c4fbbae60e --yolo -->

## Include skills, 13 May 2026

<!--
cd ~/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify rofi-prompts.sh to read the first "^description: " match ~/code/scripts/agents/**/SKILL.md and include that in the options, chopping the description to a reasonable length. For example, it would display:

```bash
...
data-analysis: Use to investigate data for sur...
devtools: Use CDP at localhost:9222 to test/de...
pdf: How to read, manipulate, and generate PDF...
```

When selected, it should paste the contents of the SKILL.md file excluding the YAML front matter, i.e. after the second `---` line.

Run and test.

---

Prefix skills with `Skill › ` to distinguish from other prompts.

<!-- codex resume 019e1e9a-a51c-7d93-90d7-bf17f7cb5556 --yolo -->
