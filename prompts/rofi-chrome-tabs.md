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

<!-- codex restore 019f6f03-10e1-73a0-831a-158405f70c46 -->
