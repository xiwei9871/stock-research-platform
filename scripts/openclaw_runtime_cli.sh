#!/usr/bin/env bash
set -euo pipefail

NODE_BIN="/Users/xiwei/.local/node-v24.14.1-darwin-arm64/bin/node"
OPENCLAW_ENTRY="/Users/xiwei/.local/npm/lib/node_modules/openclaw/dist/index.js"

exec "$NODE_BIN" "$OPENCLAW_ENTRY" "$@"
