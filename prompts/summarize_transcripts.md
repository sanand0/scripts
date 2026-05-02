# Summarize transcripts

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Dropbox/notes/transcripts:/home/sanand/Dropbox/notes/transcripts
claude --dangerously-skip-permissions
-->

## Initial version, 28 Apr 2026

Write a Python script that I can run using `uv run summarize_transcripts.py` that will add the following YAML metadata tags to transcripts - if missing or empty.

- `summary`, summarizing key takeaways quoting who said what, in simple, direct language. For example, `summary: Namit rallied the team around AI operationalization, digital twins, fast POCs, growth targets, and recent wins. Jishnu, Sukruth, and Manish shared client momentum. Naveen shared marketing traction. Anand said: help people use existing knowledge, don't build new knowledge hubs.` (But honestly, use YOUR discretion here.)
- `keywords`, the aim is to make AI coding agents easily find content via keyword searches. Write this in a single like, i.e. `keywords: [first topic, next topic, ...]` in a single line.
- `people`, write the people who are part of the call, i.e. the speakers, not people mentioned. This can be done via a script. Write this in a single line, like `people: [first person, next person, ...]`.
- `actions`, write a list of action items that I can easily copy-paste into my task manager. These should be specific and actionable. Write this in multiple lines, i.e. `actions:\n - first action\n - next action\n`

Don't process empty / trivial transcripts (if it has less than, say, 5 lines of content).
Use the Gemini API with a CLI configurable model, defaulting to `gemini-3-flash-preview`.
Read the latest Gemini docs to understand the API and how to use it efficiently.
Use GEMINI_API_KEY from .env or environment variables for authentication.

Make this an agent-friendly CLI (read the agent-friendly-cli skill and the code skill).
Allow filtering the transcripts via glob patterns in the CLI.
Assume the transcript base path to be `/home/sanand/Dropbox/notes/transcripts/` but allow overriding it via absolute globs. For example `2026-04-*.md` processes `/home/sanand/Dropbox/notes/transcripts/2026-*.md` but `/notes/2026-04-*.md` processes `/notes/2026-04-*.md`.

Run for a batch of ~5 transcripts, take a look at the results, and iterate on the prompt and code as needed.

Then run for a batch of 10 transcripts, let me know which ones were processed, and await my feedback.

---

Use JSON responses to ensure the schema. Read the docs for how best to do that using `google-genai`.
Each item in `actions:` must be a string like `Owner: Details of action`, not an object.
Ensure order of keys: summary, keywords, people, actions. Add these BEFORE existing tags.
Don't re-run for the already processed transcripts - efficiently apply the required changes for those.
Allow running in parallel. Bu default, run using 4 parallel workers with a single queue and robust error handling and retries.
Print the cost and token usage for each transcript as a summary at the end of each run.
Run for a new batch of 8 transcripts and test.
Use sub-agents (where required) for token efficiency.

---

Delete empty tags in the YAML metadata.
Ensure that there is an empty like after the YAML front matter for better readability.
You can skip a transcript if the only pending tags are list tag (e.g. keywords, people, actions) that are flagged as empty LISTs, i.e. `[]`. This means that it was already processed and there WERE no keywords, people, or actions to add. But if the tag is missing or is an empty string or null, then process it because that means it was not processed before. This is to avoid unnecessary processing of transcripts that were already processed and had no keywords, people, or actions.
Run for `2026-03-*.md` transcripts and test.

---

`2026-04-24 LearningMate Data Project Implementation.md` is an example of a transcript that is re-processed though the transcript section is empty AND it has `actions: []`. In both such cases, it should be skipped. Fix such problems.

---

/compact

---

Explore why `2025-09-14 PyCon Reuven Lerner Keynote.md` is re-run every time and resolve the issue.

Restructure this so that it is easy to add new tags, and when adding a tag, all information regarding the tag (name, format - e.g. list vs string, how to extract it, how to format it, etc.) is in one place in the code.

Restructure it so that the existing tags: summary, keywords, people, and actions are defined in the same way.

Document (in the code) how to add a new tag and how to override existing tags (e.g. if I change the prompt and want to replace specific tags for specific files).

---

Remove redundant code that won't be needed after restructuring - e.g. repair code that won't be needed in the future (but retain needs_repair).
Simplify the code elegantly.

<!-- claude --resume a2eb2487-4d33-43b8-ad70-0ea11f1c69fa -->
