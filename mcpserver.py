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
from fastmcp import FastMCP, Context
from fastmcp.server.dependencies import get_context

# Initialize the server
mcp = FastMCP("Remote shell commands")


@mcp.tool()
async def bash(commands: str, timeout_ms: int = 30_000) -> str:
    """Runs multiline bash script. Use fd, ug, rga, sd, sg, jaq, gdu, uv, node, ffmpeg, git, ..."""
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
        return str(e)
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
        await ctx.warning(f"ERROR: {result.stderr}")
    if result.returncode != 0:
        output += f"\nReturn code: {result.returncode}"
    await ctx.info(f"DONE: {len(output)} chars, return code {result.returncode}")
    return output


if __name__ == "__main__":
    mcp.run(transport="http", port=2428)
