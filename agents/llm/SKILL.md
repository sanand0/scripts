---
name: llm
description: Call LLM via CLI for transcription, vision, speech/image generation, piping prompts, sub-agents, ...
---

```bash
llm '2 + 2 = ?'
cat prompt.txt | llm
llm --system 'Speak German' 'Hi'
llm --model gpt-5-nano 'Hi'
llm --query 5-nano 'Hi' # pick first model matching query
llm --attachment audio.opus --model gemini-2.5-flash 'Transcribe'  # transcribe audio
llm --schema "{... JSON schema ...}" '...'  # use JSON schema
llm --usage 'Hi'  # show token usage
cat image.jpg | llm 'describe' --attachment -  # describe image
llm --option reasoning_effort minimal 'Hi'
llm models list
llm --extract 'List files by size'  # extract first code block
llm cmd 'List files by size'  # extract and run first code block
llm embed -c 'Hi' -m 3-small -f base64  # get embedding as base64 (or json) using text-embedding-3-small
```

Docs: https://llm.datasette.io/en/stable/usage.html

Preferred models:

gpt-5-mini: default
gpt-5-nano: cheapest
gemini-2.5-flash: cheap transcription
gemini-3-pro: best for transcription

Generate speech:

```bash
curl https://api.openai.com/v1/audio/speech -H "Authorization: Bearer $OPENAI_API_KEY" -H "Content-Type: application/json" \
  -d '{"model": "tts-1", "input": "Hello", "voice": "alloy", "response_format": "mp3"}' --output hello.mp3
```

voice: alloy, ash, ballad, coral, echo, fable, onyx, nova, sage, shimmer, and verse
response_format: mp3, opus, wav
Add "instructions": with style / tone

Generate images:

```bash
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"contents": [{"parts": [{"text": "Cat"}]}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": "16:9"}}}' \
  | jq -r '.candidates[0].content.parts[0].inlineData.data' | base64 -d > cat.png
```

aspectRatio: "1:1", "4:3", "16:9", "3:4", "9:16", "3:2", "2:3", "5:4", "4:5", "21:9"
Specify style, layout, font, scene, lighting, ... clearly

Edit images / provide reference images:

```bash
IMG=$(base64 -w0 cat.png)
echo '{"contents": [{"parts": [{"text": "Edit image: add bold caption `CAT`"}, {"inlineData": {"mime_type": "image/png", "data": "'"$IMG"'"}}]}], "generationConfig": {"responseModalities": ["IMAGE"]}}' > payload.json
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent?key=$GEMINI_API_KEY" \
  -H "Content-Type: application/json" -d @payload.json \
  | jq -r '.candidates[0].content.parts[0].inlineData.data' | base64 -d > captioned.png
```

To write/run tasks as a sub-agent (e.g., code review, code generation), use either Codex or Claude Code:

```bash
codex exec 'Review uncommitted changes for errors and style'
codex exec --image screenshot.png 'Compare code with UI and suggest improvements'
npx -y @anthropic-ai/claude-code -p 'Write a web app ...'
```
