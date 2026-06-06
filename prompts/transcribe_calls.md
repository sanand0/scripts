# Transcribe Calls

## Optimize and simplify, 31 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/:ro \
   -v /home/sanand/Dropbox/notes/transcripts/:/home/sanand/Dropbox/notes/transcripts/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify `transcribe_calls.py` so that when run without parameters, it transcribes untranscribed audio files in `/home/sanand/Documents/calls/*.opus` (based on filename, not modified time) that have a `prompt:` key in them, most recent first.

Also, make sure it has a fast start. For some reason, it's pretty slow to start. Find out why and fix.

<!-- codex resume 019e7c4b-3ecf-77c3-89e3-300d88a9dc0e --yolo -->

## Use prompt when available, 22 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/:ro \
   -v /home/sanand/Dropbox/notes/transcripts/:/home/sanand/Dropbox/notes/transcripts/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Ensure `transcribe_calls.py` uses the `prompt:` YAML frontmatter if available. The priority is: CLI `--prompt` > YAML frontmatter > default prompt.

Run and test on any pending `/home/sanand/Documents/calls/*.opus` whose corresponding transcripts have a `prompt:` key in the YAML frontmatter. Verify that the `prompt:` key is being used as context for the transcription.

<!-- codex resume 019e7324-9cae-70e1-8ffb-41b103674dce --yolo -->

## Improve context, 22 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/:ro \
   -v /home/sanand/Dropbox/notes/transcripts/:/home/sanand/Dropbox/notes/transcripts/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify `transcribe_calls.py` to pass context to the next chunk in case of multiple chunks, so that when the next chunk transcribes, it can infer who is speaking (diarization) and what they're talking about (ambiguity resolution) better.

One way is to summarize the latest transcript chunk and pass it as additional context to the next chunk. Or the full transcript. Or snippets. Or ... there may be other ways. Search online, analyze the transcripts (/home/sanand/Dropbox/notes/transcripts/), find where the transcripts will need most help, think of the best ways of implementing it, compare the likely cost increase (quantitatively, over a typical month) and the likely improvement (best informed guess), and share your results, including which one you recommend implementing. You may run tests if you need to.

<!-- codex resume 019e4e40-af3e-7153-8bfa-3a1879b5ca34 --yolo -->

## Revision, 16 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify `transcribe_calls.py` to load GEMINI_API_KEY from the script's .env file if it exists, if it's missing in the environment even after the PWD's load_dotenv().

<!-- codex resume 019e2e93-fa2d-7031-97eb-f3439eb6443b --yolo -->

## Revision, 05 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/:ro \
   -v /home/sanand/Dropbox/notes/transcripts/:/home/sanand/Dropbox/notes/transcripts/:ro \
   -v /home/sanand/code/blog/:/home/sanand/code/blog/:ro
codex --yolo --model gpt-5.5
-->

Check why `transcribe_calls.py --dry-run` wants to update metadata 800+ transcripts. For example, `2026-04-20 Sucheta LearningMate.md` seems absolutely fine and I don't see any metadata update required. In fact, there should be little or no metadata updates required.

If it's a trivial issue, then fix the script minimally so that it doesn't report false positives and verify. Ask me if you need any inputs.

<!-- codex resume 019df548-1cba-79d2-bac7-6bb5977eb4c2 --yolo -->

## Setup, 16 Mar 2026 (Copilot Yolo - gpt-5.4 xhigh)

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/:ro \
   -v /home/sanand/Dropbox/notes/transcripts/:/home/sanand/Dropbox/notes/transcripts/:ro \
   -v /home/sanand/code/blog/:/home/sanand/code/blog/:ro
copilot --yolo --model gpt-5.4 --effort xhigh
-->

The following command transcribes an audio file:

```bash
llm -m gemini-3.1-pro-preview -s "Transcribe" -a tests/test.opus
```

... and should return "The following command transcribes an audio file". Test that.

Then, write a script (shell, Python, JS, whatever) that will

- Accepts three parameters:
  - input audio files folder (defaults to /home/sanand/Documents/calls/)
  - output transcripts folder (defaults to /home/sanand/Dropbox/notes/transcripts/)
  - system prompt file (defaults to /home/sanand/code/blog/pages/prompts/transcribe-call-recording.md)
- For each audio file in the input folder, creates a transcript file in the output folder unless it already has the transcript. (It's not enough if the file exists -- the transcript section should exist.)

See the format of the latest transcripts in /home/sanand/Dropbox/notes/transcripts/ and the files in /home/sanand/Documents/calls/ for reference.
Use the prompt from the prompt file. If there's a Markdown code fence in it, only use the first code fence's contents. See /home/sanand/code/blog/pages/prompts/transcribe-call-recording.md for an example.

Plan first. Test with tests/test.opus. Then execute and check if it's working fine.

Do not change the state of the default folders (they're read-only for now). Use test folders to execute. Don't waste too many Gemini tokens.

---

Rewrite the code to use the google_genai package directly instead of using `llm`, and to load_dotenv() for the GEMINI_API_KEY.

---

Do not print the files skipped.
Add an option to specify a glob pattern to filter input audio files.
If the output transcript file already exists without a transcript section, mention that in the log.

---

Add a --chunk option that specifies the chunk size in minutes and defaults to 30.
If the audio file is longer than the chunk size, split it into chunks using ffmpeg with a 1 second overlap, transcribe each chunk separately, and then concatenate the transcripts into a single file separated by `\n\n---\n\n`. It's OK if the timestamps are not accurate due to the chunking.

---

In the --dry-run mode, print the duration of each audio file and the number of chunks it would be split into (but do not actually transcribe or create any files).

---

Add an option --prompt to add a prompt. This should be sent to Gemini as a user message (not the system prompt) apart from the audio attachment. Test with a small audio file.

---

Print the number of tokens consumed and the total cost after each transcript. Use https://raw.githubusercontent.com/simonw/llm-prices/refs/heads/main/data/google.json for the prices.

---

If an audio file ends with a single digit number after a space, its transcript is likely to have been added to the base transcript file.

For example:

2025-08-23 Debanshu Bhaumik 4.opus -> 2025-08-23 Debanshu Bhaumik.md
2025-08-23 Debanshu Bhaumik 5.opus -> 2025-08-23 Debanshu Bhaumik.md
2025-09-10 VIA Talks 2.opus -> 2025-09-10 VIA Talks 2.md
2026-01-13 Sandeep Bhat 1.opus -> 2026-01-13 Sandeep Bhat 1.md

Check if the base transcript file already has a transcript section. If it does, then treat the audio file as already transcribed and skip it. If it doesn't, then transcribe it normally, i.e. create the transcript filename based on the audio filename - without removing the trailing number.

---

<!-- gpt-4-xhigh -->

When chunking, add a prompt fragment letting the model know this is part x/y of the transcript.
Prefer chunks of somewhat uniform sizes. Specifically, if instead of 30 min, 25m, 20m, or 15m chunks produce more uniform chunks without increasing the number of total chunks, use that instead - to avoid producing a very short chunk at the end. For example, 40m -> 20m + 20m not 30m + 10m. 93m -> 25m + 25m + 25m + 25m (instead of 30m + 30m + 30m + 3m).

---

Avoid 21 min chunks! That makes it harder for me to calculate timings. A 65m chunk should be 25m + 25m + 15m not 21m40s x 3!

--- <!-- 12 Apr 2026 -->

Modify transcribe_calls.py minimally to add the "--prompt" contents (if provided) in the YAML metadata as `prompt: <contents>`.

--- <!-- 19 Apr 2026 /model gpt-5.4 high -->

Sometimes, in multi-chunk calls, transcribe_calls.py gets a response like "It appears that you forgot to attach the audio file...".

Let's do two things:

1. Add a CLI option to patch a specific section of the transcript file with a new transcript.
2. When Gemini sends the response, check if it looks like a valid transcript (e.g. are there at least 5 lines that match the transcript line format?) If not, log a warning and the command to patch the transcript file.

Run and test using a `gemini-3-flash-preview` (which is cheaper) and a short audio file to avoid consuming too many tokens.

---

Add an option to detect and patch all sections for a specific audio file.
Look at the most recent transcripts and find 3 examples of this issue.
Patch the audio using the default (Pro) model. Verify that it works fine - fixing issues as required.

---

Add/update the `prompt:` key in the YAML metadata of all transcripts to include the prompt used for that transcript.
Use this prompt as context for patches.
Run and test inexpensively.

---

In case the `user_prompt` is provided, use THAT for `prompt:`. Don't use the full contents of the DEFAULT_PROMPT_FILE!

---

Refactor the code to be more simple, removing legacy code paths, options, features that are no longer needed.

---

Currently, the logs report "[1/1] create ..." even when there are multiple chunks. When each chunk is generated, no additional logs are generated.
Modify it so that the number of chunks is calculated upfront and reported, eg. "[1/3] create ..." and when each chunk is generated, log the progress, e.g. "[2/3] create ..."

<!-- Do not add `--lessons`. We want Gemini to have the context. Maybe? -->
<!-- copilot --resume=f160bdf5-0e26-4bd8-ac40-29bcf5debb50 --yolo -->
