#!/bin/bash

set -euo pipefail

IMAGE_TAG="dev:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/dev.dockerfile"

# dev.sh --build rebuilds and exits. Extra args are passed to `docker build`.
# dev.sh --build --no-cache re-builds without cache.
if [[ ${1-} == "--build" ]]; then
    shift || true
    DOCKER_BUILDKIT=1 docker build \
        --file "$DOCKERFILE" \
        --tag "$IMAGE_TAG" \
        "$@" \
        "$SCRIPT_DIR"
    exit 0
fi

# Create history file if missing
touch $HOME/.cache/dev-sh.bash-history

args=(
  --rm                          # auto-remove container on exit
  -it                           # interactive TTY
  --gpus all                    # expose all GPUs
  --shm-size=8g                 # bigger /dev/shm for browsers, PyTorch
  --ulimit nofile=1048576:1048576  # high FD limits
  --network host                # host networking (Linux only)
  -u 1000:1000                  # run as host user 1000:1000
  -e HOME=/home/vscode
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
  # Configs
  -v "$HOME/.claude:/home/vscode/.claude"
  -v "$HOME/.claude.json:/home/vscode/.claude.json"
  -v "$HOME/.codex:/home/vscode/.codex"
  -v "$HOME/.config/gh:/home/vscode/.config/gh"
  -v "$HOME/.config/io.datasette.llm:/home/vscode/.config/io.datasette.llm"
  -v "$HOME/.config/opencode:/home/vscode/.config/opencode"
  -v "$HOME/.config/rclone:/home/vscode/.config/rclone"
  -v "$HOME/.config/wrangler/:/home/vscode/wrangler"
  -v "$HOME/.copilot:/home/vscode/.copilot"
  -v "$HOME/.gitconfig:/home/vscode/.gitconfig"
  -v "$HOME/.local/bin:/home/vscode/.local/bin:ro"
  -v "$HOME/.local/share/mise:/home/vscode/.local/share/mise"
  -v "$HOME/.local/share/opencode:/home/vscode/.local/share/opencode"
  -v "$HOME/.local/share/uv:/home/vscode/.local/share/uv"
  -v "$HOME/.npm:/home/vscode/.npm"
  -v "$HOME/.ssh:/home/vscode/.ssh:ro"
  -v "$HOME/code/scripts/agents:/home/vscode/code/scripts/agents" # Agents code
  -v "$HOME/Dropbox/scripts/llm.keys.json:/home/sanand/Dropbox/scripts/llm.keys.json"
  # X11 forwarding for GUI apps
  -e DISPLAY=$DISPLAY
  -v /tmp/.X11-unix:/tmp/.X11-unix
  -v /dev/dri:/dev/dri    # GPU (Intel/AMD)
  -v /dev/snd:/dev/snd    # Sound device
  --group-add audio
  --device /dev/dri
  # System mounts
  -v /var/run/docker.sock:/var/run/docker.sock  # docker-in-docker
  -e SSH_AUTH_SOCK=/ssh-agent                   # Forward ssh-agent
  --mount type=bind,source="$SSH_AUTH_SOCK",target=/ssh-agent
  -e GITHUB_TOKEN=$(awk -F= -v k="GITHUB_PERSONAL_ACCESS_TOKEN" '$1==k{print substr($0,index($0,"=")+1);exit}' $HOME/Dropbox/scripts/.env)
  -e HISTFILE=/home/vscode/.bash_history
  -e UV_LINK_MODE=copy
  --mount type=bind,source="$HOME/.cache/dev-sh.bash-history",target=/home/vscode/.bash_history
  -v "$PWD:$PWD"                                # mount CWD at same path
  -w "$PWD"                                     # start in CWD
  # Add AI API keys if defined
  -e AIPIPE_TOKEN="${AIPIPE_TOKEN-}"
  -e ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY-}"
  -e DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY-}"
  -e GEMINI_API_KEY="${GEMINI_API_KEY-}"
  -e GITHUB_TOKEN="${GITHUB_TOKEN-}"
  -e OPENAI_API_KEY="${OPENAI_API_KEY-}"
  -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY-}"
  --entrypoint /bin/bash                        # launch bash
)

# exec: hands over to docker and end script
exec docker run "${args[@]}" "$IMAGE_TAG" "$@"

# docker --rm -it hello-world: fails (docker binary unavailable).
