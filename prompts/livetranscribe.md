# Prompts

<!--

cd ~/code/scripts
dev.sh
claude --dangerously-skip-permissions

-->

## Plan, 10 Apr 2026

Write a script `livetranscribe` that will watch a `.opus` file that is streaming.

See `function record` in setup.fish to understand how this will be created. I will be recording using FFmpeg audio from my speakers and mic and saving it into a .opus file and the file will constantly grow.

Use the Gemini Live API to transcribe real-time. See https://ai.google.dev/gemini-api/docs/live-api/get-started-sdk
Use gemini-3.1-flash-live-preview as the model.

This script should read all the current contents of the file that exist, which may have been populated from before, and transcribe it and stream the output into a file and the console.

As new audio comes in, the transcription should continue with some kind of a reasonable polling (e.g. 2-5 seconds, CLI-configurable). The script should follow the agent-friendly-cli skill.

Create a test scaffolding that will generate a realistic streaming opus based on test-audio.opus. This will be useful when testing the script.

There's a GEMINI_API_KEY available in .env that you can use.

Don't implement yet. Create a plan for me to review. Include the key questions that you would like me to give you inputs on, the key architectural decisions, design decisions, etc.

---

Prefer live sessions. Beyond a certain duration, e.g. 14 min, create a start another session. Pass it context from the last (roughly) 30 seconds of the previous session. (Or you can pick the last few lines of transcript - whatever is easier.)

If the file already has 10 minutes of audio, transcribe the existing audio in one shot and continue transcribing new live audio in the same session.

Allow a --format to select transcript format. But include the timing information in the transcript, e.g. "[01:23] Text of the transcript."

Include a 1 second overlap of previous chunk for continuity.

Suppress empty chunks from output.

Let the default --output be the same as the input file but with .txt extension. `path/to/input.opus` -> `path/to/input.txt`.

Allow a --prompt option to specify a custom prompt to prime the model. Pick a sensible default.

Implement and test. If you run into problems, ask me.

---

Add an option to not transcribe existing audio and only transcribe new audio that comes in after the script starts. (No testing required.)

<!-- claude --resume 7415568c-8de4-4899-9315-9b53c5227f36 -->
