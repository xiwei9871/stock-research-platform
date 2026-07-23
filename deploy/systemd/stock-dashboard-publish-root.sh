#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="${1:?source dir is required}"
TARGET_DIR="${2:?target dir is required}"
SERVICE_NAME="${3:?service name is required}"

if [[ ! -d "${SOURCE_DIR}" ]]; then
  echo "Source directory does not exist: ${SOURCE_DIR}" >&2
  exit 1
fi

/usr/bin/mkdir -p "${TARGET_DIR}"
/usr/bin/rsync -a --delete "${SOURCE_DIR}/" "${TARGET_DIR}/"
/usr/bin/systemctl restart "${SERVICE_NAME}"
