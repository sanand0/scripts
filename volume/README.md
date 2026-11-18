# Volume

Speaker and microphone percentages in the GNOME top bar. Click the indicator for
two sliders from 0% to 200%. The sliders and labels follow the default devices
and update when another control changes their volume. A muted device shows its
configured level with a muted icon. Changing its gain preserves its mute state.

The extension uses GNOME Shell’s existing mixer and listens for changes.
Touchégg sends each swipe step to the extension over the session bus. Each step
changes the speaker by five percentage points, or the microphone while Ctrl is
held. Four-finger vertical swipes require the extension to be enabled. The
repository’s `touchegg.conf` is already linked on machines configured via
[`setup/linux.md`](../setup/linux.md).

## Install on GNOME 46

Run the installer from the repository root.

```sh
bash volume/install.sh
```

On Xorg, press Alt+F2, enter `r`, and press Enter to restart GNOME Shell. On
Wayland, log out and back in. Then run `gnome-extensions enable volume@sanand.net`.
Touchégg’s gestures require an Xorg session.

To check live synchronization from a terminal, try
`wpctl set-volume @DEFAULT_AUDIO_SINK@ 105%` or
`wpctl set-volume @DEFAULT_AUDIO_SOURCE@ 105%`. A target of `2` means 200%.
The stock Quick Settings control shares the underlying volume and saturates at
GNOME’s own display limit. The Volume indicator shows the full percentage.
