# setup

Prompts for setup.{fish,bash}.

## Videocompress fix, 12 Nov 2026

<!--
cd ~/code/infra/videocompress
codex --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

I tried this in ~/Downloads/:

```
❯ videocompress 'WIDE SHOT FULL.MP4'
Started videocompress (PID 366193): /home/sanand/Downloads/wide-shot-full.webm
Stop encoding: kill -TERM 366193
Ctrl+C stops viewing progress, not encoding. Log: /home/sanand/.cache/videocompress/videocompress.0CPcO5Cm.log
[av1_nvenc @ 0x630814e3fac0] No capable devices found
[vost#0:0/av1_nvenc @ 0x630814e40dc0] [enc:av1_nvenc @ 0x630814db4bc0] Error while opening encoder - maybe incorrect parameters such as bit_rate, rate, width or height.
[vf#0:0 @ 0x630814e41b40] Error sending frames to consumers: Generic error in an external library
[vf#0:0 @ 0x630814e41b40] Task finished with error code: -542398533 (Generic error in an external library)
[vf#0:0 @ 0x630814e41b40] Terminating thread with return code -542398533 (Generic error in an external library)
[vost#0:0/av1_nvenc @ 0x630814e40dc0] [enc:av1_nvenc @ 0x630814db4bc0] Could not open encoder before EOF
[vost#0:0/av1_nvenc @ 0x630814e40dc0] Task finished with error code: -22 (Invalid argument)
[vost#0:0/av1_nvenc @ 0x630814e40dc0] Terminating thread with return code -22 (Invalid argument)
[out#0/webm @ 0x63081482e780] Nothing was written into output file, because at least one of its streams received no packets.
frame=    0 fps=0.0 q=0.0 Lsize=       0KiB time=N/A bitrate=N/A speed=N/A elapsed=0:00:00.78
FFmpeg failed
```

videocompress is defined in ~/code/scripts/setup.fish.

What's the problem? How do I fix it?

---

Is this change always good? I mean, for some of the other videos in ~/Downloads/ is this good from a quality and size perspective?

---

I use videocompress to compress videos to ultra-short file sizes, with quality something that deteriorates acceptably. My quality choice reflects that. Make sure your change aligns with that philosophy.

---

These WIDE SHOT videos are rare and I'm OK to treat that as exceptions.

<!-- codex resume 01a1cd24-583e-7ad2-aa5a-6cfe2ded7019 -->
