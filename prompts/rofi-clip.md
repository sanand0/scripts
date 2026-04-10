# Rofi Clip

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
