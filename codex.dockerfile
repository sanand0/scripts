FROM ghcr.io/openai/codex-universal:latest

ARG DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gnupg && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null && \
    chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        git \
        gh \
        pkg-config \
        libssl-dev \
        jq \
        less \
        nodejs \
        npm \
        poppler-utils \
        sqlite3 \
        unzip && \
    rm -rf /var/lib/apt/lists/*

# Install uv for Python tooling.
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    install -m 755 /root/.local/bin/uv /usr/local/bin/uv && \
    install -m 755 /root/.local/bin/uvx /usr/local/bin/uvx

# Install Codex CLI via npm (ships native binary under @openai/codex).
RUN npm install -g @openai/codex
