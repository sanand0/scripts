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


@mcp.tool()
async def bash(commands: str, timeout_ms: int = 30_000) -> str:
    """Runs multiline bash script. Use fd, ug, rga, sd, sg, jaq, gdu, uv, node, ffmpeg, git, ...
/tmp/ for temp files"""
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
    mcp.run(transport="http", port=2428)
