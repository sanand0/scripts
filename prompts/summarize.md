# Summarize

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Dropbox/notes/transcripts:/home/sanand/Dropbox/notes/transcripts \
  -v /home/sanand/code/blog:/home/sanand/code/blog
claude --dangerously-skip-permissions
-->

## Refactor, 01 May 2026, #TODO

Convert `summarize_transcripts.py` into `summarize.py` that can summarize not just transcripts at `/home/sanand/Dropbox/notes/transcripts/` but also blog posts and pages under `/home/sanand/code/blog/{posts,pages}/`.

Transcripts and blogs require different schema.

- Transcripts
  - summary: str - 1-2 sentences naming key speakers and what they argued or decided.
  - keywords: list[str] - 5-15 topics, names, tools, and concepts for keyword search.
  - people: list[str] - First names of clearly identified speakers only. Empty list if none.
  - actions: list[str] - Action items as "Owner: Details" e.g. "Alok: Test GCS buckets". Empty list if none.
- Blogs
  - description: str - 20-40 word main point or most useful takeaway. Prefer concrete ideas over framing. Include distinctive methods, domains, tools, or concepts when central.
  - keywords: list[str] - 4-8 lower-case topics (names, tools, concepts) for keyword search. No generic tags, redundant synonyms.

They require different prompts. For blog, the prompt may just need to be: "Generate a description and keywords for this blog post's metadata." followed by the content.

Currently, for transcripts, the content to pass is `Transcript:` followed by the extracted `## Transcript` section. Let's simplify this and pass the entire content of the transcript file - including YAML metadata. Do the same for blog posts, too.

Restructure the code so that the prompts and the schema and other content-set related config / code sits together and more such content-sets can be easily added in the future. For example, extracting speakers is relevant only for transcripts, not for blogs.

Document (in the code) how to add a new content set.

Assume the base path to be `.` and allow overriding it via absolute globs. For example `2026-04-*.md` processes `./2026-*.md` and `/notes/2026-04-*.md` processes `/notes/2026-04-*.md`.

Remove redundant code that won't be needed after restructuring - e.g. transcript extraction, perhaps repair code that was needed earlier. Simplify the code elegantly.

Run for a batch of ~5 blog posts 5 transcripts. Pick good examples as diverse test cases to check edge cases. For blog posts, see if the output matches the intent. For transcripts, see if the revisions are structurally identical and the content is broadly similar to existing content (if any) and matches the intent. Iterate as required.

Let me know which ones were processed, and await my feedback.

---

Revise the prompts to that the `description:` reflects these preferences:

1. This is fine: Fast, Thinking, and Pro are best treated as task-specific Gemini modes rather than generic quality tiers, because each one fits a different kind of job.
2. Instead of: Migrating from Python and Tornado to Node.js simplifies corporate recruitment while maintaining asynchronous performance. Benefits include superior execution speed compared to Rhino, shared client-server codebases, and a robust event-based model similar to Nginx.
   I prefer: I migrated from Python and Tornado to Node.js. This simplifies recruitment (only one language) and maintains asynchronous performance. It's also faster than Rhino, lets you share client-server code, and has a robust Nginx-like event model.
3. This is fine: Extend Python Markdown using the markdown-customblocks library to create complex nested HTML structures like Bootstrap columns or custom audio tags. This method allows for flexible content layouts without writing raw HTML code.
4. Instead of: Visualizes IMDb data using a grid mapping user ratings against vote counts. This heatmap approach identifies popular high-rated movies, tracks personal viewing progress, and filters by genre to discover recommendation outliers beyond the standard Top 250 list.
   I prefer: I visualized IMDb data as a grid of user ratings against vote counts. This lets me find popular high-rated movies by genre, track my viewing progress beyond the standard Top 250 list, and find outliers.
5. Instead of: Using the coding agent Claude Code, the author identified ten notable individuals whose names begin and end with 'AI' by searching over 24,000 Wikipedia entries, demonstrating creative pattern analysis through automated LLM-assisted scripting and data extraction.
   I prefer: Using Claude Code, I found 10 famous people whose names begin and end with 'AI' across 24,000 Wikipedia entries. Automated LLM-assisted scripting can perform creative pattern analysis.

For blogs, new tags should be added AFTER existing YAML tags. But for transcripts, it should be BEFORE. Make that configurable, too.

Run for the same batch and iterate until you get close enough to the intended result. Run for 5 more diverse examples as test cases and check if they match the intent. Then list which ones were processed and await my feedback.

---

Document this in README.md as a one-line bullet.
Add sub-bullets explaining how to run it for new transcripts and blog posts. Basically, I will just run the two code snippets you give me blindly - maybe daily, weekly, or monthly or anywhere in-between. The same snippet should work seamlessly.
Since re-running on content that already has the meta tags is harmless, it's OK to prefer simplicity over exactness. For example, you could give me a script that'll run all transcripts with a glob of 2026-04* and I can modify that easily; or a `ug -l '^date: 2026-04'` piped via xargs for blogs. Or any other simple, easy-to-edit mechanism.

---

/compact

---

In `/home/sanand/code/blog` there are a few metadata formatting issues. For example:

- `pages/notes/gemini-immune-system.md` and other pages replaces `build: { list: never, render: always }` with `build: {list: never, render: always}`
- `pages/prompts/fake-data.md` and other pages have no indentation under `sources:`
- `posts/1999/punctuation-is-critical.md` and other pages have no indentation under `categories:`

Update `summarize.py` using as guidance to preserve the formatting.
Also, review `/home/sanand/code/blog` to make sure that all changed files have the correct formatting - and no file is changed purely because of formatting.

---

/effort medium

---

Why do I get this error on just these two posts?

❯ summarize.py blog posts/2000/more-gale-trouble.md posts/2000/train-delays.md
ERROR train-delays.md: RetryError[<Future at 0x721b167e6b10 state=finished raised ValueError>]
ERROR more-gale-trouble.md: RetryError[<Future at 0x721b169afec0 state=finished raised ValueError>]

Fix only if it REALLY needs fixing and it won't increase summarize.py lines of code by more than 3 lines.

---

Give me the description and keywords to paste.

<!-- claude --resume 1d3b01c8-87e8-4a39-b9d6-e7a347204717 --dangerously-skip-permissions -->
