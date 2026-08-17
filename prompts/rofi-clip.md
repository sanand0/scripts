# Rofi Clip

## Update strip-tracking, 17 Aug 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Modify rofi-clip.sh so that the `transform_strip_tracking` will work on text with multiple links embedded, e.g. a Markdown list of links. Only the links should be transformed - the rest of the text remains as-is (including whitespaces). Write and run failing tests first, then implement.

<!-- codex resume 01a01003-8cd4-76c1-b831-f17b761d17f4 -->

## Save usage, 30 Jul 2026

<!--
cd ~/code/scripts
dev.sh -- codex resume 019fb0bf-0297-72d2-b5d5-af4192616b5b --yolo
-->

Update `rofi-clip.sh` minimally to log clipboard transform activated. Save in ~/.local/share/sanand-scripts/rofi-clip-log.tsv with timestamp and the transform name.

<!-- codex resume 019fb0bf-0297-72d2-b5d5-af4192616b5b --yolo -->

## Use sans-serif unicode font, 06 Jun 2026

<!--
cd ~/code/scripts; dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Minimally modify `rofi-clip.sh` Markdown -> Unicode to convert **bold** to 𝗯𝗼𝗹𝗱 instead of 𝐛𝐨𝐥𝐝.

## Add emojis, 30 Mar 2026

<!--
cd ~/code/scripts; dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Update `rofi-clip.sh` to include a "Shorthand to Emoji" command. This should convert all emoji shorthand notations to their corresponding emojis. For example, ":smile:" becomes "😄", ":heart:" becomes "❤️", ":thumbsup:" becomes "👍", and so on.
Test to verify.

<!-- codex resume 019e7835-36b4-7a50-a087-532e7a56967a --yolo -->

## Add slugs, 17 Mar 2026 (Copilot Yolo - GPT 5.4 xhigh)

Update `rofi-clip.sh` to include a "Text to Slug" command. This should convert the text to lowercase and replace non-alphanumeric characters with hyphens.
" Peoples' Café " becomes "peoples-cafe".
Trim leading and trailing hyphens. Replace multiple consecutive hyphens with a single hyphen. Replace unicode with ascii (re-using code).
Test to verify.

## Add HTML to Markdown, 06 Apr 2026 (Copilot Yolo - GPT 5.4 medium)

Add a "HTML to Markdown" command to `rofi-clip.sh` that converts HTML content in the clipboard to Markdown format.
Re-use as much of existing code as possible. Minimize code changes.

---

When I copy HTML, it is typically as text/plain, not text/html!

---

<!-- effort xhigh -->

How can we refactor to simplify and make this change more elegant?

<!-- copilot --resume=192855bd-a9ed-4c35-a1da-8369d47e9263 -->
