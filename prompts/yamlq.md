# yamlq

## Initial script, 18 May 2026

<!--
cd ~/code/scripts
dev.sh -v /home/sanand/code/blog:/home/sanand/code/blog:ro -v /home/sanand/Dropbox/notes/transcripts:/home/sanand/Dropbox/notes/transcripts:ro
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write a bash script `./yamlq KEY1,KEY2,... *.md` that accepts zero or more files that contain YAML frontmatter and extracts the values for the specified keys.

For example:

```bash
yamlq actions /home/sanand/Dropbox/notes/transcripts/2026-05-1*.md
yamlq title,categories,description,keywords /home/sanand/code/blog/posts/2026/*.md
```

The result should be like this - file name, followed by indented matches (as-is, including lists):

```
/home/sanand/code/blog/posts/2026/yearly-goal-tracking-faq.md
\ttitle: Yearly Goal Tracking FAQ
\tcategories:
\t  - how-i-do-things
\tdescription: I share my process for tracking yearly goals through public email updates. I answer questions on handling "soft" relationship goals, using public commitment for discipline, and why I prefer automatic tracking via Google Fit and GitHub over manual logs.
\tkeywords: [goal tracking, public commitment, habit formation, accountability, google fit, personal growth]

/home/sanand/code/blog/posts/2026/writing-articles-from-my-blog-posts.md
... and so on
```

Run and test.

---

A quick question - see if dasel can do this more concisely. Aim to create a short script combining tools (awk, dasel, etc.) rather than a comprehensive one. It's OK to stray from my specs - brevity counts for a lot.

---

`/home/sanand/Dropbox/notes/transcripts/2026-05-17 Palani.md` had actions that `yamlq actions` didn't surface.

---

yamlq actions ~/Dropbox/notes/transcripts/2026-05-1*.md does not process all files when I run it in fish.

<!-- codex resume 019e38fa-96ef-7f63-9f8a-8ebd248c3f68 --yolo -->

## Discarded

```bash
yq --front-matter=extract FILE
```

... is a simpler alternative!
