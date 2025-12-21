#!/usr/bin/env bash
# Check environment in containers (direct tests, no helpers)
set -o xtrace
set -uo pipefail

# --- Meta / identity ---
date -Is || date
id
uname -a
hostname
pwd
echo "PATH=$PATH"
echo "SHELL=${SHELL-}"

# --- OS / distro ---
cat /etc/os-release
lsb_release -a
cat /proc/version
cat /proc/cmdline

# --- CPU / mem / disk ---
nproc
lscpu
cat /proc/cpuinfo
free -h
cat /proc/meminfo
df -h
lsblk
mount
ulimit -a

# --- Proc/sys quirks often seen in containers ---
ls -la /proc/sys 2>/dev/null || true
ls -la /proc/sys/fs 2>/dev/null || true
ls -la /proc/sys/fs/inotify 2>/dev/null || true
cat /proc/sys/fs/inotify/max_user_watches 2>/dev/null || true
cat /proc/sys/fs/inotify/max_user_instances 2>/dev/null || true

# --- Cgroup/container signals ---
cat /proc/1/cgroup 2>/dev/null || true
cat /proc/self/cgroup 2>/dev/null || true

# --- Environment (WARNING: may include secrets) ---
env | sort

# --- Networking (local state) ---
cat /etc/hosts
cat /etc/resolv.conf
ip a
ip route
ifconfig -a
cat /proc/net/dev
ss -tulpen
netstat -tulpen

# --- Shells ---
bash --version
zsh --version
fish --version

# --- Toolchain / langs (broad sweep) ---
make --version
cmake --version
gcc --version
g++ --version
python --version
python3 --version
pip --version
pip3 --version
java -version
go version
rustc --version
cargo --version
perl -v
ruby -v
php -v

# Other tools
fd --version
rg --version
ug --version
git --version
gh --version
curl --version
w3m -version
lynx --version
websocat --version
wscat --version
jq --version
jaq --version
qsv --version
csvq --version
uv --version
uvx ruff --version
uvx yt-dlp --version
uvx markitdown --version
sg --version
duckdb --version
sqlite3 --version
pdfcpu version
qpdf --version
pdftoppm --version
pandoc --version
magick --version
cwebp -version
ffmpeg -version

# --- JS runtimes / package managers ---
node --version
npm --version
npx --version
corepack --version
deno --version
bun --version
pnpm --version
yarn --version
ts-node --version
tsc --version
qjs -v
js --version

# Node detail dump (useful for ABI/OpenSSL/ICU)
node -p "process.versions"
node -p "process.platform + ' ' + process.arch"
node -e "console.log('node_exec_ok')"

# npm globals (can be large)
npm config get registry
npm ls -g --depth=0

# --- Headless browsers (inventory + headless smoke) ---
chromium --version
google-chrome --version
google-chrome-stable --version
chrome --version
chromedriver --version
firefox --version
microsoft-edge --version

# --- DNS + egress (bounded) ---
getent hosts example.com
nslookup example.com
dig example.com

# Quick TCP reachability checks (won’t hang)
curl -fsSI --max-time 5 https://example.com
wget -S --spider -T 5 https://example.com

# --- npm install capability: online probe (bounded) ---
# Use `timeout` if present; otherwise skip to avoid hanging in locked-down containers.
timeout 10s npm view lodash version
timeout 10s npm ping
