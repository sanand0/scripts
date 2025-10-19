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

docker run --rm -i -t \
    -u 1000:1000 \
    -e HOME=/home/vscode \
    -v "$HOME/.codex:/home/vscode/.codex" \
    -v "$HOME/code/scripts/agents:/home/sanand/code/scripts/agents" \
    -v "$HOME/.config/gh:/home/vscode/.config/gh" \
    -v "$HOME/.cache/pip:/home/vscode/.cache/pip" \
    -v "$HOME/.cache/uv:/home/vscode/.cache/uv" \
    -v "$HOME/.npm:/home/vscode/.npm" \
    -v "$HOME/.local/share/uv:/home/vscode/.local/share/uv" \
    -v "$PWD:$PWD" \
    -w "$PWD" \
    --entrypoint /bin/bash \
    "$IMAGE_TAG" \
    "$@"
