# Create a development container with commonly used tools

FROM mcr.microsoft.com/devcontainers/base:ubuntu

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
  && apt-get install -y \
    curl \
    ca-certificates \
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
  && rm -rf /var/lib/apt/lists/* \
  && wget https://imagemagick.org/archive/binaries/magick -O /bin/magick \
  && chmod +x /bin/magick

# Make /home/sanand point to /home/vscode (symlink; hard links for dirs aren’t supported)
RUN ln -s /home/vscode /home/sanand

# Work as the non-root user for mise + tools so files are owned by UID 1000
USER vscode
ENV HOME=/home/vscode
ENV SHELL=/bin/bash
# mise puts itself in ~/.local/bin; ensure it's on PATH for both build and runtime
ENV PATH="${HOME}/.local/bin:${PATH}"

# Pending: rclone, magick, cwebp
# Install mise and set up shell
RUN curl -fsSL https://mise.run | sh \
 && echo 'eval "$(mise activate bash)"' >> "${HOME}/.bashrc" \
 && echo 'export PATH="$HOME/apps/global/.venv/bin:$PATH"' >> "${HOME}/.bashrc"

# Install mise tools
RUN --mount=type=secret,id=github_token \
  bash -lc 'export GITHUB_TOKEN="$(cat /run/secrets/github_token 2>/dev/null || true)"; \
  mise use -g \
  ast-grep \
  deno \
  duckdb \
  fd \
  github-cli \
  hugo \
  jaq \
  node \
  pandoc \
  rclone \
  ripgrep \
  ubi:dandavison/delta \
  ubi:jqnatividad/qsv \
  ubi:mithrandie/csvq \
  ubi:pdfcpu/pdfcpu \
  ubi:tealdeer-rs/tealdeer@1.8.1 \
  uv \
  websocat \
  '

# Install uv
RUN bash -lc 'eval "$(mise env -s bash)"; \
  mkdir -p ~/apps/global; \
  cd ~/apps/global; \
  uv venv; \
  source .venv/bin/activate; \
  uv pip install csvkit dprint yt-dlp markitdown httpx pandas ruff llm typer rich orjson lxml tenacity pytest; \
  '

# Install npm tools last, so that we can update Codex and Claude.
# Note: `codex` actually runs the host system codex.
RUN bash -lc 'eval "$(mise env -s bash)"; \
  npm install -g npm@latest; \
  npm install -g wscat@latest; \
  npm install -g @openai/codex@latest; \
  npm install -g @github/copilot@latest; \
  curl -fsSL https://claude.ai/install.sh | bash \
  '

# Default back to root for image setup; we'll run as UID 1000 at runtime
USER root
