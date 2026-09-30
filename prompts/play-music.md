# play-music

## Accept partial matches, dry-run, 30 Sep 2026

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-6-luna --config model_reasoning_effort=high
-->

Modify play-music minimally so that if the argument does not exactly match a file in ~/Music, accept partial case-insensitive exact matches.

---

Minimally add an agent-friendly CLI option to just print the 10 recommended songs, without playing them.

---

Rename it to --dry-run

<!-- codex resume 01a0f0ef-935f-7b13-b552-1c43876aeba5 --yolo -->

## Improve recommendations, 27 Sep 2026

<!-- Revise play-music recommendations: https://chatgpt.com/c/6ab8eceb-ae40-83ec-abbf-48807497cb31 (2026-09-27T19:14:32+08:00) -->

On @LocalMCP2 the script ~/code/scripts/play-music plays the selected MP3 followed by 10 random MP3s from ~/Music.

I'd like to have it pick songs that are similar to the selected MP3 - based on ~/Music/musicdump.csv.

By similar, I mean similar Genre (Tamil and Telugu are closer than Tamil and Hindi), Year, Composer, Singer, Title, etc.

Keep in mind that my aim is not to pick the songs just "similar" to it. It is to pick songs I'd like to listen to next, after having heard this song. I'm using similar as my guess for that.

Think about and research what columns should be chosen, how these should be weighted based on well-established research on listener preferences - especially for Indian film music (Hindi, Tamil in particular) and how best to craft the similarity metric. Don't complicate it too much - I want it simple enough (and coded and documented simply enough) that I will be able to reason about it and change it.

Test it out, compare with good, well-known and well-admired recommendation engines. The songs in ~/Music/New.m3u are songs I listen to often, recently, and might serve as a testing seed. Revise the algorithm as required.

Finally, share how you have revised play-music and the rationale.

You're welcome to convert play-music into a uv-based Python script, similar to some of the other scripts in the directory, if that'll help. Your choice.

---

I collect songs I like into M3U files that are in ~/Music/ (which should be accessible now). Maybe we should give them a slightly higher weightage. But not all M3U files. Appa\*.m3u are my father's playlists. So, what's a good way to incorporate this without overwhelming the current ratings yet nudging a little towards what I'd like, while keeping things simple?

Now that you have access to ~/Music/ if there's something you need to test there, feel free to do that as well.

---

Save play-music in ~/Downloads/ and I'll copy it to ~/code/scripts/

## Initial version, 12 Sep 2026

<!-- https://chatgpt.com/c/6aa56e44-0590-83ec-bc9e-6b854f52add0 -->

Take a look at @LocalMCP scripts at ~/code/scripts/

When I press Ctrl+Alt+F a rofi popup shows me a list of files.
When I press Enter, it opens the file.

What's the minimal modification so that when I open a .mp3 file from ~/Music/ it automatically selects 10 random .mp3 files from ~/Music/ and opens those as well on VLC? In other words, when I open the file, it queues 10 more songs randomly.

Over time, I'll probably want to change / improve the mechanism, so a separate file might be worth implementing. Look at the files in the directory and relevant skills and suggest an implementation. No need to actually implement it.

---

Go ahead and implement.

---

VLC opens all files and adds them to the queue but starts paying the last added song. My intention is that it should add the song I run, play that, and the rest of the songs should queue after that. What's the minimal way of doing this?

---

Is there a mechanism in VLC to enqueue to an existing one-instance player?

---

I have playerctl installed. Does that help?

---

Implement this change.

---

Instead of playerctl could we use something like

dbus-send --type=method_call --dest=org.mpris.MediaPlayer2.vlc /org/mpris/MediaPlayer2 org.mpris.MediaPlayer2.Player.PlayPause 2>/dev/null

---

Would this also be apt as a playerctl replacement for services/vlc-history.sh?

---

OK. Replace playerctl in play-music
