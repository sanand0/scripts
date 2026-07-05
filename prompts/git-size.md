# git size

## Size staged files by default

<!--
cd ~/code/scripts
dev.sh -- codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium
-->

Is it possible to easily and minimally modify `git-size` to size staged files (i.e. `git add`-ed) by default, with an option to size all files (i.e. `git ls-files`) instead?

---

Actually, `git size --all` should show only files what _would_ get committed, not all files. (I think that might have been the earlier behavior?)
In any case, what's the minimal change to do this?

<!-- codex resume 019f26b4-ac2b-77f0-a6ac-f2384de3cc2f --yolo -->
