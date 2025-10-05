# Github Score

Original conversation with ChatGPT on how to evaluate developers on GitHub: https://chatgpt.com/c/68dd0b57-41cc-8328-9689-a21a98a0e5dd

## 2025-10-02 Prompt

Build a Python CLI script `githubscore.py` that takes 1+ GitHub user IDs and prints the output as YAML. Keep it under 350 lines.

Example: `uv run githubscore.py [--since YYYY-MM-DD] kanitw thejeshgn > githubscore.yaml`

Output format:

```yaml
- login: sanand0
  score: 39
  name: Anand S
  ... (emit all columns, with null where missing)
- login: mbostock
  ...
```

Requirements

- Use the **GitHub REST API v3** (JSON). Read `GITHUB_TOKEN` from env for auth.
- Do not handle errors in the code. Fail on first error.
- Cache all GitHub API requests at `~/.cache/sanand-scripts/githubscore/` for `--cache-days` (default: 7) days.
- Show progress via `tqdm` against users > metrics. Show API request on a separate line.
- If denominator for any ratio is zero, treat the value as zero.
- No PyYAML. Generate output as text.
- No test script required.

Limits

- Limit API responses to a single page where possible to reduce requests and increase speed
- Limit to `--max-repos` (default: 20, max: 100) repositories when processing multiple repos
- Limit activity to everything after `--since` (default: 18 months before today)

Columns (per user - render as a flat list in this order):

- `login`: user login
- `score`: see Score section below. Round to nearest integer
- **From user details**: From `GET /users/{login}` get:
   - `name:`
   - `company`
   - `location`
   - `email`
   - `hireable`
   - `blog`
   - `bio`
   - `created_at`
   - `followers`
   - `public_repos`
- **From recent repos** `GET /users/{login}/repos?type=owner&sort=pushed&direction=desc&per_page=${maxRepos}`. Keep only repos `fork == false`, `archived == false`, `is_template == false`, `pushed_at` since `--since`.
   - `recent_repos`: is the final count after filtering
   - `stars`: Sum `stargazers_count` across these repos
   - `readme`: # recent repos with README. `GET /repos/{o}/{r}/readme`
   - `license`: # recent repos with a LICENSE. `GET /repos/{o}/{r}/license`
   - `tests`: # recent repos with any Python / JS / ... testing paths/files.
   - `tags`: # of recent repos with tags `GET /repos/{o}/{r}/tags`
   - `semver` = # of recent repos with tags matching SemVer
   - `releases`: # of recent repos with releases `GET /repos/{o}/{r}/releases`
   - `ci`: # recent repos with CI. `GET /repos/{o}/{r}/actions/workflows` returns ≥1 workflow, **or** the default branch’s latest commit, `GET /repos/{o}/{r}/commits/{sha}/status` has any contexts/checks.
- `pr`: PRs opened in others' repos `GET /search/issues?q=is:pr+author:{login}+-user:{login}+created:>={since}&per_page=100`
- `pr_merged`: `GET /search/issues?q=is:pr+is:merged+author:{login}+-user:{login}+merged:>={since}&per_page=100`
- `issues`: Issues opened by the user: `GET /search/issues?q=author:{login}+type:issue+created:>={since}&per_page=100`
- `issues_closed`: Issues closed by user
- `reviews`: total PRs reviewed. `GET /search/issues?q=is:pr+reviewed-by:{login}+updated:>={since}&per_page=100`
- `review_repos`: distinct `owner/repo` count among reviewed PRs

**Score**

- `name`: 0.2 if present
- `company`: 0.2 if present
- `location`: 0.2 if present
- `email`: 0.2 if present
- `hireable`: 0.2 if present
- `blog`: 1 if present
- `bio`: 1 if present
- `created_at`: 5 max, otherwise years since created minus 2. (2-year old repo = 0, 3-year old repo = 1, ...)
- `followers`: 4 if > 1000. 0 if 0. Log scale
- `public_repos`: 5 if > 100, 0 if 0. Log scale
- `recent_repos`: 8 max, otherwise recent_repos
- `stars`: 6 if > 1000. 0 if 0. Log scale
- `readme`: 3 * % of recent_repos
- `license`: 4 * % of recent_repos
- `tests`: 10 * % of recent_repos
- `tags`: 3 * % of recent_repos
- `semver`: 3 * % of recent_repos
- `releases`: 10 * % of recent_repos
- `ci`: 6 * % of recent_repos
- `pr`: 5 if > 10, 0 if 0. Log scale
- `pr / pr_merged`: 10 * ratio
- `issues`: 3 if > 10, 0 if 0. Log scale
- `issues_closed / issues`: 4 * ratio
- `reviews`: 4 if > 10, 0 if 0. Log scale
- `review_repos`: 4 if > 10, 0 if 0. Log scale
