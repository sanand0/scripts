# play-music

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
