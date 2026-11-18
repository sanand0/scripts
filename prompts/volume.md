# volume

## Experiment and implement

<!--
cd ~/code/scripts
codex --model gpt-6.2-sol --config model_reasoning_effort=medium
-->

Is it possible to control my system volume just like how I control my mic volume?
Specifically, `wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 2` sets the mic volume to 200%, beyond the default 100% limit.
Can I do that for system output volume as well, i.e. the speaker volume? (I know `amixer sset` works well and I use it in touchegg.conf, but maybe there's a better way.)
I'd like that to reflect in the Gnome toolbar volume control as well.

If so, I'd like a GNOME toolbar control similar to ai-usage/ that

- shows the current volume levels - both mic and system output - as percentage (no decimals)
- clicking on it shows a slider that lets me adjust the volume levels, letting me go from 0% to 200% for both mic and system output (showing the % as I adjust the slider)

I would also like to update `touchegg.conf` so that the 4-finger swipe up/down with CTRL pressed adjusts the mic volume, and without CTRL pressed adjusts the system output volume (which is the current behavior).
The volume change should be reflected in the GNOME toolbar control as well, live.

I don't it to be as light as possible on resource usage, and reliable, robust, elegant, and minimal.

Build this in volume/ as a GNOME extension and install and test (or let me know how to install so you can test it).

---

❯ bash install.sh
Extension “volume@sanand.net” does not exist
Installed. After restarting GNOME Shell, run: gnome-extensions enable volume@sanand.net

❯ gnome-extensions enable volume@sanand.net
Extension “volume@sanand.net” does not exist

How do I restart GNOME Shell?

<!-- codex resume 01a1ec2b-46e6-71b1-9884-dc921ed3e065 -->
