#!/bin/bash
set -euo pipefail

IMAGE_TAG="codex-cli:latest"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCKERFILE="${SCRIPT_DIR}/codex.dockerfile"
HOME_MOUNT="/codex-home"

if [[ ${1-} == "--build" ]]; then
    shift || true
    DOCKER_BUILDKIT=1 docker build \
        --file "$DOCKERFILE" \
        --tag "$IMAGE_TAG" \
        "$@" \
        "$SCRIPT_DIR"
    exit 0
fi

mapfile -t CACHE_DIRS <<'EOF'
.codex
.config/gh
.cache/pip
.cache/pnpm
.cache/uv
.local/share/uv
EOF

for rel in "${CACHE_DIRS[@]}"; do
    mkdir -p "$HOME/$rel"
done

docker_flags=(--rm)
if [[ -t 0 ]]; then
    docker_flags+=(-i)
fi
if [[ -t 1 ]]; then
    docker_flags+=(-t)
fi

codex_cmd=(codex)
if (( $# )); then
    codex_cmd+=( "$@" )
fi

cmd_str=""
for part in "${codex_cmd[@]}"; do
    cmd_str+="$(printf '%q' "$part") "
done
cmd_str="${cmd_str% }"

docker run "${docker_flags[@]}" \
    -e HOME="$HOME_MOUNT" \
    -v "$HOME/.codex:$HOME_MOUNT/.codex" \
    -v "$HOME/.config/gh:$HOME_MOUNT/.config/gh" \
    -v "$HOME/.cache/pip:$HOME_MOUNT/.cache/pip" \
    -v "$HOME/.cache/pnpm:$HOME_MOUNT/.cache/pnpm" \
    -v "$HOME/.cache/uv:$HOME_MOUNT/.cache/uv" \
    -v "$HOME/.local/share/uv:$HOME_MOUNT/.local/share/uv" \
    -v "$PWD:$PWD" \
    -w "$PWD" \
    --user "$(id -u)":"$(id -g)" \
    --entrypoint /bin/bash \
    "$IMAGE_TAG" \
    -c "$cmd_str"
