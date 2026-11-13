# callprompt

## Initial draft, 13 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

Create and test an agent-friendly CLI `callprompt` that will:

- Lists untranscribed calls in ~/Documents/calls (`call --list-changes` does this - try reusing what's possible)
- Finds the latest corresponding captions for these in `~/{Downloads,Documents}/{gmeet*.md,teams*.md}` - usually created by `~/code/tools/meetcaptions/`, so check the code
  - Think about a robust way to match. Call titles may not match exactly with the file name but might offer a hint. File creation / modification dates might be a reasonable way.
  - Let the user intuitively provide a match. For example `callprompt IITM` might find the latest call with IITM in the .opus filename (like how `call` does) as well as the meeting title. Or `callprompt --audio IITM --caption gkz-nrnj-vhr` might pick the latest matching filename like `call` and the latest caption file that matches that text in the first few lines.
- Creates a prompt from the captions, just like `meetcall` does, using Luna and the same prompt template, i.e. `## Meeting transcript context` prompt from `~/code/blog/pages/prompts/fragments.md`.
- Prepends a line to `~/Downloads/transcribe.sh` as `call $FILE --prompt "$PROMPT"` - just like the lines already there, but un-commented, so I can run and then comment it out.

If the file has already been transcribed or added to ~/Downloads/transcribe.sh, it should be skipped.

---

Just running `callprompt` or `callprompt --dry-run` should skip unmatched entries.
The /home/sanand/documents/calls/ prefix can be skipped when printing the output.

<!-- codex resume 01a1d411-014d-7671-b699-ae6731a550d7 -->
