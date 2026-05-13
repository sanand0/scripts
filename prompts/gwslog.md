# gwslog

<!--

cd /home/sanand/code/scripts
dev.sh -v /home/sanand/code/infra/gws:/home/sanand/code/infra/gws:ro
codex --yolo --model gpt-5.5 --config model_reasoning_effort=medium

-->

## Initial version, 09 May 2026

<!-- metaprompt: https://claude.ai/chat/41fb6c3d-014d-461b-ac37-a493af934ac7 -->

Read /home/sanand/code/infra/gws/gws-log-changes.md to understand how to use `gws` CLI to list changed files.

Create an agent-friendly `gwslog.py` Python script (like `transcribe_calls.py`) that I can use as follows:

```bash
# Show 100 most recent changes: date (relative)
gwslog.py
```

Add well-documented CLI options for:

- display columns via `--columns`. Default to `--columns date,user,name,type,size,link,path`. Support at least these columns:
  - `date` (relative), `iso`, `human` - all three available simultaneously
  - `user` (last modifier email), `name` (= title), `type` (mime → short label like `doc`, `sheet`, `slide`, `pdf`), `mime` (raw mime), `ext`, `size` (humanised), `bytes` (raw), `link` (webViewLink), `path` (cached folder path), `id`, `parent_id`, `drive` (shared drive name), `version`, `created`, `modified_by_me`, `owner`.
- formatting as relative date-time / ISO time / human-friendly time
- filtering by
  - date range (--since, --until). Document `--since $(date -d '7 days ago' +%F)` and similar usages.
  - --folder: SUBSTR folder name, a path fragment (/Innovation/Drafts), or a folder ID. Resolves against the cached folder tree.
  - --type: doc, sheet, slide, pdf, video, image, folder, plus escape hatches ext:opus, mime:application/vnd.google-apps.spreadsheet.
  - --name SUBSTR: plain substring filter on the file name.
  - --path SUBSTR: filter by file path.
  - --user / --owner SUBSTR to filter by lastModifyingUser or owner
  - --shared-drive NAME_OR_ID to --my-drive toggle to filter by shared drive or my drive.
  - --mine-only to show only files I modified
  - --exclude-trashed on by default; --include-trashed to include them.
  - --n / --limit; default 100
- `--format text|json|tsv|jsonl|md`. `text` is colorised TSV, JSON/JSONL for piping to `jaq`. Default to `text` when `sys.stdout.isatty()` else `jsonl`.
- `--describe` flag printing a JSON blob of the command's metadata (options, valid column tokens, output schema)

Stream rows, don't buffer.

```bash
gwslog.py tree [--folder ID] # print the cached folder tree as indented text or JSON. Useful by itself; gws-log-changes.md already has the recipe.
gwslog.py show $FILEID # full metadata for one file, including headRevisionId, checksums, version, owners, parents resolved to a path. agentlog's resolve is the model.
gwslog.py refresh # explicitly refresh cache (folder tree, recent files snapshot) without printing the log, in case you want to warm the cache after restoring ~/.config/gwslog/.
```

To get the path (list of parent folder names as `/$FOLDER_NAME/$FOLDER_NAME/...`), cache & refresh the folder tree metadata.

Caching specifics:

- Layout under `~/.config/sanand-scripts/gwslog/<account>/`:
  - `folders.json` — flat map of `{id: {name, parents, driveId}}` for path resolution.
  - `files.jsonl` — last `files.list` page contents, append-only with a max age + max rows, so reruns within an hour skip the API.
  - `changes.token` — the saved `newStartPageToken` for incremental mode.
  - `drives.json` — list of shared drives the account can see, named so `--shared-drive Innovation` works.
- Cache key by query shape (account + folder + filters), the way `githubscore.api_cache` keys by SHA of the URL. Stale beyond `--max-age` (default 1 hour).
- `--no-cache` to bypass entirely, `--refresh` to force a rebuild — `agentlog.py --strict` / `skilluse.py --refresh` precedent.
- Log cache work to stderr (`refreshing folders... 1242 entries` style), keep stdout clean for piping.

Other features:

- `--dry-run` that lists what would be fetched / refreshed without calling the API. Every other tool has this.
- Fail fast on first error, no silent fallbacks.
- Honour `incompleteSearch` from the API: if true, print a warning to stderr and suggest narrowing with `--shared-drive`.
- A short `Examples:` block in the help string, in the `gmail.py` style, with the three or four invocations you'll actually type:
  - `gwslog.py --since 7d --type doc`
  - `gwslog.py --path Innovation --user s.anand@gramener.com --since 30d --format jsonl`
  - `gwslog.py --since 1d --columns "iso user title path link" | xclip -selection clipboard`
  - `GOOGLE_WORKSPACE_CLI_CONFIG_DIR=~/.config/gws-root.node@gmail.com gwslog.py since` (incremental feed)
- README.md one-liner + sub-bullets for `gwslog.py`, like `summarize.py`

---

This runs `gws` even when I rerun `gwscli.py` within a few seconds. That shouldn't be required, since we can check the cache for freshness.

Feel free to modify the cache structure if required.

- `--format text|json|tsv|jsonl|md`: always default to `text`, not JSON/JSONL - unless specified.
- `--color=auto|always|never` for text output. Default to `auto`: color if stdout is a TTY, no color if piped.
