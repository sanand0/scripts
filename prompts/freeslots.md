# freeslots.py

## Revisions, 25 May 2026

<!--
cd ~/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

When I run `freeslots.py --since 2026-05-27 --days 1` I get no free slots. But I see plenty of freeslots on my calendar for 27 May 2026.

What's happening and how do we fix this? Try and fix the general problem, not just the specific issue. Fix elegantly. Usually, great fixes reduce code while reducing bugs!

---

The holidays may not be relevant for the time zones I'm looking at. Modify the script to NOT ignore holidays but include them in the "If none of the above are suitable" section, mentioning them as a holiday (and mentioning WHAT holiday it is).

<!-- codex resume 019e5d8c-00d6-72b1-9906-3f4f313357be --yolo -->

## Initial script, 20 May 2026

<!--
cd ~/code/scripts
dev.sh
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

I'm often asked, "Could you suggest a few free slots for a meeting?"
I want to automate this process.

Write an agent-friendly CLI script `freeslots.py` that accepts these inputs:

- Optional time zone, default to my current time zone. Allow ET, EST, UK, "San Francisco", etc. Keep in mind the daylight saving time changes.
- Optional date range, default to the next 7 days.
- Optional working hours for the other person. Prefer 9 am - 6 pm but extend to 8 am - 7 pm if needed.
- Prefer scheduling meetings between 9 am - 9 pm in my time zone but extend to any open calendar slot between 7 am - 11 pm if needed.

... and uses `gws` CLI to find my free calendar slots and output them in a human-friendly format, sorted by preference.

Output should ALWAYS mention my current time zone as well as the time zone requested (if different) explicitly using the canonical abbreviation, factoring in daylight saving time changes.
Share preferred slots first, i.e. between 9 am - 9 pm in my time zone and the other person's working hours, followed by additional slots - as per the above rules.
Sort both lists of slots in chronological order.

For example:

```
Preferred slots:
15 May 2026: 8:00 am - 9:30 pm BST (12:30 pm - 2:00 pm IST)
16 May ...

If none of the above are suitable:
...
```

Run and test.
Update README.md.

---

Currently, the output is:

```
My time zone: +08 (Asia/Singapore)
Requested time zone: IST (Asia/Kolkata)
Calendar range: 20 may 2026 1:27 pm +08 to 27 may 2026 1:27 pm +08

Preferred slots:
20 May 2026: 11:30 am - 12:00 pm IST (2:00 pm - 2:30 pm +08)
20 May 2026: 12:30 pm - 1:30 pm IST (3:00 pm - 4:00 pm +08)
...
```

I would prefer:

```
Time zones: SGT (mine) and IST (requested)
Dates: 20 May 2026 + 7 days

Preferred slots:
Wed 20 May 2026: 11:30 am - 12:00 pm IST (2:00 pm - 2:30 pm SGT)
...
```

Also, avoid giving too many options during the day. Allow a customizable option to limit the number of slots per day, default it to 3, and prefer the longest slots of each day.

Avoid weekends and holidays unless explicitly requested by a CLI option.

Run and test.

<!-- codex resume 019e43d2-675d-7c11-ba08-433328ecb981 --yolo -->
