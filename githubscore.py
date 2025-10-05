#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx", "tqdm"]
# ///

import json
import os
import re
from datetime import datetime, timedelta
from hashlib import sha256
from math import log10
from pathlib import Path

import httpx
from tqdm import tqdm


def api_cache(url, token, cache_dir, cache_days):
    """Cache GitHub API requests."""
    cache_key = sha256(url.encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"
    if cache_file.exists():
        age = datetime.now().timestamp() - cache_file.stat().st_mtime
        if age < cache_days * 86400:
            return json.loads(cache_file.read_text())
    tqdm.write(f"API: {url}")
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    response = httpx.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    cache_file.write_text(json.dumps(data))
    return data


def log_score(value, zero_val, max_val, max_score):
    """Calculate log-scale score."""
    if value == 0:
        return 0
    if value >= max_val:
        return max_score
    return max_score * log10(value) / log10(max_val)


def ratio_score(numerator, denominator, max_score):
    """Calculate ratio score, treating 0/0 as 0."""
    return max_score * (numerator / denominator) if denominator > 0 else 0


def test_paths(repo_data):
    """Check if repo has test files."""
    owner, name = repo_data["owner"]["login"], repo_data["name"]
    test_patterns = [
        r"test[s]?[_/]",
        r"[_/]test[s]?\.py$",
        r"[_/]test[s]?\.js$",
        r"spec[s]?[_/]",
        r"\.spec\.js$",
        r"\.test\.js$",
    ]
    api_url = f"https://api.github.com/repos/{owner}/{name}/git/trees/{repo_data['default_branch']}?recursive=1"
    try:
        tree = api_cache(api_url, os.environ["GITHUB_TOKEN"], cache_dir, cache_days)
        for item in tree.get("tree", []):
            path = item.get("path", "")
            if any(re.search(p, path) for p in test_patterns):
                return True
    except:
        pass
    return False


def get_user_data(login, since, max_repos, cache_dir, cache_days):
    """Fetch all metrics for a user."""
    token = os.environ["GITHUB_TOKEN"]
    base_url = "https://api.github.com"

    # User details
    user_url = f"{base_url}/users/{login}"
    user = api_cache(user_url, token, cache_dir, cache_days)

    data = {
        "login": login,
        "name": user.get("name"),
        "company": user.get("company"),
        "location": user.get("location"),
        "email": user.get("email"),
        "hireable": user.get("hireable"),
        "blog": user.get("blog"),
        "bio": user.get("bio"),
        "created_at": user.get("created_at"),
        "followers": user.get("followers", 0),
        "public_repos": user.get("public_repos", 0),
    }

    # Recent repos
    repos_url = f"{base_url}/users/{login}/repos?type=owner&sort=pushed&direction=desc&per_page={max_repos}"
    all_repos = api_cache(repos_url, token, cache_dir, cache_days)
    since_dt = datetime.fromisoformat(f"{since}T00:00:00Z".replace("Z", "+00:00"))
    recent_repos = [
        r
        for r in all_repos
        if not r["fork"]
        and not r.get("archived", False)
        and not r.get("is_template", False)
        and datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")) >= since_dt
    ]

    data["recent_repos"] = len(recent_repos)
    data["stars"] = sum(r["stargazers_count"] for r in recent_repos)

    # Count repos with README, LICENSE, tests, tags, semver, releases, CI
    readme_count = 0
    license_count = 0
    tests_count = 0
    tags_count = 0
    semver_count = 0
    releases_count = 0
    ci_count = 0

    for repo in recent_repos:
        owner, name = repo["owner"]["login"], repo["name"]

        # README
        readme_url = f"{base_url}/repos/{owner}/{name}/readme"
        try:
            api_cache(readme_url, token, cache_dir, cache_days)
            readme_count += 1
        except:
            pass

        # LICENSE
        license_url = f"{base_url}/repos/{owner}/{name}/license"
        try:
            api_cache(license_url, token, cache_dir, cache_days)
            license_count += 1
        except:
            pass

        # Tests
        if test_paths(repo):
            tests_count += 1

        # Tags
        tags_url = f"{base_url}/repos/{owner}/{name}/tags?per_page=1"
        try:
            tags = api_cache(tags_url, token, cache_dir, cache_days)
            if tags:
                tags_count += 1
                # Check for semver
                if re.match(r"^v?\d+\.\d+\.\d+", tags[0]["name"]):
                    semver_count += 1
        except:
            pass

        # Releases
        releases_url = f"{base_url}/repos/{owner}/{name}/releases?per_page=1"
        try:
            releases = api_cache(releases_url, token, cache_dir, cache_days)
            if releases:
                releases_count += 1
        except:
            pass

        # CI
        workflows_url = f"{base_url}/repos/{owner}/{name}/actions/workflows"
        try:
            workflows = api_cache(workflows_url, token, cache_dir, cache_days)
            if workflows.get("total_count", 0) > 0:
                ci_count += 1
                continue
        except:
            pass

        # Check commit status
        default_branch = repo.get("default_branch", "main")
        commits_url = f"{base_url}/repos/{owner}/{name}/commits/{default_branch}"
        try:
            commit = api_cache(commits_url, token, cache_dir, cache_days)
            sha = commit["sha"]
            status_url = f"{base_url}/repos/{owner}/{name}/commits/{sha}/status"
            status = api_cache(status_url, token, cache_dir, cache_days)
            if status.get("statuses") or status.get("check_runs"):
                ci_count += 1
        except:
            pass

    data["readme"] = readme_count
    data["license"] = license_count
    data["tests"] = tests_count
    data["tags"] = tags_count
    data["semver"] = semver_count
    data["releases"] = releases_count
    data["ci"] = ci_count

    # PRs in others' repos
    pr_url = f"{base_url}/search/issues?q=is:pr+author:{login}+-user:{login}+created:>={since}&per_page=100"
    pr_data = api_cache(pr_url, token, cache_dir, cache_days)
    data["pr"] = pr_data.get("total_count", 0)

    # Merged PRs
    pr_merged_url = f"{base_url}/search/issues?q=is:pr+is:merged+author:{login}+-user:{login}+merged:>={since}&per_page=100"
    pr_merged_data = api_cache(pr_merged_url, token, cache_dir, cache_days)
    data["pr_merged"] = pr_merged_data.get("total_count", 0)

    # Issues
    issues_url = f"{base_url}/search/issues?q=author:{login}+type:issue+created:>={since}&per_page=100"
    issues_data = api_cache(issues_url, token, cache_dir, cache_days)
    data["issues"] = issues_data.get("total_count", 0)

    # Closed issues
    issues_closed_url = f"{base_url}/search/issues?q=author:{login}+type:issue+is:closed+created:>={since}&per_page=100"
    issues_closed_data = api_cache(issues_closed_url, token, cache_dir, cache_days)
    data["issues_closed"] = issues_closed_data.get("total_count", 0)

    # Reviews
    reviews_url = f"{base_url}/search/issues?q=is:pr+reviewed-by:{login}+updated:>={since}&per_page=100"
    reviews_data = api_cache(reviews_url, token, cache_dir, cache_days)
    data["reviews"] = reviews_data.get("total_count", 0)

    # Review repos
    review_repos = set()
    for item in reviews_data.get("items", []):
        repo_url = item.get("repository_url", "")
        if repo_url:
            review_repos.add(repo_url.replace(f"{base_url}/repos/", ""))
    data["review_repos"] = len(review_repos)

    return data


def calculate_score(data):
    """Calculate overall score."""
    score = 0
    score += 0.2 if data["name"] else 0
    score += 0.2 if data["company"] else 0
    score += 0.2 if data["location"] else 0
    score += 0.2 if data["email"] else 0
    score += 0.2 if data["hireable"] else 0
    score += 1 if data["blog"] else 0
    score += 1 if data["bio"] else 0

    # Account age
    if data["created_at"]:
        created = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        years = (datetime.now(created.tzinfo) - created).days / 365.25
        score += min(5, max(0, years - 2))

    score += log_score(data["followers"], 0, 1000, 4)
    score += log_score(data["public_repos"], 0, 100, 5)
    score += min(8, data["recent_repos"])
    score += log_score(data["stars"], 0, 1000, 6)

    if data["recent_repos"] > 0:
        score += 3 * (data["readme"] / data["recent_repos"])
        score += 4 * (data["license"] / data["recent_repos"])
        score += 10 * (data["tests"] / data["recent_repos"])
        score += 3 * (data["tags"] / data["recent_repos"])
        score += 3 * (data["semver"] / data["recent_repos"])
        score += 10 * (data["releases"] / data["recent_repos"])
        score += 6 * (data["ci"] / data["recent_repos"])

    score += log_score(data["pr"], 0, 10, 5)
    score += ratio_score(data["pr_merged"], data["pr"], 10)
    score += log_score(data["issues"], 0, 10, 3)
    score += ratio_score(data["issues_closed"], data["issues"], 4)
    score += log_score(data["reviews"], 0, 10, 4)
    score += log_score(data["review_repos"], 0, 10, 4)

    return round(score)


def format_yaml(data_list):
    """Format data as YAML."""
    lines = []
    for data in data_list:
        lines.append(f"- login: {data['login']}")
        for key, value in data.items():
            if key != "login":
                if value is None:
                    lines.append(f"  {key}: null")
                elif isinstance(value, bool):
                    lines.append(f"  {key}: {str(value).lower()}")
                elif isinstance(value, str):
                    lines.append(f"  {key}: {value}")
                else:
                    lines.append(f"  {key}: {value}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys

    # Parse arguments
    args = sys.argv[1:]
    since = None
    max_repos = 20
    cache_days = 7
    logins = []

    i = 0
    while i < len(args):
        if args[i] == "--since":
            since = args[i + 1]
            i += 2
        elif args[i] == "--max-repos":
            max_repos = min(100, int(args[i + 1]))
            i += 2
        elif args[i] == "--cache-days":
            cache_days = int(args[i + 1])
            i += 2
        else:
            logins.append(args[i])
            i += 1

    if not since:
        since = (datetime.now() - timedelta(days=18 * 30)).strftime("%Y-%m-%d")

    cache_dir = Path.home() / ".cache" / "sanand-scripts" / "githubscore"
    cache_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for login in tqdm(logins, desc="Users", position=0):
        data = get_user_data(login, since, max_repos, cache_dir, cache_days)
        data["score"] = calculate_score(data)
        results.append(data)

    print(format_yaml(results))
