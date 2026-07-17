# Prompts

## Handle multiple profiles, 17 Jul 2026

<!--
cd ~/code/scripts
dev.sh -p ~/.config:ro,~/Documents/data -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

I'm mainly using `~/.config/microsoft-edge-cdp/` instead of `~/.config/microsoft-edge/`.
Modify `browsing_history.py` to use that as the default.

While you're at it, just check: is it already picking up from BOTH the .config directories?
Both of them are synced to the same account.
This also includes workspaced.
I just want to make sure that there's no duplication of history when we update the browsing history database.

Explore carefully and make sure that the history is being read from the right place, and that it is being updated correctly in the database without duplication. Test.

---

FYI: I'm perfectly OK with the script picking up from either/both locations as long as it's deduplicated.

<!-- codex resume 019f6ee7-ead8-7171-a22c-03b5695242ff --yolo -->

## Explore, 13 May 2026

<!--
cd /home/sanand/code/scripts
dev.sh -v /home/sanand/.config/microsoft-edge/:/home/sanand/.config/microsoft-edge/:ro -v /home/sanand/Documents/data/:/home/sanand/Documents/data/
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Write an agent-friendly CLI script `browsing_history.py` that will export my Edge browsing history (possibly at ~/.config/microsoft-edge/). Make sure that it exports the full history, across workspaces. Use CDP at 9222 to test. Make sure it works even if Edge is running by reading it without a lock.

The CLI should export as TSV (default), CSV, or JSON. Ensure that it includes the timestamp, URL, and any other relevant metadata. Be efficient. Run and test - but no need to write test scripts.

---

/home/sanand/.config/microsoft-edge/ is now read-only and has the history. Test.

---

Is it possible to easily avoid copying History and read directly? If so, update the script to do that instead, if it will reduce complexity and lines of code and improve performance, not otherwise. Test.

---

Confirm that you can locate my browsing history for the last 6 months.

---

I think Edge keeps history for at least 3 months. Can you search and find if it's anywhere else?

---

OK, extend the script to include whatever fields can be recovered for URL activity as far back as possible.

---

I would like to build a database of the browsing history at ~/Documents/data/browsing-history.db as a single-file database (SQLite or DuckDB - whichever is easier and more efficient).
Modify browsing_history.py to update that database with the latest browsing history (including new entries - but is it even possible that existing entries need to be updated? Maybe not, but check if that's required) and respond from the database.
Run and test. Use CDP to update browsing history and confirm that the database is updated.

<!-- codex resume 019e1ea3-c63c-73d2-a288-43d35e3c7d2d --yolo -->
