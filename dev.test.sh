#!/usr/bin/env bash
# Quick smoke test that reports only the environment issues you need to fix.
set -uo pipefail

# Keep track of any failure and remember temporary paths for later cleanup.
errors=0
cleanup_items=()

# fail prints a readable error and records that at least one check failed.
fail() {
  local msg="$1"
  local cmd="${2:-}"
  if [ -n "$cmd" ]; then
    printf 'ERROR: %s (cmd: %s)\n' "$msg" "$cmd" >&2
  else
    printf 'ERROR: %s\n' "$msg" >&2
  fi
  errors=1
}

# make_tmpdir creates disposable workspaces so every test runs in isolation.
make_tmpdir() {
  local tmp
  tmp="$(mktemp -d 2>/dev/null || mktemp -d -t dev-envtest)" || {
    fail "unable to create temporary directory" "mktemp -d"
    return 1
  }
  cleanup_items+=("$tmp")
  printf '%s' "$tmp"
}

# cleanup removes everything we created so the repo stays clean.
cleanup() {
  for item in "${cleanup_items[@]}"; do
    [ -e "$item" ] && rm -rf "$item"
  done
}

# Always clean up, even if the script exits early.
trap cleanup EXIT

# Confirm a few core environment variables exist so scripts behave predictably.
required_env_vars=(HOME PATH SHELL TERM COLORTERM LANG USER)
for var in "${required_env_vars[@]}"; do
  if ! printenv "$var" >/dev/null 2>&1; then
    fail "missing env var: $var" "printenv $var"
  fi
done

# Verify the everyday CLI tools are on PATH so workflows do not break later.
required_tools=(fd find rg ug grep git gh curl w3m lynx jq csvq csvjson uvx qpdf pandoc duckdb sqlite3 psql magick cwebp ffmpeg dprint yt-dlp markitdown)
for tool in "${required_tools[@]}"; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    fail "tool unavailable: $tool" "command -v $tool"
  fi
done

# Check that GitHub CLI logins still work, otherwise repo automation fails.
if ! gh auth status --active >/dev/null 2>&1; then
  fail "gh auth status failed" "gh auth status"
fi

# Confirm the codex CLI is installed and logged in for Codex-driven tasks.
if ! command -v codex >/dev/null 2>&1; then
  fail "tool unavailable: codex" "command -v codex"
else
  if ! codex login status >/dev/null 2>&1; then
    fail "codex login status failed" "codex login status"
  fi
fi

# Confirm the claude CLI is installed. #TODO There's no way (20 Nov 2025) to check login status.
if ! command -v claude >/dev/null 2>&1; then
  fail "tool unavailable: claude" "command -v claude"
fi

# Test the llm CLI so we know model listings are available when needed.
if ! command -v llm >/dev/null 2>&1; then
  fail "tool unavailable: llm" "command -v llm"
else
  if ! llm models list >/dev/null 2>&1; then
    fail "llm models list failed" "llm models list"
  fi
fi

# Run the simplest Docker container to ensure the runtime is ready.
if command -v docker >/dev/null 2>&1; then
  if ! docker run --rm hello-world >/dev/null 2>&1; then
    fail "docker hello-world failed" "docker run --rm hello-world"
  fi
else
  fail "tool unavailable: docker" "command -v docker"
fi

# Run a tiny uv install to show we can fetch Python packages locally.
if command -v uv >/dev/null 2>&1; then
  tmp_uv="$(make_tmpdir)"
  if [ -n "$tmp_uv" ]; then
    if ! uv pip install --target "$tmp_uv" requests >/dev/null 2>&1; then
      fail "uv pip install failed" "uv pip install --target $tmp_uv requests"
    fi
  fi
else
  fail "tool unavailable: uv" "command -v uv"
fi

# Bootstrap a Node project and install one dependency to prove npm works.
if command -v npm >/dev/null 2>&1; then
  tmp_npm="$(make_tmpdir)"
  if [ -n "$tmp_npm" ]; then
    (
      cd "$tmp_npm" &&
      npm install lodash >/dev/null 2>&1
    ) || fail "npm install test failed" "cd $tmp_npm && npm install lodash"
  fi
else
  fail "tool unavailable: npm" "command -v npm"
fi

# Run uvx pytest inside a temp project to prove tests can execute end to end.
if command -v uvx >/dev/null 2>&1; then
  tmp_pytest="$(make_tmpdir)"
  if [ -n "$tmp_pytest" ]; then
    # Write a tiny passing test so pytest has real work to do.
    cat <<'PY' >"$tmp_pytest/test_sample.py"
import math

def test_trivial():
    assert math.sqrt(4) == 2
PY
    if ! uvx pytest "$tmp_pytest" >/dev/null 2>&1; then
      fail "uvx pytest failed" "uvx pytest $tmp_pytest"
    fi
  fi
else
  fail "tool unavailable: uvx" "command -v uvx"
fi

# Smoke-test GPU tooling so CUDA workloads will not surprise us later.
if command -v nvidia-smi >/dev/null 2>&1; then
  if ! nvidia-smi >/dev/null 2>&1; then
    fail "nvidia-smi failed" "nvidia-smi"
  fi
else
  fail "tool unavailable: nvidia-smi" "command -v nvidia-smi"
fi

# Return 0 only when every check succeeded.
exit "$errors"
