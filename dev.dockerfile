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
# Install mise and your toolchain for the vscode user
RUN curl -fsSL https://mise.run | sh && \
    echo 'eval "$(mise activate bash)"' >> "${HOME}/.bashrc" && \
    bash -lc 'mise use -g fd uv node ripgrep duckdb codex pandoc rclone ubi:mithrandie/csvq github-cli'

# Default back to root for image setup; we'll run as UID 1000 at runtime
USER root
