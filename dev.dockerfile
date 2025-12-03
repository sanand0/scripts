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
RUN mise use -g \
  deno \
  duckdb \
  fd \
  github-cli \
  jaq \
  node \
  pandoc \
  rclone \
  ripgrep \
  ubi:jqnatividad/qsv \
  ubi:mithrandie/csvq \
  ubi:pdfcpu/pdfcpu \
  uv \
  websocat

# Install uv
RUN bash -lc 'eval "$(mise env -s bash)"; \
  mkdir -p ~/apps/global; \
  cd ~/apps/global; \
  uv venv; \
  source .venv/bin/activate; \
  uv pip install csvkit dprint yt-dlp markitdown httpx pandas ruff llm typer rich orjson lxml tenacity pytest; \
  '

# Install npm tools last, so that we can update Codex and Claude
RUN bash -lc 'eval "$(mise env -s bash)"; \
  npm install -g wscat@latest; \
  npm install -g @openai/codex@0.63.0; \
  npm install -g @anthropic-ai/claude-code@latest; \
  npm install -g @github/copilot@latest; \
  '

# Default back to root for image setup; we'll run as UID 1000 at runtime
USER root
