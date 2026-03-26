#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# openclaw-cms-plugin one-line installer (wget variant) — v2
#
# Compatible with both openclaw and clawdbot/moltbot gateway kernels.
# Automatically detects the config directory and plugin manifest name.
#
# Does NOT require OpenClaw to be installed beforehand.
# Does NOT restart the OpenClaw gateway — the caller must do so
# (typically via `exec /usr/local/bin/docker-entrypoint.sh` in the
#  container command).
#
# Usage:
#   wget -qO- https://<oss-host>/install-wget.sh | bash -s -- \
#     --endpoint "https://..." \
#     --x-arms-license-key "xxx" \
#     --x-arms-project "xxx" \
#     --x-cms-workspace "xxx" \
#     --serviceName "my-service"
# ---------------------------------------------------------------------------
set -euo pipefail

PLUGIN_NAME="openclaw-cms-plugin"
DIAG_PLUGIN_NAME="diagnostics-otel"
DEFAULT_PLUGIN_URL="https://arms-apm-cn-hangzhou-pre.oss-cn-hangzhou.aliyuncs.com/openclaw-cms-plugin/openclaw-cms-plugin.tar.gz"

# ── Defaults ──
ENDPOINT=""
LICENSE_KEY=""
ARMS_PROJECT=""
CMS_WORKSPACE=""
SERVICE_NAME=""
PLUGIN_URL="${DEFAULT_PLUGIN_URL}"
INSTALL_DIR=""
ENABLE_METRICS=false

# ── Color helpers ──
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }

# ── Parse arguments ──
need_value() {
  if [[ $# -lt 2 ]] || [[ "$2" == --* ]]; then
    error "Option $1 requires a value"
    exit 1
  fi
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --endpoint)           need_value "$@"; ENDPOINT="$2";       shift 2 ;;
    --x-arms-license-key) need_value "$@"; LICENSE_KEY="$2";    shift 2 ;;
    --x-arms-project)     need_value "$@"; ARMS_PROJECT="$2";   shift 2 ;;
    --x-cms-workspace)    need_value "$@"; CMS_WORKSPACE="$2";  shift 2 ;;
    --serviceName)        need_value "$@"; SERVICE_NAME="$2";   shift 2 ;;
    --plugin-url)         need_value "$@"; PLUGIN_URL="$2";     shift 2 ;;
    --install-dir)        need_value "$@"; INSTALL_DIR="$2";    shift 2 ;;
    --enable-metrics)     ENABLE_METRICS=true; shift ;;
    --disable-metrics)    ENABLE_METRICS=false; shift ;;
    *)
      warn "Unknown option: $1 (ignored)"
      shift
      ;;
  esac
done

# ── Validate required parameters ──
MISSING=()
[[ -z "$ENDPOINT" ]]      && MISSING+=("--endpoint")
[[ -z "$LICENSE_KEY" ]]    && MISSING+=("--x-arms-license-key")
[[ -z "$ARMS_PROJECT" ]]   && MISSING+=("--x-arms-project")
[[ -z "$CMS_WORKSPACE" ]]  && MISSING+=("--x-cms-workspace")
[[ -z "$SERVICE_NAME" ]]   && MISSING+=("--serviceName")

if [[ ${#MISSING[@]} -gt 0 ]]; then
  error "Missing required parameters: ${MISSING[*]}"
  echo ""
  echo "Usage:"
  echo "  wget -qO- https://<host>/install-wget.sh | bash -s -- \\"
  echo "    --endpoint \"https://...\" \\"
  echo "    --x-arms-license-key \"xxx\" \\"
  echo "    --x-arms-project \"xxx\" \\"
  echo "    --x-cms-workspace \"xxx\" \\"
  echo "    --serviceName \"my-service\""
  exit 1
fi

# ── Check prerequisites ──
info "Checking prerequisites..."

if ! command -v node &>/dev/null; then
  error "Node.js is not installed. Please install Node.js >= 18 first."
  exit 1
fi

NODE_MAJOR=$(node -e "process.stdout.write(String(process.versions.node.split('.')[0]))")
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  error "Node.js >= 18 is required (current: $(node --version))"
  exit 1
fi
ok "Node.js $(node --version)"

if ! command -v npm &>/dev/null; then
  error "npm is not installed."
  exit 1
fi
ok "npm $(npm --version)"

if ! command -v wget &>/dev/null; then
  error "wget is not installed."
  exit 1
fi
ok "wget available"

# ══════════════════════════════════════════════════════════════
# ── Detect gateway kernel: clawdbot / moltbot / openclaw ──
# ══════════════════════════════════════════════════════════════
GATEWAY_KERNEL=""
CONFIG_DIR=""
CONFIG_FILENAME=""
MANIFEST_NAME=""

detect_gateway_kernel() {
  # Priority: clawdbot > moltbot > openclaw
  # Check by: 1) existing config dir  2) running process  3) binary in PATH

  # 1) Check existing config directories
  if [[ -d "$HOME/.clawdbot" ]]; then
    GATEWAY_KERNEL="clawdbot"
    CONFIG_DIR="$HOME/.clawdbot"
    CONFIG_FILENAME="clawdbot.json"
    MANIFEST_NAME="moltbot.plugin.json"
    return
  fi
  if [[ -d "$HOME/.moltbot" ]]; then
    GATEWAY_KERNEL="moltbot"
    CONFIG_DIR="$HOME/.moltbot"
    CONFIG_FILENAME="moltbot.json"
    MANIFEST_NAME="moltbot.plugin.json"
    return
  fi
  if [[ -d "$HOME/.openclaw" ]]; then
    GATEWAY_KERNEL="openclaw"
    CONFIG_DIR="$HOME/.openclaw"
    CONFIG_FILENAME="openclaw.json"
    MANIFEST_NAME="openclaw.plugin.json"
    return
  fi

  # 2) Check running processes
  if pgrep -f "clawdbot" &>/dev/null 2>&1 || pgrep -f "Clawdbot" &>/dev/null 2>&1; then
    GATEWAY_KERNEL="clawdbot"
    CONFIG_DIR="$HOME/.clawdbot"
    CONFIG_FILENAME="clawdbot.json"
    MANIFEST_NAME="moltbot.plugin.json"
    return
  fi
  if pgrep -f "moltbot" &>/dev/null 2>&1; then
    GATEWAY_KERNEL="moltbot"
    CONFIG_DIR="$HOME/.moltbot"
    CONFIG_FILENAME="moltbot.json"
    MANIFEST_NAME="moltbot.plugin.json"
    return
  fi

  # 3) Check binaries in PATH
  if command -v clawdbot &>/dev/null 2>&1; then
    GATEWAY_KERNEL="clawdbot"
    CONFIG_DIR="$HOME/.clawdbot"
    CONFIG_FILENAME="clawdbot.json"
    MANIFEST_NAME="moltbot.plugin.json"
    return
  fi
  if command -v moltbot &>/dev/null 2>&1; then
    GATEWAY_KERNEL="moltbot"
    CONFIG_DIR="$HOME/.moltbot"
    CONFIG_FILENAME="moltbot.json"
    MANIFEST_NAME="moltbot.plugin.json"
    return
  fi

  # 4) Check docker-entrypoint.sh content for hints
  if [[ -f "/usr/local/bin/docker-entrypoint.sh" ]]; then
    local entrypoint_content
    entrypoint_content=$(cat /usr/local/bin/docker-entrypoint.sh 2>/dev/null || true)
    if echo "$entrypoint_content" | grep -qi "clawdbot" 2>/dev/null; then
      GATEWAY_KERNEL="clawdbot"
      CONFIG_DIR="$HOME/.clawdbot"
      CONFIG_FILENAME="clawdbot.json"
      MANIFEST_NAME="moltbot.plugin.json"
      return
    fi
    if echo "$entrypoint_content" | grep -qi "moltbot" 2>/dev/null; then
      GATEWAY_KERNEL="moltbot"
      CONFIG_DIR="$HOME/.moltbot"
      CONFIG_FILENAME="moltbot.json"
      MANIFEST_NAME="moltbot.plugin.json"
      return
    fi
  fi

  # 5) Default to openclaw
  GATEWAY_KERNEL="openclaw"
  CONFIG_DIR="$HOME/.openclaw"
  CONFIG_FILENAME="openclaw.json"
  MANIFEST_NAME="openclaw.plugin.json"
}

detect_gateway_kernel
info "Detected gateway kernel: ${GATEWAY_KERNEL}"
info "Config directory: ${CONFIG_DIR}"
info "Config filename: ${CONFIG_FILENAME}"
info "Plugin manifest: ${MANIFEST_NAME}"

# ── Determine install directory ──
if [[ -n "$INSTALL_DIR" ]]; then
  TARGET_DIR="$INSTALL_DIR"
else
  TARGET_DIR="/opt/${PLUGIN_NAME}"
fi

info "Install directory: ${TARGET_DIR}"

# ── Clean previous installation ──
if [[ -d "$TARGET_DIR" ]]; then
  if [[ -z "$(ls -A "$TARGET_DIR" 2>/dev/null)" ]]; then
    info "Target directory exists but is empty, skipping cleanup."
  elif [[ -f "$TARGET_DIR/package.json" ]] || [[ -f "$TARGET_DIR/openclaw.plugin.json" ]] || [[ -f "$TARGET_DIR/moltbot.plugin.json" ]]; then
    info "Removing previous installation..."
    rm -rf "$TARGET_DIR"
  else
    warn "Target directory exists but does not look like a plugin installation, removing anyway..."
    rm -rf "$TARGET_DIR"
  fi
fi
mkdir -p "$TARGET_DIR"

# ── Download and extract ──
info "Downloading plugin from ${PLUGIN_URL}..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

wget -q --no-cache "$PLUGIN_URL" -O "$TMP_DIR/plugin.tar.gz"
ok "Downloaded"

info "Extracting to ${TARGET_DIR}..."
tar -xzf "$TMP_DIR/plugin.tar.gz" -C "$TMP_DIR"
if [[ -d "$TMP_DIR/${PLUGIN_NAME}" ]]; then
  cp -rf "$TMP_DIR/${PLUGIN_NAME}/." "$TARGET_DIR/"
else
  cp -rf "$TMP_DIR/." "$TARGET_DIR/"
fi
ok "Extracted"

# ── Create moltbot.plugin.json if needed ──
# The tarball ships openclaw.plugin.json; clawdbot/moltbot kernels
# look for moltbot.plugin.json instead.
if [[ "$MANIFEST_NAME" == "moltbot.plugin.json" ]] && [[ -f "$TARGET_DIR/openclaw.plugin.json" ]] && [[ ! -f "$TARGET_DIR/moltbot.plugin.json" ]]; then
  cp "$TARGET_DIR/openclaw.plugin.json" "$TARGET_DIR/moltbot.plugin.json"
  ok "Created ${MANIFEST_NAME} from openclaw.plugin.json"
fi

# ── Install npm dependencies for openclaw-cms-plugin ──
info "Installing npm dependencies (production only)..."
cd "$TARGET_DIR"
if ! npm install --omit=dev --ignore-scripts 2>&1; then
  error "npm install failed in ${TARGET_DIR}"
  exit 1
fi
ok "Dependencies installed"

# ══════════════════════════════════════════════════════════════
# ── Determine config file path ──
# ══════════════════════════════════════════════════════════════
# The entrypoint generates the config file at startup.
# If it doesn't exist yet (pre-entrypoint phase), we create it
# so the entrypoint can merge our plugins config.
# We also set up a background watcher to inject config after
# entrypoint generates it (in case entrypoint overwrites).
CONFIG_PATH="${CONFIG_DIR}/${CONFIG_FILENAME}"
mkdir -p "$CONFIG_DIR"

info "Config file path: ${CONFIG_PATH}"

# ── Build plugins config JSON ──
PLUGINS_CONFIG=$(node -e "
const pluginName   = process.argv[1];
const installDir   = process.argv[2];
const endpoint     = process.argv[3];
const licenseKey   = process.argv[4];
const armsProject  = process.argv[5];
const cmsWorkspace = process.argv[6];
const serviceName  = process.argv[7];

const config = {
  plugins: {
    allow: [pluginName],
    load: { paths: [installDir] },
    entries: {}
  }
};

config.plugins.entries[pluginName] = {
  enabled: true,
  config: {
    endpoint: endpoint,
    headers: {
      'x-arms-license-key': licenseKey,
      'x-arms-project': armsProject,
      'x-cms-workspace': cmsWorkspace
    },
    serviceName: serviceName
  }
};

process.stdout.write(JSON.stringify(config));
" "$PLUGIN_NAME" "$TARGET_DIR" "$ENDPOINT" "$LICENSE_KEY" "$ARMS_PROJECT" "$CMS_WORKSPACE" "$SERVICE_NAME")

# ── Write or merge config ──
info "Updating config: ${CONFIG_PATH}"

node -e "
const fs = require('fs');
const configPath = process.argv[1];
const pluginsConfig = JSON.parse(process.argv[2]);

let config = {};
try {
  config = JSON.parse(fs.readFileSync(configPath, 'utf8'));
} catch (e) {
  if (e.code !== 'ENOENT') {
    console.error('[WARN] Failed to parse existing config, starting fresh:', e.message);
  }
}

// Deep merge plugins config
if (!config.plugins) config.plugins = {};

// Merge allow list
if (!Array.isArray(config.plugins.allow)) config.plugins.allow = [];
for (const name of (pluginsConfig.plugins.allow || [])) {
  if (!config.plugins.allow.includes(name)) {
    config.plugins.allow.push(name);
  }
}

// Merge load paths
if (!config.plugins.load) config.plugins.load = {};
if (!Array.isArray(config.plugins.load.paths)) config.plugins.load.paths = [];
for (const path of (pluginsConfig.plugins.load?.paths || [])) {
  const idx = config.plugins.load.paths.findIndex(p => p.includes('openclaw-cms-plugin'));
  if (idx >= 0) config.plugins.load.paths[idx] = path;
  else config.plugins.load.paths.push(path);
}

// Merge entries
if (!config.plugins.entries) config.plugins.entries = {};
Object.assign(config.plugins.entries, pluginsConfig.plugins.entries);

fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n', 'utf8');
console.log('[CMS] Config written to ' + configPath);
" "$CONFIG_PATH" "$PLUGINS_CONFIG"

ok "Config updated"

# ══════════════════════════════════════════════════════════════
# ── Background config injector ──
# ══════════════════════════════════════════════════════════════
# The entrypoint (docker-entrypoint.sh) generates the config file
# AFTER this script runs. It may overwrite our plugins config.
# This background watcher re-injects the plugins config after
# the entrypoint generates the config file.
info "Starting background config injector..."

INJECTOR_SCRIPT=$(cat <<'INJECTOR_EOF'
const fs = require('fs');
const configPath = process.argv[1];
const pluginsConfig = JSON.parse(process.argv[2]);
const maxWaitSeconds = 120;
const checkIntervalMs = 1000;

let injected = false;
let elapsed = 0;

const timer = setInterval(() => {
  elapsed += checkIntervalMs / 1000;
  if (elapsed > maxWaitSeconds) {
    clearInterval(timer);
    if (!injected) {
      console.error('[CMS] Timeout waiting for config file: ' + configPath);
    }
    process.exit(0);
  }

  try {
    const raw = fs.readFileSync(configPath, 'utf8');
    const config = JSON.parse(raw);

    // Check if plugins config already present
    if (config.plugins && config.plugins.entries &&
        config.plugins.entries['openclaw-cms-plugin'] &&
        config.plugins.entries['openclaw-cms-plugin'].enabled) {
      if (!injected) {
        // Already has our config (either we wrote it or entrypoint kept it)
        injected = true;
      }
      // Keep watching for a bit in case entrypoint overwrites
      return;
    }

    // Config exists but missing our plugins — inject
    if (!config.plugins) config.plugins = {};
    if (!Array.isArray(config.plugins.allow)) config.plugins.allow = [];
    for (const name of (pluginsConfig.plugins.allow || [])) {
      if (!config.plugins.allow.includes(name)) {
        config.plugins.allow.push(name);
      }
    }
    if (!config.plugins.load) config.plugins.load = {};
    if (!Array.isArray(config.plugins.load.paths)) config.plugins.load.paths = [];
    for (const path of (pluginsConfig.plugins.load?.paths || [])) {
      const idx = config.plugins.load.paths.findIndex(p => p.includes('openclaw-cms-plugin'));
      if (idx >= 0) config.plugins.load.paths[idx] = path;
      else config.plugins.load.paths.push(path);
    }
    if (!config.plugins.entries) config.plugins.entries = {};
    Object.assign(config.plugins.entries, pluginsConfig.plugins.entries);

    fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + '\n', 'utf8');
    console.log('[CMS] Injected plugins into ' + configPath);
    injected = true;
  } catch (e) {
    // File not ready yet, keep waiting
  }
}, checkIntervalMs);
INJECTOR_EOF
)

# Run injector in background — it will exit after injection or timeout
node -e "$INJECTOR_SCRIPT" "$CONFIG_PATH" "$PLUGINS_CONFIG" &
INJECTOR_PID=$!
ok "Background injector started (PID: ${INJECTOR_PID})"

# Also watch other possible config paths because the gateway may
# auto-migrate configs (e.g. .clawdbot → .moltbot, clawdbot.json → moltbot.json).
# We need to ensure plugins config survives any migration.
EXTRA_CONFIG_PATHS=()
for kernel_dir in ".clawdbot" ".moltbot" ".openclaw"; do
  for config_name in "clawdbot.json" "moltbot.json" "openclaw.json"; do
    candidate="$HOME/${kernel_dir}/${config_name}"
    if [[ "$candidate" != "$CONFIG_PATH" ]]; then
      EXTRA_CONFIG_PATHS+=("$candidate")
    fi
  done
done

for alt_path in "${EXTRA_CONFIG_PATHS[@]}"; do
  node -e "$INJECTOR_SCRIPT" "$alt_path" "$PLUGINS_CONFIG" &
done
ok "Background injectors watching all possible config paths"

# ── Clean up stale lock files ──
# Gateway stores lock files in both /tmp and config directories.
# The "gateway already running" error occurs when stale locks remain
# from a previous container run (especially PID 1 locks).
info "Cleaning stale lock files..."
rm -f /tmp/moltbot*.lock /tmp/clawdbot*.lock /tmp/gateway*.lock /tmp/*.pid 2>/dev/null || true
# Clean lock files in all possible config directories
for lock_dir in "$HOME/.clawdbot" "$HOME/.moltbot" "$HOME/.openclaw"; do
  if [[ -d "$lock_dir" ]]; then
    rm -f "$lock_dir"/*.lock "$lock_dir"/*.pid "$lock_dir"/gateway.lock 2>/dev/null || true
    # Also clean any lock-like files (some gateways use .lock suffix or pid files)
    find "$lock_dir" -maxdepth 1 \( -name "*.lock" -o -name "*.pid" -o -name "lock" -o -name "gateway.pid" \) -delete 2>/dev/null || true
  fi
done
ok "Lock files cleaned"

# ── Summary ──
echo ""
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅ openclaw-cms-plugin installed successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════${NC}"
echo ""
echo "  Gateway kernel: ${GATEWAY_KERNEL}"
echo "  Install dir:    ${TARGET_DIR}"
echo "  Config file:    ${CONFIG_PATH}"
echo "  Manifest:       ${TARGET_DIR}/${MANIFEST_NAME}"
echo "  Endpoint:       ${ENDPOINT}"
echo "  Service name:   ${SERVICE_NAME}"
echo "  Metrics:        ${ENABLE_METRICS}"
echo ""
echo -e "${CYAN}  Background injector is running to ensure config${NC}"
echo -e "${CYAN}  survives entrypoint regeneration.${NC}"
echo ""
info "The gateway will be started by the entrypoint."
echo ""
