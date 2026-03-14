#!/usr/bin/env bash
# Quick smoke test that reports only the environment issues you need to fix.
# By default it re-runs itself inside `dev.sh` so container-only checks do not
# fail just because you launched it from the host shell. Use `--local-only` to
# test the current shell instead.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="${SCRIPT_DIR}/$(basename "${BASH_SOURCE[0]}")"

inside_container=0
local_only=0
for arg in "$@"; do
  case "$arg" in
    --inside-container)
      inside_container=1
      ;;
    --local-only)
      local_only=1
      ;;
    *)
      printf 'ERROR: unknown argument: %s\n' "$arg" >&2
      exit 2
      ;;
  esac
done

# Keep track of any failure and remember temporary paths for later cleanup.
errors=0
total_checks=0
passed_checks=0
failed_checks=0
running_line_visible=0
cleanup_items=()
failure_log_dir=''

now_ns() {
  date +%s%N
}

script_start_ns="$(now_ns)"

if [ -t 1 ]; then
  tty_output=1
  color_red=$'\033[31m'
  color_green=$'\033[32m'
  color_yellow=$'\033[33m'
  color_reset=$'\033[0m'
else
  tty_output=0
  color_red=''
  color_green=''
  color_yellow=''
  color_reset=''
fi

# format_duration renders nanoseconds as a short seconds.millis string.
format_duration() {
  local duration_ns="$1"
  local duration_ms=$((duration_ns / 1000000))
  printf '%d.%03ds' "$((duration_ms / 1000))" "$((duration_ms % 1000))"
}

# print_note emits a short secondary line for diagnostics.
print_note() {
  printf '%bnote%b %s\n' "$color_yellow" "$color_reset" "$1"
}

# running_in_container returns success when this script is already executing in a container.
running_in_container() {
  [ -f /.dockerenv ] || grep -qaE '(docker|containerd|kubepods)' /proc/1/cgroup 2>/dev/null
}

# The default path exercises the real dev-container contract. `--local-only` is
# intentionally a debugging escape hatch, not the primary mode.
if [ "$inside_container" -eq 0 ] && [ "$local_only" -eq 0 ] && ! running_in_container; then
  docker_args=()
  if [ "$SCRIPT_DIR" != "$PWD" ]; then
    docker_args+=(-v "${SCRIPT_DIR}:${SCRIPT_DIR}:ro")
  fi
  print_note "re-running inside dev container via dev.sh (use --local-only to test this shell)"
  exec bash "${SCRIPT_DIR}/dev.sh" "${docker_args[@]}" -- "$SCRIPT_PATH" --inside-container
fi

# print_result emits one concise, color-coded line per check.
print_result() {
  local status="$1"
  local duration_ns="$2"
  local label="$3"
  local color="$color_green"
  if [ "$status" = "FAIL" ]; then
    color="$color_red"
  fi
  printf '%b%-4s%b %8s  %s\n' "$color" "$status" "$color_reset" "$(format_duration "$duration_ns")" "$label"
}

# print_running shows the in-flight check on a single transient line.
print_running() {
  local label="$1"
  if [ "$tty_output" -eq 1 ]; then
    running_line_visible=1
    printf '\r\033[2K%b%-4s%b %8s  %s' "$color_yellow" "RUN" "$color_reset" "..." "$label"
  fi
}

# clear_running removes the transient in-flight line before printing the final result.
clear_running() {
  if [ "$tty_output" -eq 1 ] && [ "$running_line_visible" -eq 1 ]; then
    running_line_visible=0
    printf '\r\033[2K'
  fi
}

# Keep the success path quiet; only retain detailed command output for failures.
# This makes the script usable as a fast smoke test while still leaving clues
# when a check breaks.
# ensure_failure_log_dir lazily creates a directory that keeps failed command output.
ensure_failure_log_dir() {
  if [ -n "$failure_log_dir" ]; then
    return 0
  fi
  failure_log_dir="$(mktemp -d 2>/dev/null || mktemp -d -t dev-envtest-logs)" || return 1
  cleanup_items+=("$failure_log_dir")
}

# print_failure_excerpt shows a short hint for why a command failed.
print_failure_excerpt() {
  local log_file="$1"
  local excerpt
  excerpt="$(awk 'NF { print; exit }' "$log_file" 2>/dev/null | cut -c1-240)"
  if [ -n "$excerpt" ]; then
    print_note "$excerpt"
  fi
  if [ "${DEV_TEST_VERBOSE:-0}" = "1" ]; then
    sed 's/^/      /' "$log_file"
  fi
}

# run_check executes a command or function, then reports its status and timing.
run_check() {
  local label="$1"
  shift
  local start_ns
  local end_ns
  local duration_ns
  local log_file=''
  total_checks=$((total_checks + 1))
  print_running "$label"
  start_ns="$(now_ns)"
  if ensure_failure_log_dir; then
    log_file="$failure_log_dir/check-$(printf '%03d' "$total_checks").log"
  fi
  if "$@" >"${log_file:-/dev/null}" 2>&1; then
    end_ns="$(now_ns)"
    duration_ns=$((end_ns - start_ns))
    passed_checks=$((passed_checks + 1))
    [ -n "$log_file" ] && rm -f "$log_file"
    clear_running
    print_result PASS "$duration_ns" "$label"
    return 0
  fi
  end_ns="$(now_ns)"
  duration_ns=$((end_ns - start_ns))
  failed_checks=$((failed_checks + 1))
  errors=1
  clear_running
  print_result FAIL "$duration_ns" "$label"
  if [ -n "$log_file" ] && [ -s "$log_file" ]; then
    print_failure_excerpt "$log_file"
  fi
  return 1
}

# fail records an internal script failure that did not go through run_check.
fail() {
  local msg="$1"
  local label="${2:-$1}"
  total_checks=$((total_checks + 1))
  failed_checks=$((failed_checks + 1))
  errors=1
  clear_running
  print_result FAIL 0 "$label"
  if [ "$msg" != "$label" ]; then
    printf '%bnote%b %s\n' "$color_yellow" "$color_reset" "$msg"
  fi
}

has_command() {
  command -v "$1" >/dev/null 2>&1
}

check_command_runs() {
  local label="$1"
  shift
  run_check "$label" "$@"
}

env_var_present() {
  printenv "$1" >/dev/null 2>&1
}

env_var_equals() {
  [ "$(printenv "$1" 2>/dev/null || true)" = "$2" ]
}

check_env_eq() {
  local name="$1"
  local expected="$2"
  run_check "printenv $name == $expected" env_var_equals "$name" "$expected"
}

shm_size_large_enough() {
  local shm_size_mb
  shm_size_mb="$(df -Pm /dev/shm 2>/dev/null | awk 'NR==2 {print $2}')"
  [[ -n "$shm_size_mb" && "$shm_size_mb" =~ ^[0-9]+$ && "$shm_size_mb" -ge 7800 ]]
}

path_is_executable() {
  [ -x "$1" ]
}

python_packages_present() {
  local python_bin="$1"
  shift
  "$python_bin" -m pip show "$@" >/dev/null 2>&1
}

npm_global_packages_present() {
  npm ls -g --depth=0 "$@" >/dev/null 2>&1
}

npm_install_lodash() {
  (
    cd "$1" &&
    npm install lodash >/dev/null 2>&1
  )
}

any_directory_exists() {
  local path
  for path in "$@"; do
    if [ -d "$path" ]; then
      return 0
    fi
  done
  return 1
}

mounted_font_dirs_have_files() {
  local dir
  for dir in "$@"; do
    if [ -d "$dir" ] && find "$dir" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' -o -iname '*.woff' -o -iname '*.woff2' \) -print -quit | grep -q .; then
      return 0
    fi
  done
  return 1
}

fontconfig_sees_mounted_fonts() {
  local dir
  local file
  for dir in "$@"; do
    if [ -d "$dir" ] && find "$dir" -type f \( -iname '*.ttf' -o -iname '*.otf' -o -iname '*.ttc' -o -iname '*.woff' -o -iname '*.woff2' \) -print -quit | grep -q .; then
      while IFS= read -r file; do
        case "$file" in
          "$dir"/*)
            return 0
            ;;
        esac
      done < <(fc-list -f '%{file}\n')
    fi
  done
  return 1
}

playwright_screenshot_works() {
  local browser="$1"
  local html_path="$2"
  local screenshot_path="$3"
  playwright screenshot --browser "$browser" "file://$html_path" "$screenshot_path" >/dev/null 2>&1 && [ -s "$screenshot_path" ]
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
  clear_running
  for item in "${cleanup_items[@]}"; do
    if [ "$errors" -ne 0 ] && [ -n "$failure_log_dir" ] && [ "$item" = "$failure_log_dir" ]; then
      continue
    fi
    [ -e "$item" ] && rm -rf "$item"
  done
}

# Always clean up, even if the script exits early.
trap cleanup EXIT

# These env vars are part of the `dev.sh` runtime contract. When one changes,
# the container wiring changed too, so keep this list in sync with `dev.sh`.
# Confirm a few core environment variables exist so scripts behave predictably.
required_env_vars=(HOME PATH SHELL TERM COLORTERM LANG USER UV_LINK_MODE CLAUDE_CODE_MAX_OUTPUT_TOKENS PLAYWRIGHT_BROWSERS_PATH)
for var in "${required_env_vars[@]}"; do
  run_check "printenv $var" env_var_present "$var"
done

check_env_eq UV_LINK_MODE copy
check_env_eq CLAUDE_CODE_MAX_OUTPUT_TOKENS 64000
check_env_eq PLAYWRIGHT_BROWSERS_PATH /home/vscode/.local/share/playwright-browsers

# Cover newer dev.sh runtime settings that matter for browsers and hard-link-safe uv installs.
run_check "/dev/shm >= 7800MB" shm_size_large_enough

# Exercise the everyday CLI tools rather than only checking PATH entries.
check_command_runs "fd --version" fd --version
check_command_runs "find --version" find --version
check_command_runs "rg --version" rg --version
check_command_runs "ug --version" ug --version
check_command_runs "grep --version" grep --version
check_command_runs "git --version" git --version
check_command_runs "curl --version" curl --version
check_command_runs "w3m -version" w3m -version
check_command_runs "lynx --version" lynx --version
check_command_runs "jq --version" jq --version
check_command_runs "mise --version" mise --version
check_command_runs "node --version" node --version
check_command_runs "npm --version" npm --version
check_command_runs "csvq --version" csvq --version
check_command_runs "csvjson --version" csvjson --version
check_command_runs "uv --version" uv --version
check_command_runs "uvx --version" uvx --version
check_command_runs "qpdf --version" qpdf --version
check_command_runs "pandoc --version" pandoc --version
check_command_runs "duckdb --version" duckdb --version
check_command_runs "sqlite3 --version" sqlite3 --version
check_command_runs "psql --version" psql --version
check_command_runs "magick --version" magick --version
check_command_runs "cwebp -version" cwebp -version
check_command_runs "ffmpeg -version" ffmpeg -version
check_command_runs "pdftoppm -v" pdftoppm -v
check_command_runs "gs --version" gs --version
check_command_runs "fc-list --version" fc-list --version
check_command_runs "rsvg-convert --version" rsvg-convert --version
check_command_runs "resvg --version" resvg --version
check_command_runs "sg --version" sg --version
check_command_runs "deno --version" deno --version
check_command_runs "jaq --version" jaq --version
check_command_runs "qsv --version" qsv --version
check_command_runs "pdfcpu version" pdfcpu version
check_command_runs "rclone version" rclone version
check_command_runs "websocat --version" websocat --version
check_command_runs "wscat --help" wscat --help
check_command_runs "hugo version" hugo version
check_command_runs "cargo --version" cargo --version
check_command_runs "dprint --version" dprint --version
check_command_runs "yt-dlp --version" yt-dlp --version
check_command_runs "markitdown --help" markitdown --help
check_command_runs "playwright --version" playwright --version
check_command_runs "copilot version" copilot version
check_command_runs "gemini --help" gemini --help

# Check that GitHub CLI logins still work, otherwise repo automation fails.
check_command_runs "gh auth status --active" gh auth status --active

# Confirm the coding CLIs are callable and authenticated where supported.
check_command_runs "codex login status" codex login status
check_command_runs "claude --version" claude --version
check_command_runs "llm models list" llm models list

# Run the simplest Docker container to ensure the runtime is ready.
if run_check "docker version --format {{.Client.Version}}" docker version --format '{{.Client.Version}}'; then
  check_command_runs "docker run --rm hello-world" docker run --rm hello-world
fi

# Run a tiny uv install to show we can fetch Python packages locally.
if has_command uv; then
  global_python="${HOME}/apps/global/.venv/bin/python"
  if run_check "test -x $global_python" path_is_executable "$global_python"; then
    check_command_runs "$global_python --version" "$global_python" --version
    run_check "python packages cairosvg pillow" python_packages_present "$global_python" cairosvg pillow
  fi
  tmp_uv="$(make_tmpdir)"
  if [ -n "$tmp_uv" ]; then
    check_command_runs "uv pip install --target tmp requests" uv pip install --target "$tmp_uv" requests
  fi
fi

# Check package presence separately from CLI execution. This helps distinguish
# "npm package missing" from "package installed but PATH/shims broken".
# Bootstrap a Node project and install one dependency to prove npm works.
if has_command npm; then
  run_check "npm ls -g wscat playwright @github/copilot @google/gemini-cli @openai/codex --depth=0" \
    npm_global_packages_present \
    wscat \
    playwright \
    @github/copilot \
    @google/gemini-cli \
    @openai/codex
  run_check "npm ls -g pixelmatch pngjs --depth=0" npm_global_packages_present pixelmatch pngjs
  tmp_npm="$(make_tmpdir)"
  if [ -n "$tmp_npm" ]; then
    run_check "npm install lodash" npm_install_lodash "$tmp_npm"
  fi
fi

# Ensure fontconfig can see fonts from the mounted system/user font directories.
font_dirs=(/usr/share/fonts /usr/local/share/fonts "$HOME/.fonts" "$HOME/.local/share/fonts")
if run_check "font directories available" any_directory_exists "${font_dirs[@]}"; then
  run_check "mounted font files present" mounted_font_dirs_have_files "${font_dirs[@]}"
  run_check "fc-list sees mounted fonts" fontconfig_sees_mounted_fonts "${font_dirs[@]}"
fi

# The earlier `playwright --version` check only proves the CLI shim exists. The
# screenshot checks below prove the browser downloads and launch dependencies
# are actually usable at runtime.
# Playwright must be on PATH and able to launch each installed browser headlessly.
if has_command playwright; then
  tmp_playwright="$(make_tmpdir)"
  if [ -n "$tmp_playwright" ]; then
    cat <<'HTML' >"$tmp_playwright/index.html"
<!doctype html>
<html lang="en">
  <body>
    <h1>playwright smoke test</h1>
  </body>
</html>
HTML
    for browser in chromium firefox webkit; do
      screenshot="$tmp_playwright/${browser}.png"
      run_check "playwright screenshot --browser $browser" playwright_screenshot_works "$browser" "$tmp_playwright/index.html" "$screenshot"
    done
  fi
fi

# Run uvx pytest inside a temp project to prove tests can execute end to end.
if has_command uvx; then
  tmp_pytest="$(make_tmpdir)"
  if [ -n "$tmp_pytest" ]; then
    # Write a tiny passing test so pytest has real work to do.
    cat <<'PY' >"$tmp_pytest/test_sample.py"
import math

def test_trivial():
    assert math.sqrt(4) == 2
PY
    check_command_runs "uvx pytest temp project" uvx pytest "$tmp_pytest"
  fi
fi

# Smoke-test GPU tooling so CUDA workloads will not surprise us later.
if run_check "command -v nvidia-smi" has_command nvidia-smi; then
  check_command_runs "nvidia-smi" nvidia-smi
fi

# Print a short final summary so the overall state is obvious at a glance.
summary_status="PASS"
summary_color="$color_green"
if [ "$errors" -ne 0 ]; then
  summary_status="FAIL"
  summary_color="$color_red"
fi
printf '%b%-4s%b %8s  %d passed, %d failed, %d total\n' \
  "$summary_color" \
  "$summary_status" \
  "$color_reset" \
  "$(format_duration "$(( $(now_ns) - script_start_ns ))")" \
  "$passed_checks" \
  "$failed_checks" \
  "$total_checks"
if [ "$errors" -ne 0 ] && [ -n "$failure_log_dir" ] && [ -d "$failure_log_dir" ]; then
  print_note "failure logs kept in $failure_log_dir (set DEV_TEST_VERBOSE=1 to print full failing output)"
fi

# Return 0 only when every check succeeded.
exit "$errors"
