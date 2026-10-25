# Phone sync

## Initial version, created in infra/phone-sync, 25 Oct 2026

<!--
cd ~/code/infra/phone-sync
codex --model gpt-6.1-sol --config model_reasoning_effort=high
-->

My phone is connected via adb. I'd like to incrementally sync all useful information (list of all messages, call logs, etc.) in full detail to my laptop - saving results in ~/Documents/data/

- What can be fetched? (If you need permissions, feel free to ask.)
- How best to store it, keeping in mind that:
  - I want efficient incremental updates
  - will certainly add more data, apps and features to back up over time
  - might change phones at some point, and
  - probably won't change accounts or back-up other phones?

Test this out. Create a portable script similar to what's in ~/code/scripts/ to sync. Test the script. I will move it later to ~/code/scripts/

My aim is that I'll run this one agent-friendly CLI, e.g. `phonesync`, on a daily or weekly basis to sync all useful data.

---

Could we explore an alternate file format that's easy for me to browse through as well as for the script to update? I don't want to duplicate, but I want it atomic.

--- <!-- steering -->

For images, image files are fine. Basically, I want to be able to double click them on any file explorer and see the results. Or grep them where relevant.

---

OK, proceed to update phonesync and test - including incremental updates.

--- <!-- steering -->

Let's make it flatter. ~/Documents/phone-DEVICE-ID/...

--- <!-- steering -->

Sorry, ~/Documents/data/phone-DEVICE-ID/

<!--  codex resume 01a170c7-7c09-75b3-bc8f-c326b17c8dad -->
