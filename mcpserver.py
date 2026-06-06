#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.14"
# dependencies = ["fastmcp"]
# ///

# Usage: uv run mcpserver.py
#   Exposes an MCP server on localhost:2428 that lets LLMs run bash commands.
#   curl localhost:2428/mcp to test
# npx -y ngrok@latest http --host-header=rewrite 2428
#   Exposes the server to the internet via ngrok. (Use with caution!)

import subprocess
import os
from datetime import datetime
from pathlib import Path
from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import get_context

# Initialize the server
mcp = FastMCP("Remote shell commands")


def markdown_code_block(text: str) -> str:
    """Return text in a fence that cannot be closed by the content."""
    ticks = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            ticks = max(ticks, current)
        else:
            current = 0
    fence = "`" * max(3, ticks + 1)
    return f"{fence}\n{text}\n{fence}"


def log_bash_command(commands: str, output: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S.%f")
    log_dir = Path.home() / ".local/share/sanand-scripts/mcpserver"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / f"{timestamp}.md").write_text(
        f"# mcpserver bash log {timestamp}\n\n"
        f"## Command\n\n{markdown_code_block(commands)}\n\n"
        f"## Output\n\n{markdown_code_block(output)}\n",
    )


def load_env_token(name: str) -> str:
    env_path = Path(__file__).with_name(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == name:
                return value.strip().strip("'\"")
    return os.environ.get(name, "")


def matching_cloudflared_running(token: str) -> bool:
    for cmdline_path in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            parts = cmdline_path.read_bytes().split(b"\0")
        except OSError:
            continue
        if not parts or Path(parts[0].decode(errors="ignore")).name != "cloudflared":
            continue
        if token in " ".join(part.decode(errors="ignore") for part in parts):
            return True
    return False


def start_cloudflare_tunnel() -> subprocess.Popen[str] | None:
    token = load_env_token("CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN")
    if not token:
        raise RuntimeError("CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN not found in .env")
    if matching_cloudflared_running(token):
        return None
    log_dir = Path.home() / ".local/share/sanand-scripts/mcpserver-cloudflared"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{datetime.now():%Y-%m-%d-%H-%M-%S}.jsonl"
    return subprocess.Popen(
        ["cloudflared", "tunnel", "--logfile", str(log_path), "run", "--token", token],
        text=True,
    )


def stop_cloudflare_tunnel(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@mcp.tool()
async def bash(commands: str, timeout_ms: int = 30_000) -> str:
    """Runs multiline bash script.
Useful CLI tools: curl, fd, ug, rga, jaq, sd, sg, git, gh, uv, agent-browser, duckdb, sqlite3, ...
Under `~` = `/home/sanand/` you have:

- ~/Dropbox/notes/transcripts/ - call transcripts
- ~/Documents/data/
  - s.anand@gramener.com/ and root.node@gmail.com/ - email, chat, calendar exports
  - whatsapp/ - whatsapp exports
  - browsing-history.db (SELECT url, timestamp, visit_count, ... FROM activity)
  - linkedin-invites.json
- ~/code/talks/README.md - talk transcripts, slides
- ~/code/datastories/config.json - data stories
- ~/code/llmdemos/config.json - innovation team demos
- ~/code/llmevals/README.md - LLM evals
- ~/code/blog/description.md - 20K files, 5K posts. Search for "- llm" for AI-related posts.
- ~/code/til/README.md - things I learnt
- ~/code/scripts/agents/*/SKILL.md - agent skills
- ~/code/README.md - code repos
- ~/r2/files/podcast - podcasts written for myself
- ~/Documents/activities/ - daily activity logs
- /tmp/ - to write temp files

gws can access email, calendar, chat:
    gws gmail users messages list --params '{"userId":"me", "q": "from:..."}'
    gws calendar events list --params '{"calendarId":"s.anand@straive.com","timeMin":"...","timeMax":"...","singleEvents":true,"orderBy":"startTime"}
"""
    ctx: Context = get_context()
    await ctx.info(f"bash: {commands}")
    try:
        result = subprocess.run(
            commands,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=timeout_ms / 1000,
        )
    except Exception as e:
        output = str(e)
        log_bash_command(commands, output)
        return output
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
        await ctx.warning(f"ERROR: {result.stderr}")
    if result.returncode != 0:
        output += f"\nReturn code: {result.returncode}"
    await ctx.info(f"DONE: {len(output)} chars, return code {result.returncode}")
    log_bash_command(commands, output)
    return output


if __name__ == "__main__":
    tunnel = start_cloudflare_tunnel()
    try:
        mcp.run(transport="http", port=2428)
    finally:
        stop_cloudflare_tunnel(tunnel)
