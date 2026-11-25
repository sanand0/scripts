# setup

Prompts for setup.{fish,bash}.

## Improve plutoniun setup, 25 Nov 2026

The Herdr app in installed on this Windows machine. Remove it, and all related data, settings, etc.

---

How many Claude Codes are installed on this system? I think there's one installed via winget, one installed via npm somehwere, many multiple npm installations. Locate all and identify their versions. Similarly for codex, agy, copilot (GitHub) and pi.

---

Implement your suggestion #1 - delete old mise folder, etc. Remove C:\Apps\nodejs. Re-install pi and copilot CLI with Node A's npm as you suggested. Delete the two leftover .codex-* folders. Give me the command to remove the winget Claude code and I'll do that. Update ~/code/scripts/setup/windows.md with the instructions to set up this configuration on a new laptop.

---

I ran step 1. Check if that worked. After that, I'll exit this process and run winget uninstall --id Anthropic.ClaudeCode --exact

---

PS C:\Windows\System32> winget uninstall --id Anthropic.ClaudeCode --exact
Found Claude Code [Anthropic.ClaudeCode]
Starting package uninstall...
An unexpected error occurred while executing the command:
remove: Access is denied.: "C:\Users\Anand\AppData\Local\Microsoft\WinGet\Packages\Anthropic.ClaudeCode_Microsoft.Winget.Source_8wekyb3d8bbwe\claude.exe"
Uninstall failed with exit code: 0x8a150003 : Executing command failed

But now you're a different Claude instance. See if you can uninstall the winget one.

---

On VS Code when I run `bash` from Cygwin's fish, I get this error: `Error: cannot operate on non-existent file "C:\\c\\Dropbox\\scripts\\.env"`.
How do I fix this? Ideally, I want to use C:\Dropbox\scripts\.env. And it should continue working on graphene - my Linux machine - as it currently is.

---

I'll fix the copilot and opencode abbreviations myself.
I added $env:APPDATA/sops/age/keys.txt and was able to decrypt the Dropbox/scripts/.env file.
But now bash reports this error:
could not read config file: open /home/Anand/Dropbox/scripts/.sops.yaml: The system cannot find the path specified.

<!-- claude --resume d5799600-2d53-4f21-99ed-0476c31e6421 -->

## Remove herdr, 25 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.2-sol --config model_reasoning_effort=medium
-->

Herdr was installed via `curl -fsSL https://releases.herdr.dev/app/install.sh | sh` and run. Remove the app and all related settings, data, etc.

<!-- claude --resume 1dd0ac47-b8b3-432d-a271-9b436f915369 -->

## Plutonium skills, 25 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.2-sol --config model_reasoning_effort=medium
-->

You can `ssh plutonium` to the Plutonium server.
See ~/code/skills/INSTALLATION.md for how to set up agents.
Update `setup/windows.md` with the agent setup instructions for Windows on Plutonium.
Apply the instructions and verify for codex, agy, claude, and pi. (If you're actually using agents, choose the cheapest models - gpt-6-luna, claude-haiku-5.5, etc.)

---

FYI: I deleted the plugin (just to test), renamed it to "Anand Skills", and added it again.
https://chatgpt.com/plugins/Plugin_250a6b65220081918c8ddc5236fff181
This has an upload new version button. To use that, does the ZIP need to have a different version number? If so, `just new-version zip` should increment the version number (just the minor version) and create the zip.
Test it.

<!-- codex resume 01a2104b-74c9-73f1-92bd-16a6362aa03d -->

## Avif fix, 16 Nov 2026

<!--
cd ~/code/scripts
codex --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

See `setup.fish` for the `avif` function. It currently fails with the following error on ~/Downloads/

```
❯ avif --width 1024 --quality 20 --speed 0 Pocket\ Professor’s\ Tenure\ Test.png
[yuv4mpegpipe @ 0x62c5eb0ae4c0] ERROR: yuv4mpeg can only handle yuv444p, yuv422p, yuv420p, yuv411p and gray8 pixel formats. And using 'strict -1' also yuv444p9, yuv422p9, yuv420p9, yuv444p10, yuv422p10, yuv420p10, yuv444p12, yuv422p12, yuv420p12, yuv444p14, yuv422p14, yuv420p14, yuv444p16, yuv422p16, yuv420p16, yuva444p, gray9, gray10, gray12 and gray16 pixel formats. Use -pix_fmt to select one.
[out#0/yuv4mpegpipe @ 0x62c5eb0b1b80] Could not write header (incorrect codec parameters ?): Invalid data found when processing input
[vf#0:0 @ 0x62c5eb0b4b00] Error sending frames to consumers: Invalid data found when processing input
[vf#0:0 @ 0x62c5eb0b4b00] Task finished with error code: -1094995529 (Invalid data found when processing input)
[vf#0:0 @ 0x62c5eb0b4b00] Terminating thread with return code -1094995529 (Invalid data found when processing input)
[out#0/yuv4mpegpipe @ 0x62c5eb0b1b80] Nothing was written into output file, because at least one of its streams received no packets.
frame=    0 fps=0.0 q=0.0 Lsize=       0KiB time=N/A bitrate=N/A speed=N/A elapsed=0:00:00.08
```

What's the cleanest, future-proof, elegant fix? Update `setup.fish` accordingly.

---

When I use `avifenc -q 20 --speed 0 --jobs (nproc) image.png` on `~/Downloads/image.png` it created `~/Downloads/image.avif` which is larger than what https://squoosh.app/editor created - see `~/Downloads/squoosh-image.avif`.
Squoosh is open on my browser (see devtools skill - CDP localhost:9222) if you want to compare settings.
How do I get `avif` to reproduce the same settings minimally?

--- <!-- steering -->

Feel free to check the source code for squoosh and see if you can optimize further in line with how squoosh does.

<!-- codex resume 01a1e375-c7a3-75d2-bfb7-cee993fcdf17 -->

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
