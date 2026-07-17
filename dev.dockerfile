# Create a development container with commonly used tools
# Build can take ~15 min

# 01 Jun 2026: Review after 01 July 2026 (monthly) to see if Playwright is released for ubuntu-26.04 and re-pin.
FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

ARG DEBIAN_FRONTEND=noninteractive
# Keep this aligned with the seccomp profile version resolved by dev.sh.
ARG PLAYWRIGHT_VERSION=1.61.0

# Takes ~3 min
# `docker.io` is here for the client binary only. `dev.sh` bind-mounts the host
# Docker socket, so container-side Docker commands talk to the host daemon.
#
# Install Google Chrome as a normal system package, independently of Playwright.
# Compatibility aliases maximize discovery by tools that probe Chromium names.
RUN set -eux; \
  apt-get update; \
  apt-get install -y --no-install-recommends \
    bubblewrap \
    ca-certificates \
    curl \
    docker.io \
    ffmpeg \
    fontconfig \
    ghostscript \
    imagemagick \
    librsvg2-bin \
    lynx \
    moreutils \
    poppler-utils \
    postgresql-client \
    qpdf \
    sqlite3 \
    ugrep \
    w3m \
    webp \
    xxd; \
  curl -fsSL \
    https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    -o /tmp/google-chrome.deb; \
  apt-get install -y --no-install-recommends /tmp/google-chrome.deb; \
  ln -sf /usr/bin/google-chrome-stable /usr/local/bin/chrome; \
  ln -sf /usr/bin/google-chrome-stable /usr/local/bin/google-chrome; \
  ln -sf /usr/bin/google-chrome-stable /usr/local/bin/chromium; \
  ln -sf /usr/bin/google-chrome-stable /usr/local/bin/chromium-browser; \
  command -v google-chrome-stable; \
  command -v google-chrome; \
  command -v chromium; \
  command -v chromium-browser; \
  rm -f /tmp/google-chrome.deb; \
  rm -rf /var/lib/apt/lists/*

# Hints used by browser launchers that do not reliably search PATH.
ENV CHROME_BIN=/usr/bin/google-chrome-stable \
    CHROME_PATH=/usr/bin/google-chrome-stable \
    GOOGLE_CHROME_BIN=/usr/bin/google-chrome-stable \
    CHROMIUM_BIN=/usr/bin/google-chrome-stable \
    CHROMIUM_PATH=/usr/bin/google-chrome-stable \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/google-chrome-stable

# dev.sh passes GID 992 (render/GPU device - ollama?). Avoid warning about missing group name.
RUN getent group 992 >/dev/null || groupadd --gid 992 render

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
 && ln -sf "$(command -v magick || command -v convert)" "${HOME}/.local/overrides/magick" \
 && curl -L "https://github.com/tsl0922/ttyd/releases/latest/download/ttyd.x86_64" -o "${HOME}/.local/overrides/ttyd" \
 && chmod +x "${HOME}/.local/overrides/ttyd"

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
  bat \
  cloudflared \
  deno \
  duckdb \
  fd \
  gcloud \
  gdu \
  github-cli \
  github:dandavison/delta \
  github:jqnatividad/qsv \
  github:mithrandie/csvq \
  github:pdfcpu/pdfcpu \
  github:casey/just \
  github:phiresky/ripgrep-all[extract_all=true] \
  github:rtk-ai/rtk \
  hugo \
  jaq \
  node \
  pandoc \
  rclone \
  ripgrep \
  sd \
  uv \
  websocat \
  yq \
  '

# Install cargo. Takes ~1 min
RUN bash -lc 'curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y; \
  . "$HOME/.cargo/env"; \
  cargo install --locked resvg; \
  '

# Install Python tools, pinning Playwright so its browsers and Docker seccomp
# profile can be kept on the same release.
RUN bash -lc 'eval "$(mise env -s bash)"; \
  mkdir -p ~/apps/global; \
  cd ~/apps/global; \
  uv venv; \
  source .venv/bin/activate; \
  uv pip install cairosvg csvkit dprint yt-dlp markitdown httpx pandas pillow ruff llm typer rich orjson lxml tenacity pytest google_genai "playwright==${PLAYWRIGHT_VERSION}"; \
  llm install llm-cmd llm-openrouter llm-gemini llm-anthropic llm-openai-plugin llm-whisper-api llm-groq-whisper; \
  '

# Playwright's Firefox and WebKit are patched builds; Chromium is kept too so
# normal Playwright defaults and CLI commands continue to work. System Chrome
# remains independently discoverable through /usr/bin and /usr/local/bin.
USER root
RUN /home/vscode/apps/global/.venv/bin/playwright install-deps chromium firefox webkit \
 && rm -rf /var/lib/apt/lists/*

USER vscode
RUN bash -lc 'eval "$(mise env -s bash)"; \
  playwright install chromium firefox webkit; \
  '

# Global npm executables under a mise-managed Node are not reliably visible
# until `mise reshim node` runs, so keep that coupled to any future CLI adds.
# Takes ~5 min
RUN bash -lc 'eval "$(mise env -s bash)"; \
  npm install -g npm@latest; \
  npm install -g wscat@latest; \
  npm install -g @googleworkspace/cli@latest; \
  npm install -g pixelmatch pngjs; \
  mise reshim node \
  '

# Install frequently changing agent CLIs last to keep them fresh
# Takes ~1.5 min
RUN bash -lc 'eval "$(mise env -s bash)"; \
  echo "17 Jul 2026: Updating agents and fast-moving agent tools"; \
  npm install -g agent-browser@latest; \
  npm install -g @openai/codex@latest; \
  npm install -g @github/copilot@latest; \
  npm install -g --ignore-scripts @earendil-works/pi-coding-agent@latest; \
  mise reshim node \
  '
# No need to install claude since ~/.local/share/claude is shared. Run `claude update` periodically
# agy (antigravity-cli) is also from host. But you need to run `agy` once inside container to log in. #TODO Not sure where credentials are saved.

# Default back to root for image setup; we'll run as UID 1000 at runtime
USER root

# Exporting to layers takes ~3 min
