#!/usr/bin/env -S uv run --script

# /// script
# requires-python = ">=3.14"
# dependencies = ["mcp"]
# ///

# Usage: uv run mcpserver.py
#   Exposes an MCP server on localhost:8000 that lets LLMs run bash commands.
#   curl localhost:8000/sse to test
# npx -y ngrok@latest http --host-header=rewrite 8000
#   Exposes the server to the internet via ngrok. (Use with caution!)

import subprocess
from mcp.server.fastmcp import FastMCP

# Initialize the server
mcp = FastMCP("Remote shell commands")


@mcp.tool()
def bash(command: str) -> str:
    """Runs command in bash in remote machine. Has uv, node, rg, jq, ffmpeg, git, ..."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        return str(e)
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
    if result.returncode != 0:
        output += f"\nReturn code: {result.returncode}"
    return output


if __name__ == "__main__":
    mcp.run(transport="sse")
