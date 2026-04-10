# Create a development container with commonly used tools
# Build can take ~15 min

FROM mcr.microsoft.com/devcontainers/base:ubuntu

ARG DEBIAN_FRONTEND=noninteractive

# Takes ~3 min
# `docker.io` is here for the client binary only. `dev.sh` bind-mounts the host
# Docker socket, so container-side Docker commands talk to the host daemon.
RUN apt-get update \
  && apt-get install -y \
    curl \
    ca-certificates \
    docker.io \
    fontconfig \
    imagemagick \
    ugrep \
    lynx \
    qpdf \
    w3m \
    sqlite3 \
    moreutils \
    ffmpeg \
    webp \
    postgresql-client \
    poppler-utils \
    ghostscript \
    librsvg2-bin \
    bubblewrap \
  && rm -rf /var/lib/apt/lists/*

# Make /home/sanand point to /home/vscode (symlink; hard links for dirs aren’t supported)
RUN ln -s /home/vscode /home/sanand

# Work as the non-root user for mise + tools so files are owned by UID 1000
USER vscode
ENV HOME=/home/vscode
ENV SHELL=/bin/bash
# `dev.sh` bind-mounts the host `~/.local/bin` read-only. Keep image-owned
# overrides and mise shims earlier on PATH so the container still prefers the
# image toolchain when the host mount is present.
ENV PATH="${HOME}/apps/global/.venv/bin:${HOME}/.cargo/bin:${HOME}/.local/overrides:${HOME}/.local/share/mise/shims:${HOME}/.local/bin:${PATH}"
# Keep Playwright browser payloads in an image-owned path rather than under the
# host-mounted cache, otherwise the image can look "installed" but launch with
# whatever happens to exist on the host.
ENV PLAYWRIGHT_BROWSERS_PATH="${HOME}/.local/share/playwright-browsers"

# Prefer distro ImageMagick over any user-level AppImage in `~/.local/bin`.
# The AppImage path has failed in practice inside the container because it
# depends on FUSE/fusermount availability.
RUN mkdir -p "${HOME}/.local/overrides" "${PLAYWRIGHT_BROWSERS_PATH}" \
 && ln -sf "$(command -v magick || command -v convert)" "${HOME}/.local/overrides/magick"

# Install mise and set up shell
# Keep a copy of `mise` outside `~/.local/bin`, because `dev.sh` intentionally
# overlays that directory with the host view at runtime.
RUN curl -fsSL https://mise.run | sh \
 && install -m 0755 "${HOME}/.local/bin/mise" "${HOME}/.local/overrides/mise" \
 && echo 'eval "$(mise activate bash)"' >> "${HOME}/.bashrc" \
 && echo 'export PATH="$HOME/apps/global/.venv/bin:$PATH"' >> "${HOME}/.bashrc"

# Install mise tools. Takes ~2.5 min
RUN --mount=type=secret,id=github_token bash -lc 'eval "$(mise env -s bash)"; \
  export GITHUB_TOKEN="$(sudo cat /run/secrets/github_token)"; \
  mise use -g \
  ast-grep \
  deno \
  duckdb \
  fd \
  gcloud \
  github-cli \
  hugo \
  jaq \
  node \
  pandoc \
  rclone \
  ripgrep \
  github:dandavison/delta \
  github:jqnatividad/qsv \
  github:mithrandie/csvq \
  github:pdfcpu/pdfcpu \
  uv \
  websocat \
  '

# Install uv. Takes ~0.5 min
RUN bash -lc 'eval "$(mise env -s bash)"; \
  mkdir -p ~/apps/global; \
  cd ~/apps/global; \
  uv venv; \
  source .venv/bin/activate; \
  uv pip install cairosvg csvkit dprint yt-dlp markitdown httpx pandas pillow ruff llm typer rich orjson lxml tenacity pytest google_genai; \
  llm install llm-cmd llm-openrouter llm-gemini llm-anthropic llm-openai-plugin llm-whisper-api llm-groq-whisper; \
  '

# Install cargo. Takes ~1 min
RUN bash -lc 'curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; \
  . "$HOME/.cargo/env"; \
  cargo install --locked resvg; \
  '

# Global npm executables under a mise-managed Node are not reliably visible
# until `mise reshim node` runs, so keep that coupled to any future CLI adds.
# Takes ~5 min
RUN bash -lc 'eval "$(mise env -s bash)"; \
  npm install -g npm@latest; \
  npm install -g wscat@latest; \
  npm install -g @googleworkspace/cli@latest; \
  npm install -g pixelmatch pngjs; \
  npm install -g playwright; \
  playwright install --with-deps chromium firefox webkit; \
  mise reshim node \
  '

# Install frequently changing agent CLIs last to keep them fresh
# Takes ~1.5 min
RUN bash -lc 'eval "$(mise env -s bash)"; \
  echo "03 Apr 2026: Updating agents"; \
  npm install -g @openai/codex@latest; \
  npm install -g @github/copilot@latest; \
  npm install -g @google/gemini-cli; \
  mise reshim node \
  '
# No need to install claude since ~/.local/share/claude is shared

# Default back to root for image setup; we'll run as UID 1000 at runtime
USER root

# Exporting to layers takes ~3 min
