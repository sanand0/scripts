# aboutmerge.py

## Initial version, 30 Jun 2026

<!--
cd ~/code/scripts
dev.sh -p ~/Dropbox/notes/about/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly CLI `aboutmerge.py` that takes as source all `~/Dropbox/notes/about/week-2026-06-06.md` and merges it into the relevant files using the following logic.

- For each source file `~/Dropbox/notes/about/week-*.md` (in order)
  - For each H1 in the source file except Review, Skipped, Checklist:
    - If a target file matching the H1 title (case-insensitive) does not exist in the target directory `~/Dropbox/notes/about/`, create it with the H1 title as the filename and add the same H1 title as the first line in the new file. Log the target file creation.
    - For each H2 under the H1, if that H2 does not exist in the target file, insert the H2 and content below the H2 into the target file just before the first H2/H3/... or end of the target file. Log the H2 insertion with line number.

No line is ever deleted or changed in the merge process. Only added.
Test via dry-run first.
Then test by copying target files to `/tmp/some-directory/...` and updating the files there sure nothing is lost or overwritten.
Then execute on the target folder.
Re-run to ensure idempotency.

--- <!-- steering -->

Would this be more robust with a real Markdown parser?

--- <!-- steering -->

Await my confirmation before executing on the target folder.

---

Log updates:
- When creating a file, just replace the "insert" with "create". So that way, there's no need for 1 line that mentions "create" and another that mentions "insert". Just say "create" and the rest of the line can be the same as the insert line.
- For the target, just mention the filename, not the full path.
- No need to log the h1 - that's the same as the filename

Do a dry-run.

---

By default, don't update all week-*.md files.
If at least two H2 entries from a file already exist, skip that week's source file and log it.
This is to avoid re-processing files that have already been merged - especially if they contain old H1 entries.

---

Modify the logic as follows:

- PASS 1: Go through each source file `~/Dropbox/notes/about/week-*.md` in REVERSE alphabetical order (Z-A). Identify which files can be skipped. Once you identify 2 consecutive files that can be skipped, stop this pass.
- PASS 2: Process the required files in alphabetical order, as before.

Dry-run and test.

---

Is this the simplest, minimal script that does the job?
Identify refactoring opportunities and share, prioritized by impact (how much the code shrinks) and risk (how much the code changes).
Suggest which ones to implement.
Implement those.
Dry-run and test.

<!-- codex resume 019f17f9-e993-7161-a126-5c7988382e61 --yolo -->
