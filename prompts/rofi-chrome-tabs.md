# rofi-chrome-tabs

## Use edge instead of CDP, 17 Jul 2026

<!--
cd ~/code/scripts/
codex --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

`rofi-chrome-tabs.sh` uses CDP to list tabs. But this lists only non-sleeping tabs.
`edge tabs` lists the full list.
Is it possible to modify `rofi-chrome-tabs.sh` to use `edge tabs` instead of CDP to identify the tabs, but still activate the tab using CDP?
This requires identifying the CDP ID of the tab from the `edge tabs` output.
If it's possible and required, feel free to edit `edge` minimally, too.
If it's not possible, let me know and don't change anything.

--- <!-- steering -->

If the smaller change is that we just use the hidden tab target directly via CDP and don't need to touch `edge`, that's even better.

---

rofi-chrome-tabs.sh doesn't show the titles of sleeping tabs (though it DOES show the IDs).
That defeats the purpose of the script, which is to allow me to switch to a tab by title.
If it's possible to use CDP to get that information, do so.
If the only way is to modify `edge` to do this, modify `edge` minimally.

---

When I run this command on the command line, it works fine - opening rofi with the list of tabs.

```bash
rofi -show-icons -show combi -modes combi -combi-modes "window,🌍:/home/sanand/code/scripts/rofi-chrome-tabs.sh,📝:/home/sanand/code/scripts/rofi-files.sh" -kb-accept-alt "" -kb-accept-custom "" -kb-accept-custom-alt "" -kb-custom-1 "Shift+Return" -kb-custom-2 "Control+Return" -kb-custom-3 "Control+Shift+Return"
```

But when I run it from espanso's key bindings, window and rofi-files.sh work but the output of rofi-chrome-tabs.sh is missing. Some path issue or permission issue or something?

---

Yeah, it was the `edge` path. I fixed it. No action required.

---

`edge tabs --json --cdp-url http://localhost:9222` in rofi-chrome-tabs.sh takes over 300ms to run. How can we speed it up?

---

`edge tabs --json` takes ~100ms.
`edge tabs --json --cdp-url http://localhost:9222` takes ~180ms.
Can that 80ms gap be closed?

--- <!-- steering -->

That 80ms can't be dependencies or uv, right - the only difference is the cdp flag...


--- <!-- steering -->

I'm not too keen to over-engineer for 80ms, BTW.

<!-- codex resume 019f6f03-10e1-73a0-831a-158405f70c46 -->
