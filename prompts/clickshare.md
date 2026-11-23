# clickshare

## Try installer, 23 Nov 2026

<!--
cd ~/code/infra/clickshare  # Later moved to ~/code/scripts/clickshare
codex --model gpt-6.2-sol --config model_reasoning_effort=medium
-->

I have a ClickShare app on a USB drive. But it exists only for Mac/Windows, not Linux.
Can you research and enable it so that I can use it with Meet, Teams, Zoom, etc.?
Ideally, find existing Linux software. If not, tell me how easy it is to create one.

---

I'd rather not use Wine

---

There's a button on the Clickshare. Let me know if you need me to click it and test if it appears on the LCD screen in the room or something.

---

<send_user_message_question_reply>
[{"answer":"LED is blinking. TV is showing my colleague's screen.","question":"What color is the Button’s LED, and is it solid or blinking? If it’s solid white and the room display is free, press once with a harmless window on screen and tell me what the LCD shows. Press again if it starts sharing.","questionItemId":"[\"request_user_input_async\",\"call_c70a6f6be44e47d892f6dd99870d8da8\",0]"}]
</send_user_message_question_reply>

---

My colleague stopped presenting. I pressed the button, but it's still blinking. See if you can take control.

---

The ClickShare network's password is "clickshare" - try that maybe?

---

I enabled streaming via Google Cast. Try now

---

I saw Clickshare Test on the screen briefly. How do I set things up so I can do this without switching networks, so I can use Internet via WiFi and still share? I do have the USB device connected... maybe that helps?

---

I can't do any of the above. Without a second USB Wi-Fi adapter can you still make it work for me? If required, you may switch to the ClickShare network, make changes, and switch back.

---

Any way we can detect the microphone and speaker and use them?

---

<send_user_message_question_reply>
[{"answer":"Yes, from the room speakers","question":"Did you hear the last test tone from the room speakers? It was a single tone lasting about two seconds.","questionItemId":"[\"request_user_input_async\",\"call_c443183d331c498ba4a87c7f3a2c7073\",0]"}]
</send_user_message_question_reply>

---

Mic and speaker worked. Camera?

---

How do I persist these settings after reboot or on a new machine? Document in ~/code/scripts/setup/linux.md.

---

System hung while I tried to connect to another monitor via HDMI. Continue and complete

---

Too verbose and complex. Is it possible to simplify this into a single script in ~/code/scripts/ that I can run to connect to ClickShare? That way, we may not need any changes to ~/code/scripts/setup/linux.md.

---

Update clickshare so that when run by default, it'll warn mentioning the system freeze issue (see ../system-crash/) and ask the user if they're sure they want to continue. `--force` can override it.

<!-- codex resume 01a20654-7a8e-7ad0-9111-791722ed46d6 -->
