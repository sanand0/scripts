# linkedin

## Initial research, 08 Nov 2026

<!--
cd ~/code/research/linkedin-cli
codex --model gpt-6.1-sol --config model_reasoning_effort=high
-->

Is it possible to create a LinkedIn CLI using the underlying LinkedIn API? Ideally, I'd like something that reverse engineers the API like I think [whatsmeow](https://github.com/tulir/whatsmeow), [twitter-cli](https://github.com/public-clis/twitter-cli), [rdt-cli](https://github.com/public-clis/rdt-cli) do.

LinkedIn is logged in on my browser via CDP on localhost:9222. Prefer background operations rather than bringing the browser to the foreground. See the devtools skill. Research the LinkedIn API and see if searches, user profiles, user activity feeds, my feed, etc. can be exposed / synced via a CLI.

Document your research in RESEARCH.md and recommend a design for an agent-friendly LinkedIn CLI.

---

Implement a LinkedIn CLI. Think about the most common operations. Use my browser history at ~/Documents/data/browsing-history.db as a reference.
Make sure it syncs data to a local cache so that it can be searched offline, efficiently.
Use relevant skills. Test against common scenarios.

--- <!-- steering -->

See ~/code/scripts/ for LinkedIn related scripts which might provide additional use cases. Factor these in into the capabilities we want the CLI to have.
Think about how best to design for these - as well as future - capabilities.
Keep things simple, modular, and easy-to-understand and extend.

---

Make markdown the default format and `md` an alias for markdown.
Document search filters in help, e.g. search by location, organization, degrees of separation, etc.
Implement and document how to fetch / sync / update post analytics; for example likes, comments, reposts, impressions, ... for the logged-in user.
Convert this to a single-file script and copy it into ~/code/scripts/, along with a single-file test case in ~/code/scripts/tests/ that will run as part of the ~/code/scripts/ `just test` suite.

---

Make all Markdown outputs more intuitive and easier to read - like real-life useful Markdown files.

---

Could the script in ~/code/scripts/linkedin.mjs be converted to just `linkedin` and be made to work? I don't want ~/.local/bin/linkedin. ~/code/scripts/ is already on my path.

Also, the Markdown output will often be read on the terminal. I prefer less vertical size. For example, I would have written:

```
# Post analytics

From 30d

4 posts
```

... as just:

```
# Post analytics (30d, 4 posts)
```

Also, links take up too much space and I prefer links at the end of rows than the start or middle. For example:

```
| Name | Headline | Location |
| --- | --- | --- |
| [First Last](<https://www.linkedin.com/in/abcd>) | Engineer at Microsoft | Bengaluru |
```

... I would prefer:

```
| Name | Headline | Location | Link |
| --- | --- | --- | --- |
| First Last | Engineer at Microsoft | Bengaluru | https://www.linkedin.com/in/abcd |
```

Lists are easier to process than tables, sometimes (especially for metric & value). For example,

```
| Metric | Value |
| --- | --- |
| Profile views | 8 |
| Followers gained | 0 |
```

... could be written as:

```
- Profile views: 8
- Followers gained: 0
```

---

I would like to subsume the functionality of backuplinkedin.py into this `linkedin` CLI.
The output of `backuplinkedin.py` is used by ~/code/blog/
I'd like to just retain the existing script.
What do you suggest, A, B, or something else?
A. Migrate the existing backup data from backuplinkedin.py into the format used by the new `linkedin` CLI, and revise the code in ~/code/blog/
B. Modify the new `linkedin` CLI to export in same format as backuplinkedin.py, so that ~/code/blog/ can continue to use it without changes.

---

Implement B, move backuplinkedin.py into archive, and add an abbreviation in ~/code/scripts/setup.fish mapping backuplinkedin.py to an appropriate linkedin command.

---

If we can move the tests for `linkedin backup` into `tests/test_linkedin.mjs` we can archive the older version of `tests/test_backuplinkedin.py`. That might be cleaner.
For search, I would like to be able to search for location using partial matches, e.g. "Chennai", "Singapore", "Boston"; for organizations using "IBM", "Tata"; same for past organizations.
For `linkedin activity PROFILE` (and any other subommand that requires a profile) allow a name, e.g. `linkedin activity "First Last"`, apart from a profile URL. Pick the first matching search relevant for the logged-in user.
Whenever displaying posts, include the date & time near the top (if possible and easy.)
Unless the output is piped, show markdown output piped via `glow -p`.

--- <!-- steering -->

Correction: use all matches with OR. I revise what I thought.

--- <!-- steering -->

If glow is not available, use PAGER, else skip.

--- <!-- steering -->

Include a `linkedin scheduled` command to show scheduled posts, if any. It should include the scheduled date/time and contents.
Include a `linkedin paths` that shows the paths of backup, cache, config, and any other relevant files used by the app.
Check why `linkedin connections` reports an ok: false right now with a SCHEMA_CHANGED and a "Connected profile is missing" error.

<!-- codex resume 01a1bb3a-9f4c-7951-8dd2-d7c86baec2a5 -->

## Fix need for initial tab to be open, 27 Jul 2026

<!--
# Initially created at ~/code/private-research/linkedin-cli/

cd ~/code/scripts/
dev.sh -- codex --yolo --model gpt-5.6-sol --config model_reasoning_effort=medium
-->

Modify linkedin.py (and tests/test_linkedin.py) to not require an initial LinkedIn tab to be open.
Assume CDP at localhost:9222 is logged in.
Use this as an opportunity to SHORTEN and simplify the code, not increase it.

<!-- codex resume 019fa297-e100-7f53-91da-3af1f50730c5 --yolo -->

<!-- #TODO: Maybe extend linkedin.py to cover /recent-activity/all/ and /details/{certifications,volunteering-experiences,projects,skills,recommendations,courses,honors,interests,languages}
