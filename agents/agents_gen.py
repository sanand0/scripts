#!/usr/bin/env python3
"""
Keep local skill directories and AGENTS.md in sync with remote sources.

Steps:
1. Load the list of remote skill folders and resolve their local target names.
2. Ensure `.gitignore` contains one entry per remote skill so Git ignores them.
3. For targets older than the provided TTL (24h by default), sparse-clone each
   repository (grouped by repo/branch) and copy the requested folders locally.
4. Walk every `SKILL.md`, extract name/description, and rebuild the Markdown
   index between `<!-- skills -->` markers in `AGENTS.md`.

Outcome: Remote skills stay refreshed without polluting commits, while the
documentation index always lists every available skill.
"""

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AGENTS = ROOT / "AGENTS.md"
GITIGNORE = ROOT / ".gitignore"
START, END = "<!-- skills -->", "<!-- /skills -->"

REMOTE_SKILLS = [
    # "https://github.com/anthropics/skills/tree/main/skill-creator",
    "https://github.com/anthropics/skills/tree/main/webapp-testing",
    "https://github.com/anthropics/skills/tree/main/document-skills/pdf",
    "https://github.com/anthropics/skills/tree/main/document-skills/pptx",
    "https://github.com/anthropics/skills/tree/main/document-skills/xlsx",
    # "https://github.com/ComposioHQ/awesome-claude-skills/tree/master/changelog-generator",
    # Superpowers are not independently reusable. They rely on other superpowers.
    # "https://github.com/obra/superpowers/tree/main/skills/brainstorming",
]


def run(cmd, cwd=None):
    subprocess.run(cmd, check=True, cwd=cwd)


def parse_url(url: str):
    tail = url.replace("https://github.com/", "", 1)
    repo, _, rest = tail.partition("/tree/")
    branch, _, path = rest.partition("/")
    return repo, branch, path


def remote_targets():
    targets = []
    for url in REMOTE_SKILLS:
        repo, branch, rel = parse_url(url)
        dest = ROOT / Path(rel).name
        targets.append((repo, branch, rel, dest))
    return targets


def needs_refresh(dest: Path, ttl: int, now: float) -> bool:
    return not dest.exists() or (now - dest.stat().st_mtime) > ttl


def fetch_remote_skills(targets, ttl: int):
    now = time.time()
    groups = {}
    for repo, branch, rel, dest in targets:
        if needs_refresh(dest, ttl, now):
            groups.setdefault((repo, branch), []).append((rel, dest))
    if not groups:
        return
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for (repo, branch), items in groups.items():
            repo_dir = tmp_path / repo.replace("/", "-")
            run(
                [
                    "git",
                    "clone",
                    "--depth=1",
                    "--filter=blob:none",
                    "--sparse",
                    f"https://github.com/{repo}.git",
                    str(repo_dir),
                ]
            )
            run(["git", "checkout", branch], cwd=repo_dir)
            run(["git", "sparse-checkout", "set", *(rel for rel, _ in items)], cwd=repo_dir)
            for rel, dest in items:
                src = repo_dir / rel
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(src, dest)


def parse_frontmatter(path: Path):
    text = path.read_text()
    match = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL)
    data = {
        k.strip(): v.strip()
        for k, v in (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    }
    return data["name"], data["description"]


def build_index(skills):
    lines = []
    for path in skills:
        name, desc = parse_frontmatter(path)
        rel = path.parent.relative_to(ROOT)
        lines.append(f"- [{name}]({rel}/SKILL.md): {desc}")
    header = f"Refer relevant SKILL.md under {ROOT}:\n\n"
    return f"{START}\n\n{header}" + "\n".join(lines) + f"\n\n{END}"


def update_agents(block):
    body = AGENTS.read_text()
    pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.DOTALL)
    updated = pattern.sub(block, body) if pattern.search(body) else f"{body.rstrip()}\n\n{block}\n"
    AGENTS.write_text(updated)


def main():
    targets = remote_targets()
    remotes = {dest for _, _, _, dest in targets}
    GITIGNORE.write_text("\n".join(f"{dest.name}/" for dest in remotes) + "\n")

    # Refresh remote skills at most once per day
    fetch_remote_skills(targets, ttl=24 * 60 * 60)

    # Get */SKILL.md sorted by local skills first, then remotes
    skills = sorted((p.parent in remotes, p) for p in ROOT.rglob("SKILL.md") if p.parent != ROOT)

    # Write into AGENTS.md
    update_agents(build_index([skill for _, skill in skills]))


if __name__ == "__main__":
    main()
