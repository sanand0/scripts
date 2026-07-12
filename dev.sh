#!/bin/bash

# Usage examples (agent-heavy workflows)
#
# Build/update the dev image:
#   GITHUB_TOKEN=(secret GITHUB_TOKEN) dev.sh --build
#   GITHUB_TOKEN=(secret GITHUB_TOKEN) dev.sh --build --no-cache
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
#   dev.sh -p ~/dir,~/data:ro,/tmp -- codex
#   dev.sh -e OPENAI_API_KEY=... -- codex --help
#
# Run tools/scripts in your current repo path (mounted as the same $PWD):
#   dev.sh -- uv run pytest
#   dev.sh -- bash -lc 'cd /home/vscode/code/scripts && rg "TODO|FIXME"'

set -euo pipefail

IMAGE_TAG="dev:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/dev.dockerfile"

# Keep the Chrome/Chromium sandbox enabled while retaining
# no-new-privileges. Playwright's profile is Docker's default seccomp policy
# with user-namespace operations enabled.
PLAYWRIGHT_VERSION="$(
  awk -F= '$1 == "ARG PLAYWRIGHT_VERSION" { print $2; exit }' "$DOCKERFILE"
)"
if [[ -z "$PLAYWRIGHT_VERSION" ]]; then
  printf 'ERROR: ARG PLAYWRIGHT_VERSION is missing from %s\n' "$DOCKERFILE" >&2
  exit 2
fi

PLAYWRIGHT_SECCOMP_PROFILE="${XDG_CACHE_HOME:-$HOME/.cache}/dev-sh/playwright-seccomp-${PLAYWRIGHT_VERSION}.json"
PLAYWRIGHT_SECCOMP_URL="https://raw.githubusercontent.com/microsoft/playwright/v${PLAYWRIGHT_VERSION}/utils/docker/seccomp_profile.json"

download_file() {
  local url="$1"
  local destination="$2"

  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$url" -o "$destination"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$destination" "$url"
  else
    printf 'ERROR: curl or wget is required to download %s\n' "$url" >&2
    return 1
  fi
}

ensure_playwright_seccomp_profile() {
  local profile_dir
  local temporary_profile

  if [[ -s "$PLAYWRIGHT_SECCOMP_PROFILE" ]]; then
    return 0
  fi

  profile_dir="$(dirname "$PLAYWRIGHT_SECCOMP_PROFILE")"
  temporary_profile="${PLAYWRIGHT_SECCOMP_PROFILE}.tmp.$$"
  mkdir -p "$profile_dir"

  if ! download_file "$PLAYWRIGHT_SECCOMP_URL" "$temporary_profile"; then
    rm -f "$temporary_profile"
    printf 'ERROR: unable to download Playwright seccomp profile %s\n' \
      "$PLAYWRIGHT_SECCOMP_URL" >&2
    return 1
  fi

  # Cheap validation without requiring jq/python on the host.
  if ! grep -q '"defaultAction"' "$temporary_profile" \
    || ! grep -q '"clone"' "$temporary_profile" \
    || ! grep -q '"unshare"' "$temporary_profile"; then
    rm -f "$temporary_profile"
    printf 'ERROR: downloaded Playwright seccomp profile looks invalid\n' >&2
    return 1
  fi

  chmod 0644 "$temporary_profile"
  mv -f "$temporary_profile" "$PLAYWRIGHT_SECCOMP_PROFILE"
}

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

ensure_playwright_seccomp_profile

# Create history file if missing
touch "$HOME/.cache/dev-sh.bash-history"

expand_path_mount() {
  local entry="$1"
  local path="${entry%%:*}"
  local mode="${entry#"$path"}"
  path="${path/#\~/$HOME}"
  [[ "$path" != "/" ]] && path="${path%/}"
  printf '%s:%s%s\n' "$path" "$path" "$mode"
}

# Split CLI args: before `--` -> docker run args, after `--` -> container command args
docker_run_args=()
container_cmd_args=()
target=docker
path_mounts=()

while [[ $# -gt 0 ]]; do
  arg="$1"
  shift
  if [[ "$target" == docker && "$arg" == "--" ]]; then
    target=cmd
    continue
  fi

  if [[ "$target" == docker ]]; then
    if [[ "$arg" == "-p" ]]; then
      if [[ $# -eq 0 ]]; then
        printf 'ERROR: -p requires a comma-separated path list\n' >&2
        exit 2
      fi
      IFS=, read -ra path_mounts <<< "${1-}"
      shift
      for path_mount in "${path_mounts[@]}"; do
        docker_run_args+=(-v "$(expand_path_mount "$path_mount")")
      done
    else
      docker_run_args+=("$arg")
    fi
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

# Reuse the host GitHub CLI authentication inside the container.
# The host credential is normally stored in its keyring, not ~/.config/gh.
if [[ -z "${GH_TOKEN:-}" ]] && command -v gh >/dev/null 2>&1; then
  GH_TOKEN="$(gh auth token --hostname github.com 2>/dev/null || true)"
  export GH_TOKEN
fi

args=(
  --rm                          # auto-remove container on exit
  --init                        # reap browser/agent child processes
  -it                           # interactive TTY
  --gpus all                    # expose all GPUs
  --shm-size=8g                 # bigger /dev/shm for browsers, PyTorch
  --ulimit nofile=1048576:1048576  # high FD limits
  --network host                # host networking (Linux only)
  -u 1000:1000                  # run as host user 1000:1000
  --security-opt no-new-privileges:true
  --security-opt "seccomp=${PLAYWRIGHT_SECCOMP_PROFILE}"
  -e GH_TOKEN                   # Copy GH_TOKEN from host env if present
  -e HOME=/home/vscode
  -e USER=vscode
  -e LOGNAME=vscode
  -e TERM="${TERM:-xterm-256color}"         # terminal type for colors
  -e COLORTERM="${COLORTERM:-truecolor}"    # 24-bit color hint
  -e LANG="${LANG:-en_US.UTF-8}"            # UTF-8 locale
  -e PATH="/home/sanand/code/scripts:/home/vscode/apps/global/.venv/bin:/home/vscode/.cargo/bin:/home/vscode/.local/overrides:/home/vscode/.local/share/mise/shims:/home/vscode/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
  # Timezone
  -v /etc/localtime:/etc/localtime:ro
  -v /etc/timezone:/etc/timezone:ro
  # Caches
  -v "$HOME/.cache/huggingface:/home/vscode/.cache/huggingface"
  -v "$HOME/.cache/pip:/home/vscode/.cache/pip"
  -v "$HOME/.cache/uv:/home/vscode/.cache/uv"
  # Configs. Enable what's required.
  # 🔴 = sensitive credentials. (LLM API keys are OK - loss is a few dollars.)
  -v "$HOME/.claude:/home/vscode/.claude"
  -v "$HOME/.claude.json:/home/vscode/.claude.json"
  -v "$HOME/.codex:/home/vscode/.codex"
  # -v "$HOME/.config/gcloud:/home/vscode/.config/gcloud:ro"   # 🔴
  # We don't need .config/gh since we're passing GH_TOKEN
  # -v "$HOME/.config/gh:/home/vscode/.config/gh:ro"
  -v "$HOME/.config/gws/:/home/vscode/.config/gws"
  -v "$HOME/.config/gws-root.node@gmail.com/:/home/vscode/.config/gws-root.node@gmail.com"
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
  -v "$HOME/.local/share/rtk:/home/vscode/.local/share/rtk"
  -v "$HOME/.local/share/sanand-scripts:/home/vscode/.local/share/sanand-scripts"
  -v "$HOME/.npm:/home/vscode/.npm"
  -v "$HOME/.gemini:/home/vscode/.gemini"
  -v "$HOME/.pi:/home/vscode/.pi"
  # UV caches are shared above but the managed Python installations should be image-owned
  # -v "$HOME/.local/share/uv:/home/vscode/.local/share/uv"
  # -v "$HOME/.ssh:/home/vscode/.ssh:ro"  # 🔴
  -v "$HOME/code/scripts/agents:/home/vscode/code/scripts/agents:ro" # Agents code
  -v "$HOME/Dropbox/scripts/llm.keys.json:/home/vscode/Dropbox/scripts/llm.keys.json:ro"
  -v "$HOME/Documents/data/agents:/home/vscode/Documents/data/agents" # Agents data
  "${font_mount_args[@]}"
  # X11 forwarding for GUI apps
  -e DISPLAY="$DISPLAY"
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
  -e PWD="$PWD"                                 # keep logical /home/sanand/... path across the image symlink
  # Add AI API keys if defined
  -e AIPIPE_TOKEN="${AIPIPE_TOKEN-}"
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY-}"
  -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY-}"
  -e GEMINI_API_KEY="${GEMINI_API_KEY-}"
  -e GITHUB_TOKEN="${GITHUB_TOKEN-}"
  -e OPENAI_API_KEY="${OPENAI_API_KEY-}"
  -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY-}"
)

if [[ ${#container_cmd_args[@]} -eq 0 ]]; then
  args+=(--entrypoint /bin/bash)                # launch bash
fi

# exec: hand over to docker and end script
exec docker run "${args[@]}" "${docker_run_args[@]}" "$IMAGE_TAG" "${container_cmd_args[@]}"

# docker --rm -it hello-world: fails (docker binary unavailable).
