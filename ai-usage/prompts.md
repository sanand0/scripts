# ai-usage

## Cache results, 13 Oct 2026

<!--
cd ~/code/scripts/
dev.sh -- codex --yolo --model gpt-6.1-sol --config model_reasoning_effort=medium
-->

Minimally modify the ai-usage/ widget so that if `ccusage` or `codexusage` fail, it uses the last known value - which should persist even after a restart.

<!-- codex resume 01a134cc-1ebd-7122-aa05-50d362e928b7 --yolo -->

## Initial draft, 12 Oct 2026

<!-- 🔸Restart machine Gnome Widget for Codex Claude Code Usage: https://chatgpt.com/c/6acc703f-00b4-83ec-b7d6-4446af6a6bd2 (2026-10-12T17:45:25+08:00) -->

I'd like to add a widget to my desktop bar - ideally somewhere near where where my current Vitals@CoreCoding.com widget is - that shows my current Claude Code and Codex / ChatGPT usage. I should have an option to refresh it and change the auto-refresh frequency.

I've had previous conversations about this. You can see the past chats titled "Claude Code Usage on Ubuntu Dock" and on @LocalMCP2 check out ~/code/infra/dock-stats/

What's the cleanest, lightweight way to implement this - specifically for my system & configurations?

What's the easiest way to get the actual usage from Claude / OpenAI? Is there a supported API? What's the most robust and reliable way that others use?

---

OK, I'll go with your suggestion. I need Codex usage as in addition to Claude Code. Also, ccusage requires me to run Claude Code periodically - and if it's possible to avoid that, or refresh automatically, that'll be great. Update codexusage and ccusage as you think fit. Feel free to test.

What I want to see on screen is something like the icon, 5h usage, and 7d usage:

[Claude Icon] 17% | 21% [ChatGPT Icon] 0% | 1%

The panel display you showed is great - but also show how long until the next 5h or 7d resets (e.g. 2:03 or 2d 3h) as well as at what date / time (in an intuitive human-readable way).

Let me know when you need me to test on the host (since you can only access the container) and I'll test as required.

---

After running these steps, I don't see anything new on the dock. What do I need to do next?

---

❯ gnome-extensions info ai-usage@sanand.net
ai-usage@sanand.net
Name: AI Usage
Description: Claude Code and Codex subscription quota in the panel
Path: /home/sanand/.local/share/gnome-shell/extensions/ai-usage@sanand.net
Version: 1
Enabled: Yes
State: ERROR

❯ gnome-extensions list | grep ai-usage

ai-usage@sanand.net

❯ gnome-extensions info ai-usage@sanand.net
ai-usage@sanand.net
Name: AI Usage
Description: Claude Code and Codex subscription quota in the panel
Path: /home/sanand/.local/share/gnome-shell/extensions/ai-usage@sanand.net
Version: 1
Enabled: Yes
State: ERROR

❯ journalctl -b --no-pager | grep -i 'ai-usage@sanand' | tail -30
Oct 12 15:20:37 graphene dbus-daemon[1875]: [session uid=1000 pid=1875] Activating service name='org.gnome.Shell.Extensions' requested by ':1.304' (uid=1000 pid=399920 comm="gnome-extensions enable ai-usage@sanand.net" label="vscode (unconfined)")
Oct 12 16:28:57 graphene dbus-daemon[467613]: [session uid=1000 pid=467613] Activating service name='org.gnome.Shell.Extensions' requested by ':1.122' (uid=1000 pid=473367 comm="gnome-extensions enable ai-usage@sanand.net" label="vscode (unconfined)")
Oct 12 16:28:58 graphene gnome-shell[468027]: Extension ai-usage@sanand.net: Error: Tried to construct an object without a GType
UsageIndicator@file:///home/sanand/.local/share/gnome-shell/extensions/ai-usage@sanand.net/extension.js:34:9
enable@file:///home/sanand/.local/share/gnome-shell/extensions/ai-usage@sanand.net/extension.js:195:27
Oct 12 16:29:04 graphene dbus-daemon[467613]: [session uid=1000 pid=467613] Activating service name='org.gnome.Shell.Extensions' requested by ':1.124' (uid=1000 pid=473640 comm="gnome-extensions info ai-usage@sanand.net" label="vscode (unconfined)")
Oct 12 16:29:26 graphene dbus-daemon[467613]: [session uid=1000 pid=467613] Activating service name='org.gnome.Shell.Extensions' requested by ':1.128' (uid=1000 pid=474430 comm="gnome-extensions info ai-usage@sanand.net" label="vscode (unconfined)")

---

That worked.

A few changes: Use color to visually differentiate the content and make it easier for me to understand. For example, use the Anthropic color for the Anthropic logo. I think the OpenAI logo is in white and black anyway. Don't make the text at the bottom bar bold - it currently looks bold. When I click on it and the popup opens, show text like this:

5h: <bold+color>25%</bold+color> - <color>0:17 m - Mon 12 Oct 5:10 pm +08</color>
7d: <bold+color>22%</bold+color> - <color>3d 1h - Thu 15 Oct 6:00 pm +08</color>

Each should appear in a single line - so the bar needs to be wide enough for that.
bold + color means that it should be in bold, and color means green for <70% and amber for <90% and red for 90%+. The <color> for the time should show amber if a 5h reset is due within 1 hour and red if it's due in 30 minutes. For the 7d reset, show amber for 1 day and red for 12 hours.

Also, change the 15 min refresh duration to 10 minutes.

Then, I'd like to move the script from ~/code/infra/dock-stats/ai-usage/ to ~/code/scripts/ai-usage/ so that I can install it from here later. Document it for the first time-user (i.e. someone completely unfamiliar with this conversation, doesn't care about the versions, debugging issues we faced, etc. and just wants to know how to install and use it.) Also update ~/code/scripts/README.md and any other related files. Since I've already copied ccusage and codexusage to ~/code/scripts, if they're not required, let's drop them. Revise the paths in install.sh as required.

Let me know if this requires a login or it can be done without a login.

---

@LocalMCP2 is available now

---

Why is ~/code/scripts/ mounted read-only? Is there something in ~/code/scripts/{mcpserver,dev.sh,mcpserver.py,...} that prevents ~/code/scripts/ from being writeable? I invoked it as mcpserver -p ~/Downloads,~/code,~/Dropbox/notes:ro,~/r2:ro,~/Documents:ro - so I was expecting ~/code/scripts to be writeable. No need to make any changes - but if there's a minimal safe change I can make, let me know what to change where. If it's more complex than that, explain what's causing it and what it takes to fix it and I'll review that.

---

OK, I've made the change and restarted @LocalMCP2

Now, you should be able to directly edit in ~/code/scripts/

A few points:

I prefer ccusage and codexusage to remain in ~/code/scripts/ since that's on my path and will make things easier.
I prefer ai-usage/ to be flat - so can we move what's in ~/code/scripts/ai-usage/gnome/ one level up?
Can we remove anything that's not required, or a historical artifact, if it still exists?

---

A few more tweaks.

On the bottom bar, color the percentages based on the time left. So, for example, the Claude 5h percentage would be amber if a 5h reset is due within 1 hour and red if it's due in 30 min. Same for the 7d percentage. Likewise for Codex.

In the popup, apply the color only to the remaining time, i.e. like this:

5h: <bold+color>25%</bold+color> - <color>0:17 m</color> - Mon 12 Oct 5:10 pm +08

Increase the font size for "Updated x min ago".

Reduce the width of the popup - it feels too wide now.

Let me know if I need to restart.
