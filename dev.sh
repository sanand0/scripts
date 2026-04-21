#!/bin/bash

# Usage examples (agent-heavy workflows)
#
# Build/update the dev image:
#   dev.sh --build
#   dev.sh --build --no-cache
#
# Open an interactive shell in the container (default entrypoint is bash):
#   dev.sh
#
# Run a coding agent CLI inside the container:
#   dev.sh -- codex
#   dev.sh -- copilot
#
# Pass docker-run flags BEFORE `--`, and command args AFTER `--`:
#   dev.sh -v ~/dir:/home/vscode/dir:ro -- codex
#   dev.sh -e OPENAI_API_KEY=... -- codex --help
#
# Run tools/scripts in your current repo path (mounted as the same $PWD):
#   dev.sh -- uv run pytest
#   dev.sh -- bash -lc 'cd /home/vscode/code/scripts && rg "TODO|FIXME"'

set -euo pipefail

IMAGE_TAG="dev:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/dev.dockerfile"
# Optional host-only secret source. The script must still run cleanly when this
# file does not exist, because not every machine has the Dropbox layout.
ENV_FILE="${HOME}/Dropbox/scripts/.env"

# GITHUB_TOKEN=(secret GITHUB_TOKEN) dev.sh --build rebuilds and exits. Extra args are passed to `docker build`.
# GITHUB_TOKEN=(secret GITHUB_TOKEN) dev.sh --build --no-cache re-builds without cache.
if [[ ${1-} == "--build" ]]; then
    shift || true
    DOCKER_BUILDKIT=1 docker build \
        --file "$DOCKERFILE" \
        --tag "$IMAGE_TAG" \
        --secret id=github_token,env=GITHUB_TOKEN \
        "$@" \
        "$SCRIPT_DIR"
    exit 0
fi

# Create history file if missing
touch $HOME/.cache/dev-sh.bash-history

# Split CLI args: before `--` -> docker run args, after `--` -> container command args
docker_run_args=()
container_cmd_args=()
target=docker

for arg in "$@"; do
  if [[ "$target" == docker && "$arg" == "--" ]]; then
    target=cmd
    continue
  fi

  if [[ "$target" == docker ]]; then
    docker_run_args+=("$arg")
  else
    container_cmd_args+=("$arg")
  fi
done

if [[ "$target" == docker ]]; then
  if [[ ${#docker_run_args[@]} -gt 0 && "${docker_run_args[0]}" == -* ]]; then
    container_cmd_args=()
  else
    container_cmd_args=("${docker_run_args[@]}")
    docker_run_args=()
  fi
fi

font_mount_args=()

add_mount_if_present() {
  local source_path="$1"
  local target_path="$2"
  local mode="${3:-ro}"
  if [[ -e "$source_path" ]]; then
    font_mount_args+=(-v "${source_path}:${target_path}:${mode}")
  fi
}

# Mount host fonts opportunistically. Rendering/debugging tasks and
# `dev.test.sh` both care about seeing the same fonts the host has, but the
# script should stay portable across machines with different font layouts.
add_mount_if_present /usr/share/fonts /usr/share/fonts ro
add_mount_if_present /usr/local/share/fonts /usr/local/share/fonts ro
add_mount_if_present "$HOME/.fonts" /home/vscode/.fonts ro
add_mount_if_present "$HOME/.local/share/fonts" /home/vscode/.local/share/fonts ro

docker_socket_group_args=()
# UID 1000 inside the container needs the host docker socket's GID for access.
# We also bind-mount a patched /etc/group (with a named entry for that GID) to
# suppress the cosmetic "groups: cannot find name for group ID NNN" warning.
# The patched file is cached by GID+image-digest so docker is invoked at most
# once per image build (or GID change); subsequent runs use the cached file.
if [[ -S /var/run/docker.sock ]]; then
  docker_socket_gid="$(stat -c '%g' /var/run/docker.sock)"
  if [[ "$docker_socket_gid" =~ ^[0-9]+$ ]]; then
    docker_socket_group_args=(--group-add "$docker_socket_gid")
    _image_digest="$(docker image inspect "$IMAGE_TAG" --format '{{.Id}}' 2>/dev/null | tr -dc '[:alnum:]' | head -c 12)"
    if [[ -n "$_image_digest" ]]; then
      _docker_etc_group="/tmp/dev-sh-etc-group-${docker_socket_gid}-${_image_digest}"
      if [[ ! -s "$_docker_etc_group" ]]; then
        docker run --rm "$IMAGE_TAG" cat /etc/group > "$_docker_etc_group" 2>/dev/null
        grep -qE "^[^:]*:[^:]*:${docker_socket_gid}:" "$_docker_etc_group" || \
          printf 'docker_host:x:%s:\n' "$docker_socket_gid" >> "$_docker_etc_group"
      fi
      [[ -s "$_docker_etc_group" ]] && docker_socket_group_args+=(--volume "$_docker_etc_group:/etc/group:ro")
    fi
  fi
fi

# Prefer an explicitly exported token, but allow a local secrets file for the
# author's machine. Avoid hard-failing when neither is present.
github_token_value="${GITHUB_TOKEN-}"
if [[ -z "$github_token_value" && -f "$ENV_FILE" ]]; then
  github_token_value="$(awk -F= -v k="GITHUB_PERSONAL_ACCESS_TOKEN" '$1==k{print substr($0,index($0,"=")+1);exit}' "$ENV_FILE")"
fi

args=(
  --rm                          # auto-remove container on exit
  -it                           # interactive TTY
  --gpus all                    # expose all GPUs
  --shm-size=8g                 # bigger /dev/shm for browsers, PyTorch
  --ulimit nofile=1048576:1048576  # high FD limits
  --network host                # host networking (Linux only)
  -u 1000:1000                  # run as host user 1000:1000
  --security-opt no-new-privileges:true     # prevent privilege escalation within the container
  -e HOME=/home/vscode
  -e USER=vscode
  -e LOGNAME=vscode
  -e TERM="${TERM:-xterm-256color}"         # terminal type for colors
  -e COLORTERM="${COLORTERM:-truecolor}"    # 24-bit color hint
  -e LANG="${LANG:-en_US.UTF-8}"            # UTF-8 locale
  # Timezone
  -v /etc/localtime:/etc/localtime:ro
  -v /etc/timezone:/etc/timezone:ro
  # Caches
  -v "$HOME/.cache/huggingface:/home/vscode/.cache/huggingface" \
  -v "$HOME/.cache/ms-playwright:/home/vscode/.cache/ms-playwright" \
  -v "$HOME/.cache/pip:/home/vscode/.cache/pip"
  -v "$HOME/.cache/uv:/home/vscode/.cache/uv"
  # Configs. Enable what's required.
  # 🔴 = sensitive credentials. (LLM API keys are OK - loss is a few dollars.)
  -v "$HOME/.claude:/home/vscode/.claude"
  -v "$HOME/.claude.json:/home/vscode/.claude.json"
  -v "$HOME/.codex:/home/vscode/.codex"
  -v "$HOME/.config/gcloud:/home/vscode/.config/gcloud:ro"   # 🔴
  -v "$HOME/.config/gh:/home/vscode/.config/gh"
  -v "$HOME/.config/gws/:/home/vscode/.config/gws"
  -v "$HOME/.config/io.datasette.llm:/home/vscode/.config/io.datasette.llm"
  -v "$HOME/.config/opencode:/home/vscode/.config/opencode"
  # -v "$HOME/.config/wrangler/:/home/vscode/wrangler"    # 🔴
  -v "$HOME/.copilot:/home/vscode/.copilot"
  -v "$HOME/.gemini:/home/vscode/.gemini"
  -v "$HOME/.gitconfig:/home/vscode/.gitconfig:ro"
  # The host `~/.local/bin` is useful for sharing personal CLIs, but it must
  # stay behind the image-owned PATH entries defined in `dev.dockerfile`.
  -v "$HOME/.local/bin:/home/vscode/.local/bin:ro"
  -v "$HOME/.local/share/claude:/home/vscode/.local/share/claude"
  # Deliberately do not mount host `~/.local/share/mise`: doing so replaces the
  # image-managed installs/shims and makes the container toolchain depend on the
  # host's mise state.
  -v "$HOME/.local/share/opencode:/home/vscode/.local/share/opencode"
  -v "$HOME/.local/share/uv:/home/vscode/.local/share/uv"
  -v "$HOME/.npm:/home/vscode/.npm"
  # -v "$HOME/.ssh:/home/vscode/.ssh:ro"  # 🔴
  -v "$HOME/code/scripts/agents:/home/vscode/code/scripts/agents:ro" # Agents code
  -v "$HOME/Dropbox/scripts/llm.keys.json:/home/vscode/Dropbox/scripts/llm.keys.json:ro"
  "${font_mount_args[@]}"
  # X11 forwarding for GUI apps
  -e DISPLAY=$DISPLAY
  # Allow Claude Code to generate large HTML files. https://code.claude.com/docs/en/settings
  -e CLAUDE_CODE_MAX_OUTPUT_TOKENS=64000
  -v /tmp/.X11-unix:/tmp/.X11-unix
  -v /dev/dri:/dev/dri    # GPU (Intel/AMD)
  -v /dev/snd:/dev/snd    # Sound device
  --group-add audio
  "${docker_socket_group_args[@]}"
  --device /dev/dri
  # System mounts
  -v /var/run/docker.sock:/var/run/docker.sock  # docker-in-docker

  # SSH: enable when required
  # -e SSH_AUTH_SOCK=/ssh-agent                   # 🔴 Forward ssh-agent
  # --mount type=bind,source="$SSH_AUTH_SOCK",target=/ssh-agent

  -e HISTFILE=/home/vscode/.bash_history
  -e UV_LINK_MODE=copy
  # Keep this aligned with `dev.dockerfile`; `dev.test.sh` treats the exact
  # value as part of the runtime contract.
  -e PLAYWRIGHT_BROWSERS_PATH=/home/vscode/.local/share/playwright-browsers
  --mount type=bind,source="$HOME/.cache/dev-sh.bash-history",target=/home/vscode/.bash_history
  -v "$PWD:$PWD"                                # mount CWD at same path
  -w "$PWD"                                     # start in CWD
  # Add AI API keys if defined
  -e AIPIPE_TOKEN="${AIPIPE_TOKEN-}"
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY-}"
  -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY-}"
  -e GEMINI_API_KEY="${GEMINI_API_KEY-}"
  -e GITHUB_TOKEN="${github_token_value}"
  -e OPENAI_API_KEY="${OPENAI_API_KEY-}"
  -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY-}"
)

if [[ ${#container_cmd_args[@]} -eq 0 ]]; then
  args+=(--entrypoint /bin/bash)                # launch bash
fi

# exec: hand over to docker and end script
exec docker run "${args[@]}" "${docker_run_args[@]}" "$IMAGE_TAG" "${container_cmd_args[@]}"

# docker --rm -it hello-world: fails (docker binary unavailable).
