# Transcribe Calls

## Setup, 16 Mar 2026 (Copilot Yolo - gpt-5.4 xhigh)

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

<!-- Do not add `--lessons`. We want Gemini to have the context. Maybe? -->
<!--

dev.sh -v /home/sanand/Documents/calls/:/home/sanand/Documents/calls/:ro \
   -v /home/sanand/Dropbox/notes/transcripts/:/home/sanand/Dropbox/notes/transcripts/:ro \
   -v /home/sanand/code/blog/:/home/sanand/code/blog/:ro

copilot --yolo --resume=f160bdf5-0e26-4bd8-ac40-29bcf5debb50
-->
