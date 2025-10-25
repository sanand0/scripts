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

echo "Use codex --dangerously-bypass-approvals-and-sandbox"

docker run --rm -i -t \
    --gpus all \
    -u 1000:1000 \
    -e HOME=/home/vscode \
    -v "$HOME/.cache/pip:/home/vscode/.cache/pip" \
    -v "$HOME/.cache/uv:/home/vscode/.cache/uv" \
    -v "$HOME/.codex:/home/vscode/.codex" \
    -v "$HOME/.config/gh:/home/vscode/.config/gh" \
    -v "$HOME/.config/mise:/home/vscode/.config/mise" \
    -v "$HOME/.gitconfig:/home/vscode/.gitconfig:ro" \
    -v "$HOME/.local/share/dev-sh-bash-history:/home/vscode/.bash_history" \
    -v "$HOME/.local/share/mise:/home/vscode/.local/share/mise" \
    -v "$HOME/.local/share/uv:/home/vscode/.local/share/uv" \
    -v "$HOME/.npm:/home/vscode/.npm" \
    -v "$HOME/.ssh:/home/vscode/.ssh:ro" \
    -v "$HOME/code/scripts/agents:/home/sanand/code/scripts/agents" \
    -v /etc/localtime:/etc/localtime:ro \
    -v /etc/timezone:/etc/timezone:ro \
    -v "$PWD:$PWD" \
    -w "$PWD" \
    --network=host \
    --entrypoint /bin/bash \
    "$IMAGE_TAG" \
    "$@"
