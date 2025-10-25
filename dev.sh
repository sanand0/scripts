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

args=(
  --rm                          # auto-remove container on exit
  -it                           # interactive TTY
  --gpus all                    # expose all GPUs
  --shm-size=2g                 # bigger /dev/shm for browsers, PyTorch
  --ulimit nofile=1048576:1048576  # high FD limits
  --network host                # host networking (Linux only)
  -u 1000:1000                  # run as host user 1000:1000
  -e HOME=/home/vscode          # set HOME
  -e TERM="${TERM:-xterm-256color}"         # terminal type for colors
  -e COLORTERM="${COLORTERM:-truecolor}"    # 24-bit color hint
  -e LANG="${LANG:-en_US.UTF-8}"            # UTF-8 locale
  -e SSH_AUTH_SOCK=/ssh-agent               # Forward ssh-agent
  --mount type=bind,source="$SSH_AUTH_SOCK",target=/ssh-agent
  -e HISTFILE=/home/vscode/.bash_history
  --mount type=bind,source="$HOME/.cache/dev-sh.bash-history",target=/home/vscode/.bash_history
  -v "$HOME/.cache/huggingface:/home/vscode/.cache/huggingface" \
  -v "$HOME/.cache/ms-playwright:/home/vscode/.cache/ms-playwright" \
  -v "$HOME/.cache/pip:/home/vscode/.cache/pip" # pip cache
  -v "$HOME/.cache/uv:/home/vscode/.cache/uv"   # uv cache
  -v "$HOME/.claude:/home/vscode/.claude"       # Claude config
  -v "$HOME/.codex:/home/vscode/.codex"         # Codex config
  -v "$HOME/.copilot:/home/vscode/.copilot"     # Copilot config
  -v "$HOME/.config/gh:/home/vscode/.config/gh" # gh config
  -v "$HOME/.gitconfig:/home/vscode/.gitconfig" # git config
  -v "$HOME/.local/share/uv:/home/vscode/.local/share/uv" # uv data
  -v "$HOME/.npm:/home/vscode/.npm"             # npm cache
  -v "$HOME/.ssh:/home/vscode/.ssh:ro"          # ssh keys (RO)
  -v "$HOME/code/scripts/agents:/home/vscode/code/scripts/agents" # Agents code
  -v /var/run/docker.sock:/var/run/docker.sock  # docker-in-docker
  -v /etc/localtime:/etc/localtime:ro           # timezone rules
  -v /etc/timezone:/etc/timezone:ro             # timezone name
  -v "$PWD:$PWD"                                # mount CWD at same path
  -w "$PWD"                                     # start in CWD
  --entrypoint /bin/bash                        # launch bash
)

# exec: hands over to docker and end script
exec docker run "${args[@]}" "$IMAGE_TAG" "$@"
