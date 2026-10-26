# Edge Server

## Build Edge Server, 26 Oct 2026

<!--
cd ~/code/scripts
claude --model opus --effort medium
-->
<!-- source: https://claude.ai/chat/152e478a-ba9c-4edd-9599-ca5fd4d73302 + https://chatgpt.com/c/6adf3525-2698-83ec-a7a3-6f25be9cfdeb -->

```markdown
Build `edgeserver`: a phone remote for presenting Edge tabs at workshops. Read agents/AGENTS.md first.

## End state

- `edgeserver` (uv single-file script + one static HTML/JS page) runs on 127.0.0.1, talks to Edge CDP at localhost:9222.
- Exposed to my Android phone (Chrome) via `tailscale serve` HTTPS on a dedicated port (HTTPS is needed for Wake Lock; never expose CDP). Check `tailscale serve status` first; don't take over the hostname root.
- `edge serve` is a thin alias that execs edgeserver. Don't refactor `edge`; reuse its CDP techniques (tab targets with embedderData.tabStripIndex/tabActive, Browser.getWindowForTarget, Target.activateTarget).

## Design principle

The phone is a blind trackpad. I look at the projector, not the phone, so feedback appears on the projected tab. The phone surface maps proportionally onto the stage tab's viewport.

## Present mode (default, full-screen, touch-action:none, overscroll-behavior:none)

- 1-finger drag: scroll. Dragging X% of pad height scrolls X% of the visible viewport. No momentum. Implement as CDP mouseWheel at the mapped point (scrolls inner panels under the point; at zoom >1 it pans the visual viewport first, verified).
- 2 fingers: on touchdown show a ring at the mapped midpoint; start scaling only after spread changes ~8% (lets me aim). Zoom anchored at the midpoint, no reflow. 2-finger move while zoomed = pan.
- Double-tap: restore the last checkpoint. Push a checkpoint when a zoom starts from scale 1, on tab switch, and on viewpoint jump, not on every scroll. Capture tab, scale, visualViewport offsets, scrollX/Y, and the scroll position of the scroller under the anchor. Best-effort. Keep checkpoints per tab across switches.
- Hold still ~350 ms then drag: pointer mode (buzz), ring follows the finger, hidden on release. Can be toggled off.
- Clean tap in bottom-left / bottom-right corner: previous / next tab in the playlist.
- Swipe down starting in a header strip: Select mode. Do NOT use side-edge or top-edge swipes (Android Back / notification shade).
- Haptics via navigator.vibrate with distinct patterns per event.

## Select mode (the only mode I look at)

- Windows labelled by active-tab title + tab count → tabs in tabStripIndex order (fallback for tabs without an index).
- Tap tab: activate it, raise its native window, return to Present. Verify Target.activateTarget raises the window on GNOME/X11; else use wmctrl/xdotool.
- Lock a stage window. Playlist: tick the tabs that take part in prev/next; persist per URL.
- Save named viewpoints here (same state as a checkpoint plus a text/element anchor where practical); list them for jumping.

## Zoom: spike first, decide by measurement

Tested on Edge 156 (headless and Xvfb-headed):

- `Input.synthesizePinchGesture` {x:600,y:400,scaleFactor:1.5,relativeSpeed:2000} works and anchors exactly, but it is animated.
- `Emulation.setPageScaleFactor(2)` is instant but anchors at top-left.
- mouseWheel at 2× pans the visual viewport (delta/scale CSS px) before scrolling the document.
  Candidate A: setPageScaleFactor + compensating pan (Δoffset = a/s_old − a/s_new CSS px). Risk: the compensating wheel lands over an inner scroller and scrolls that instead.
  Candidate B: small incremental synthesizePinchGesture calls.
  Pick whichever keeps the anchor within a few px and feels continuous on the real headed window.

## Ring overlay

Injected position:fixed element, pointer-events:none, max z-index, sized inversely to visualViewport.scale, no layout impact. Or use CDP Overlay.highlightRect if cleaner.

## Transport and resilience

- One WebSocket. The phone sends the latest gesture state; the server coalesces to frame rate and drops stale frames, so movement stops the instant I lift.
- One persistent CDP session to the stage tab, re-attached on tab switch, commands serialized.
- The server pushes state (windows, tabs, active tab, scale, playlist, viewpoints).
- Phone shows a thin green/red status band and a small measured round-trip time. Auto-reconnect. Re-acquire Wake Lock on visibilitychange.

## Later: design for it, don't build

Clickable buttons. Keep messages semantic ({kind, ...}) with a server capability list, so we can add `actions.list` (visible buttons from DOM + accessibility tree, with ids and rects) and `click` (a CDP mouse event at rect center, for real user activation) as a third mode. Tap-to-click in pointer mode only behind an explicit mode.
Also deferred: haptic absolute scrubber.

## Order (report results after step 1 before continuing)

1. Spike scroll + zoom on a throwaway tab you create via Target.createTarget in my real Edge and close afterwards. Test a long page, a nested-scroll dashboard and a Google Doc. Report anchor drift, pinch smoothness, stop-on-lift, latency.
2. Present + Select modes + playlist.
3. Checkpoints, pointer mode, viewpoints.
4. Tailscale serve, reconnect, wake lock; add `tailscale ping` (direct vs relayed) to a pre-talk check.

README section starts with the end state, one line per command.

Never close, navigate or modify my existing tabs beyond activating them.
```

---

Proceed

---

I ran edgeserver and get a CalledProcessError: Command '['tailscale', 'serve', '--bg', '--https=8765', 'http://127.0.0.1:8765']' returned non-zero exit status 1.

---

It looks too dark to be visible on my phone screen. Maybe because some dark mode override setting on Edge. Maybe full screen isn't a great idea either - I forgot how to get out of full screen mode.

<!-- claude --resume d9044060-e78d-4951-914e-8e15262e0d2c -->
