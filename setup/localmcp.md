# LocalMCP2: ChatGPT to local MCP through an OpenAI tunnel

LocalMCP2 lets ChatGPT call `mcpserver.py` on this laptop without exposing the
server directly to the internet. OpenAI's
[Secure MCP Tunnel](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels)
uses an outbound HTTPS connection from `tunnel-client`; requests are forwarded
to the private MCP endpoint on localhost. The ChatGPT-side steps follow
[Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt).

```text
ChatGPT plugin LocalMCP2
  -> OpenAI tunnel tunnel_6ab0b44c148c8191ab70479ddbf9baca
  -> tunnel-client on this laptop
  -> http://127.0.0.1:2428/mcp2428
  -> mcpserver.py in the dev.sh container
```

This is a private, developer-mode connection. Secure MCP Tunnel does not make
the plugin eligible for public distribution; public plugins need a stable,
publicly reachable HTTPS MCP endpoint.

## Daily use

Run the wrapper from the directory that `dev.sh` should mount as the current
working directory:

```bash
mcpserver -p ~/code/talks,~/Downloads,~/code:ro,~/r2:ro
```

Pass the same options that would normally appear before `--` in a `dev.sh`
command. Do **not** add `-- mcpserver.py`; the wrapper adds it. For example:

```bash
mcpserver
mcpserver -p ~/Downloads,~/Documents/data:ro
mcpserver -p ~/code/scripts,~/code/talks,~/Downloads,~/code:ro,~/r2:ro
```

The [mcpserver wrapper](../mcpserver):

1. Checks whether the managed `localmcp2` tunnel runtime is already running.
2. If needed, reads `OPENAI_API_KEY_LOCALMCP2` from `~/code/scripts/.env` and
   starts the runtime.
3. Executes `dev.sh <options> -- mcpserver.py` in the foreground.

Ctrl-C stops the foreground MCP server container. The managed tunnel runtime
stays up and is reused on the next invocation. After a reboot, running
`mcpserver` starts both pieces again.

## One-time setup

### 1. Check access and networking

The OpenAI requirements are:

- Tunnels **Read + Manage** permission to create or edit the Platform tunnel.
- Tunnels **Read + Use** permission to run it and select it in ChatGPT.
- ChatGPT developer-mode access. On managed Enterprise/Edu workspaces, an
  administrator may need to grant it before it can be enabled under
  **Settings -> Security and login**.
- Outbound HTTPS access to `api.openai.com:443` from the laptop.
- Local access from `tunnel-client` to `127.0.0.1:2428`.

The host also needs Docker, the `dev:latest` image built by `dev.sh --build`,
and `jaq`. `setup.fish` adds this repository to `PATH`; users of another shell
must add `~/code/scripts` themselves or invoke `~/code/scripts/mcpserver`.
`tunnel-client` is installed in step 4.

Platform organization permissions and ChatGPT workspace developer-mode access
are separate. The tunnel must also be associated with both the owning Platform
organization and the ChatGPT workspace that should list it.

### 2. Serve MCP on a distinct local path

`mcpserver.py` defines `MCP_PATH = "/mcp2428"` and starts FastMCP on port 2428,
so the local URL is:

```text
http://127.0.0.1:2428/mcp2428
```

The path was changed from `/mcp` to `/mcp2428` to avoid stale routing or cached
endpoint state while diagnosing the previous public connection. A focused test
asserts that FastMCP advertises exactly this route:

```bash
just test-mcpserver
```

`mcpserver.py` no longer starts the older Cloudflare tunnel. The
`CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN` setting and public
`https://mcp.s-anand.net/mcp` route are not part of LocalMCP2 startup.

### 3. Create the OpenAI tunnel

Open [Platform tunnel settings](https://platform.openai.com/settings/organization/tunnels)
in the intended Platform organization and create a tunnel with:

- Name: `LocalMCP2`
- Description: `Anand's machine via OpenAI Secure MCP Tunnel`
- Platform organization: the personal organization used here
- ChatGPT workspace: the personal ChatGPT workspace used here

The resulting tunnel ID is:

```text
tunnel_6ab0b44c148c8191ab70479ddbf9baca
```

The tunnel ID identifies the endpoint but is not the runtime secret. If the
tunnel does not appear later in ChatGPT, first check its workspace association
and the operator's Tunnels Read + Use permission.

### 4. Install `tunnel-client`

Use the download offered in Platform tunnel settings or the latest public
[openai/tunnel-client release](https://github.com/openai/tunnel-client/releases/latest).
Verify the archive against the checksum published with that release. Use the
latest-release page for future installations rather than hard-coding the old
download URL.

The installation performed on 21 September 2026 was:

- Version: `0.0.14`
- Linux archive SHA-256:
  `15bd17e805cad39d412199115bb9e10a978dd35258a114cdf25dd2ae6681c7d3`
- Binary: `~/.local/share/tunnel-client/v0.0.14/tunnel-client`
- Bundled Cloudflare binary:
  `~/.local/share/tunnel-client/v0.0.14/cloudflared`
- Command symlink: `~/.local/bin/tunnel-client`

Verify the current binary with:

```bash
tunnel-client --version
```

The correct syntax is `--version`, not `tunnel-client version`.

### 5. Store the runtime key safely

Create a runtime API key for the tunnel. Store the actual value only in the
ignored local file `~/code/scripts/.env`:

```dotenv
OPENAI_API_KEY_LOCALMCP2=...
```

Protect the file and verify that Git ignores it:

```bash
chmod 600 ~/code/scripts/.env
cd ~/code/scripts
git check-ignore -v .env
```

Never put the literal key in `mcpserver`, the tunnel profile, shell history, or
documentation. The generated profile stores `env:OPENAI_API_KEY_LOCALMCP2`, not
the secret value. The older `CLOUDFLARE_TUNNEL_LOCALHOST_TOKEN` is no longer
required by `mcpserver.py`.

### 6. Attach the local server to the tunnel

The initial attachment was created with:

```bash
cd ~/code/scripts
set -a
source .env
set +a

tunnel-client runtimes connect \
  --alias localmcp2 \
  --tunnel-id tunnel_6ab0b44c148c8191ab70479ddbf9baca \
  --runtime-api-key env:OPENAI_API_KEY_LOCALMCP2 \
  --mcp-server-url http://127.0.0.1:2428/mcp2428 \
  --json
```

`runtimes connect` writes a reusable profile and starts a managed background
runtime. The wrapper runs the same command only when that runtime is missing or
stale.

Current local state lives at:

| Purpose | Path |
| --- | --- |
| Runtime profile | `~/.config/tunnel-client/localmcp2.yaml` |
| Runtime log | `~/.local/state/tunnel-client/logs/localmcp2.log` |
| Health URL pointer | `~/.local/state/tunnel-client/health/localmcp2.url` |
| MCP request and session logs | `~/.local/share/sanand-scripts/mcpserver/` |

The health listener uses an ephemeral loopback port, so read the URL pointer or
structured status instead of assuming a fixed port.

### 7. Create the ChatGPT plugin

Enable developer mode if necessary, then open
[ChatGPT Plugins](https://chatgpt.com/plugins?view=personal):

1. Select **Create app**.
2. Set the name to `LocalMCP2`.
3. Set the description to
   `Run bash commands on Anand's machine via Secure MCP Tunnel.`
4. Under **Connection**, choose **Tunnel**.
5. Select the `LocalMCP2` tunnel.
6. Select **No Auth**. The local MCP server does not implement user OAuth; the
   tunnel runtime separately authenticates to OpenAI with its runtime key.
7. Acknowledge the tool-risk warning and create the app.
8. Review the discovered `bash`, `download_file`, and `save_file` tools, then
   select **Connect**.

This is a development plugin with local-machine capabilities. Do not broaden
its workspace association or install it for people who should not have access.

### 8. Test end to end

Start the service:

```bash
mcpserver -p ~/code/talks,~/Downloads,~/code:ro,~/r2:ro
```

In a fresh ChatGPT conversation, run a harmless test such as:

```text
Use the LocalMCP2 plugin's bash tool to run exactly: printf LOCALMCP2_OK.
Return only the output.
```

The verified result during setup was `LOCALMCP2_OK`. This proves more than
schema discovery: ChatGPT sent a real `tools/call` through OpenAI, the tunnel
forwarded it to `/mcp2428`, and the local server returned the output.

## Mounts and permissions

`mcpserver.py` can run shell commands, upload files, and download files. ChatGPT
labels the Bash and upload tools as write/open-world/destructive actions. Treat
every writable mount as data the model may modify or delete.

`dev.sh -p` accepts a comma-separated list. A bare path is read-write; append
`:ro` for read-only access:

```bash
mcpserver -p ~/code/talks,~/Downloads,~/code:ro,~/r2:ro
```

Here, `~/code/talks` and `~/Downloads` are writable while the broader `~/code`
and `~/r2` trees are read-only. `dev.sh` also mounts the current working
directory read-write, so run the wrapper from a directory whose contents may be
changed. Prefer the narrowest writable mounts that support the task.

`dev.sh` is useful containment, but it is **not a hard security boundary**. Its
default configuration also mounts several host caches and configuration paths,
`~/Documents/data/agents` read-write, and `/var/run/docker.sock`. Access to the
Docker socket can be used to launch another container with additional host
mounts, bypassing the apparent `:ro` boundary. Review `dev.sh` whenever its
defaults change and grant LocalMCP2 only to a trusted ChatGPT workspace.

`~/code/scripts/.env` is inside this repository. It may be readable to the MCP
shell when the repository—or a broader path such as `~/code:ro`—is mounted.
Never ask the model to display it, and do not treat read-only mounts as secret
isolation. The tunnel runtime key limits transport access, but exposure still
requires revoking and replacing the key.

The tunnel adds no inbound firewall port. It needs outbound HTTPS and uses the
runtime key to poll OpenAI. The local health UI is loopback-only by default;
leave it that way unless remote operator access is intentional.

## Health checks and troubleshooting

Inspect the managed runtime:

```bash
tunnel-client runtimes status localmcp2 --json \
  | jaq '{ready, process_running, stale, target: .process.target_value}'
```

A working runtime reports `ready: true`, `process_running: true`,
`stale: false`, and the `/mcp2428` target.

Check its loopback health endpoints:

```bash
health_url="$(cat ~/.local/state/tunnel-client/health/localmcp2.url)"
curl -fsS "$health_url/healthz"
curl -fsS "$health_url/readyz"
```

Expected responses are `live` and `ready`. The same base URL has `/ui` and
`/metrics`. To inspect recent transport activity:

```bash
tail -n 100 ~/.local/state/tunnel-client/logs/localmcp2.log | jaq .
```

For a fuller diagnosis:

```bash
set -a; source ~/code/scripts/.env; set +a
tunnel-client doctor --profile localmcp2 --explain
```

Common issues:

- **Tunnel absent in ChatGPT:** check the ChatGPT workspace association and
  Tunnels Read + Use permission. Organization membership alone is insufficient.
- **Runtime is live but not ready:** confirm `mcpserver` is still running and
  that the target remains `http://127.0.0.1:2428/mcp2428`.
- **After a reboot:** run `mcpserver ...`; the wrapper recreates the managed
  runtime before launching the server.
- **Runtime metadata is stale:** run `tunnel-client runtimes stop localmcp2`,
  then run `mcpserver ...` again.
- **ChatGPT shows old tool schemas:** open LocalMCP2 in ChatGPT Plugins, select
  **Refresh**, then start a new conversation. Refresh after changing tools,
  schemas, annotations, authentication, or UI resources.
- **`server/discover` returns HTTP 400:** FastMCP does not implement this
  optional probe. ChatGPT successfully falls back to standard MCP `initialize`
  and `tools/list`; treat it as benign only if discovery and a real tool call
  still succeed.
- **OAuth discovery warning:** this server intentionally uses **No Auth** and
  does not publish OAuth metadata. The warning is expected while `/readyz`
  remains ready and tool calls succeed.
- **Repeated `tools/call` failures:** these are not benign. Check the MCP logs,
  tunnel log, current endpoint, and ChatGPT plugin metadata.
- **A bare GET to `/mcp2428` returns 406:** the request may simply lack MCP's
  required streamable-HTTP headers. Use MCP Inspector, tunnel readiness, or a
  real ChatGPT tool call rather than treating that GET as the protocol test.

To inspect the local endpoint independently, use
[MCP Inspector](https://modelcontextprotocol.io/docs/tools/inspector), as
recommended by OpenAI's plugin testing guide.

## Updating the server later

When changing the endpoint path, tool names, descriptions, schemas,
annotations, or authentication:

1. Update `mcpserver.py` and its focused tests together.
2. Run `just test-mcpserver`.
3. If the URL changed, update `MCP_URL` in `mcpserver` and reconnect the runtime.
4. Restart the local MCP server.
5. Refresh LocalMCP2 in ChatGPT Plugins.
6. Start a new conversation and repeat the end-to-end tool-call test.

The tunnel ID can remain the same when only the local endpoint or tool metadata
changes.
