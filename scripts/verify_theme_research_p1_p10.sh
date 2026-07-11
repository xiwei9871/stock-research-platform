#!/bin/sh
set -eu

REPO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "$REPO_ROOT/.venv/bin/stock-research" theme-research verify-p1-p10 "$@"

