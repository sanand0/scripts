# podcast

## Revise podcast output, 21 May 2026

<!--

cd ~/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Minimally modify `podcast.py` so that, if the output file is not specified, default to the same filename as the input Markdown file but with a `.mp3` extension if that target doesn't exist, and append a timestamp only if it exists.

<!-- codex resume 019e49f1-1867-7e72-a50a-904f880dc2ed --yolo -->

## Revise podcast script, 19 May 2026

<!--

cd ~/code/scripts
dev.sh \
  -v /home/sanand/code/generative-ai-group/:/home/sanand/code/generative-ai-group/:ro \
  -v /home/sanand/code/sanand0/week/:/home/sanand/code/sanand0/week/:ro
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Modify `podcast.py` as follows:

First, if the output filename is not specified, default to the base name of the Markdown file specified, with a timestamp suffix for uniqueness, and with the .mp3 extension.

Second, if we get an unexpected result in the response, like the one below, then log the full response body for debugging instead of just raising a KeyError:

```
│ /home/sanand/code/scripts/podcast.py:319 in request_gemini_audio                                                                                               │
│                                                                                                                                                                │
│   316 │   )                                                                                                                                                    │
│   317 │   raise_for_status_with_body(response)                                                                                                                 │
│   318 │   result = response.json()                                                                                                                             │
│ ❱ 319 │   audio_b64 = result["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]                                                                     │
│   320 │   return base64.b64decode(audio_b64)                                                                                                                   │

KeyError: 'content'
```
<!-- codex resume 019e3f5a-3145-7da0-9cf6-b84eee8d0742 -->

## Create podcast script, 14 May 2026

<!--

cd ~/code/scripts
dev.sh \
  -v /home/sanand/code/generative-ai-group/:/home/sanand/code/generative-ai-group/:ro \
  -v /home/sanand/code/sanand0/week/:/home/sanand/code/sanand0/week/:ro
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Create an agent-friendly CLI `podcast.py` that accepts a single Markdown file as input and renders it as a podcast.

Use the same approach as /home/sanand/code/generative-ai-group/podcast.py / /home/sanand/code/sanand0/week/summary.py which is to:

- Use the Gemini API key from .env / environment to generate audio via a CLI-configurable TTS model that defaults to gemini-2.5-flash-preview-tts
- Stitch them together using ffmpeg (with -hide-banner and showing the output as it runs) into a CLI-configurable output that defaults to podcast-YYYY-MM-DD-HH-MM-SS.opus

The input Markdown file will have the following format:

```markdown
Alex: First speaker's words
which may span multiple lines

including with empty lines in between

- or a list
- with multiple items.

  **Maya**: Second speaker's words. Any sentence that begins with a word (optionally prefixed by whitespace) followed by a colon is a new speaker.
The speaker name is the word before the colon, stripped of special characters and whitespace (just letters, numbers, hyphens, underscores).
The words after the colon are the speaker's words.

Alex: First speaker again.
Maya: There may not be any spaces between speakers.
```

Find all speakers and their words, generate an audio file for each speaker's words sequentially, and stitch them together.

Log progress as you go, clearly indicating CURRENT/TOTAL (e.g. 3/10 means we started the 3rd item out of 10.)

Process YAML front matter if available, which can contain the multi-speaker voice configuration as follows:

```yaml
# Mapping of speaker names to pre-built voice names.
speakers:
  Alex: Algieba
  Maya: Kore
```

For unmapped speakers, use the first unassigned pre-built voice from this list, in order.

Algieba
Kore
Orus
Zephyr
Achird
Achernar
Alnilam
Aoede
Charon
Autonoe
Enceladus
Callirrhoe
Fenrir
Gacrux
Iapetus
Laomedeia
Puck
Leda
Rasalgethi
Pulcherrima
Sadachbia
Sulafat
Sadaltager
Vindemiatrix
Schedar
Umbriel
Zubenelgenubi

Before starting the generation, log the speaker - voice mapping to be used and the number of items to be generated.

Use tenacity for fallback.
Allow resuming if interrupted by ensuring that intermediate files are cached and skipped if they already exist. Use a sensible cache (hashed based on voice, text, and any other API parameter) that allows for multiple runs. On startup, ensure that cache files older than a day are deleted. (File modified time is good enough. Keep the script fast and frugal.)

Begin by writing test cases against a dry-run (without actual TTS generation) and then implement the actual generation. Make sure it works by also testing a small real input.

---

I made a few changes to the ffmpeg invocation. Retain them.

Just make one change: switch to .mp3 as the default output format instead of .opus, but allow .opus as an option.

In both cases, aim for maximum compression for voice audio. For opus, I use `-c:a libopus -b:a 12k -ac 1 -application voip -vbr on -compression_level 10` which to me is good enough. Use the equivalent for MP3.

---

If GEMINI_API_KEY is not set in the environment or the current .env, fall back to the .env in the script directory.

---

Allow generating in parallel. Allow configuring the number of parallel processes using the CLI arguments. Default to 4.

<!-- codex resume 019e267c-a215-7911-acb7-c165938e34da --yolo -->
