---
name: llm
description: For niche models (e.g. OpenRouter) and API keys
---

```bash
llm models list
llm keys get openrouter
llm --system 'Speak German' 'Hi'
llm --fragment a.txt --fragment https://example.org/ --fragment "User prompt fragment" --system-fragment system-prompt.txt
llm --attachment audio.opus --model gemini-3-flash-preview 'Transcribe audio'
llm -a a.png -a b.png -s "OCR images"
llm --schema "{... JSON schema ...}" '...'  # use JSON schema
llm --usage 'Hi'  # show token usage
cat image.jpg | llm 'describe' --attachment -  # describe image
llm --option reasoning_effort minimal 'Hi'
llm --extract 'List files by size'  # extract first code block
llm cmd 'List files by size'  # extract and run first code block
llm embed -c 'Hi' -m 3-small -f base64  # get embedding as base64 (or json) using text-embedding-3-small
```

Docs: https://llm.datasette.io/en/stable/usage.html
