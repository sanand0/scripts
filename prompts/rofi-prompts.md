# Rofi prompts

## Include skills, 13 May 2026

<!--

cd /home/sanand/code/scripts
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
