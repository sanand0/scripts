# Rofi prompts

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
