---
name: llm
description: Call LLM via CLI for transcription, vision, pipeline-based automation, ...
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

Preferred models:

gpt-5-mini: default
gpt-5-nano: cheapest
gemini-2.5-flash: cheap transcription
gemini-2.5-pro: best for transcription

Docs: https://llm.datasette.io/en/stable/usage.html
