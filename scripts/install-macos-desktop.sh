#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONTEND="$ROOT/frontend"
APP_NAME="Synplex AgentHub.app"
BUILT_APP="$FRONTEND/src-tauri/target/release/bundle/macos/$APP_NAME"
INSTALL_APP="/Applications/$APP_NAME"
BACKUP_ROOT="$HOME/Library/Application Support/Synplex AgentHub/Install Backups"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"

if [[ "$(uname -s)" != "Darwin" || "$(uname -m)" != "arm64" ]]; then
  echo "This installer supports Apple Silicon macOS only."
  exit 1
fi
if [[ ! -f "$FRONTEND/.env.desktop" ]]; then
  echo "Missing frontend/.env.desktop"
  exit 1
fi
if ! grep -qx 'VITE_API_BASE_URL=https://synplex.xyz/api' "$FRONTEND/.env.desktop"; then
  echo "Desktop API base must be https://synplex.xyz/api"
  exit 1
fi

cd "$FRONTEND"
npm ci
npm run typecheck
npm run test:run
npm run desktop:build

test -d "$BUILT_APP"
BINARY="$BUILT_APP/Contents/MacOS/synplex-agenthub"
test "$(file "$BINARY" | grep -c 'arm64')" -eq 1

# A local ad-hoc signature is deterministic enough for this Mac. External distribution
# still requires a Developer ID certificate and Apple notarization.
codesign --force --deep --sign - "$BUILT_APP"
codesign --verify --deep --strict --verbose=2 "$BUILT_APP"

mkdir -p "$BACKUP_ROOT"
backup_app=""
restore_previous() {
  if [[ -n "$backup_app" && ! -d "$INSTALL_APP" ]]; then
    mv "$backup_app" "$INSTALL_APP"
  fi
}
trap restore_previous ERR
if [[ -d "$INSTALL_APP" ]]; then
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup_app="$BACKUP_ROOT/$APP_NAME.$stamp"
  mv "$INSTALL_APP" "$backup_app"
fi

ditto "$BUILT_APP" "$INSTALL_APP"
trap - ERR
xattr -dr com.apple.quarantine "$INSTALL_APP" 2>/dev/null || true
"$LSREGISTER" -u "$INSTALL_APP" >/dev/null 2>&1 || true
"$LSREGISTER" -f "$INSTALL_APP" >/dev/null
codesign --verify --deep --strict --verbose=2 "$INSTALL_APP"

printf 'Installed: %s\n' "$INSTALL_APP"
printf 'Binary SHA256: '
shasum -a 256 "$INSTALL_APP/Contents/MacOS/synplex-agenthub" | awk '{print $1}'
printf 'Open with: open -a "%s"\n' "$INSTALL_APP"
