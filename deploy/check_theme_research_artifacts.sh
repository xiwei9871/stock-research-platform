#!/usr/bin/env bash
set -euo pipefail

artifact_root="${1:?artifact root is required}"
minimum_count="${2:-25}"
required_theme_id="${3:-ai_compute_infrastructure_value_chain_v1}"

if [[ "$artifact_root" != /* ]] || [[ "$artifact_root" == *".."* ]]; then
  echo "Theme Research artifact root must be a safe absolute path" >&2
  exit 2
fi
if [[ ! "$minimum_count" =~ ^[0-9]+$ ]] || (( minimum_count < 1 )); then
  echo "Theme Research minimum artifact count must be positive" >&2
  exit 2
fi
if [[ ! "$required_theme_id" =~ ^[a-z0-9_]+$ ]]; then
  echo "Theme Research required theme ID contains unsupported characters" >&2
  exit 2
fi
if [[ ! -d "$artifact_root" || ! -r "$artifact_root" || ! -x "$artifact_root" ]]; then
  echo "Theme Research artifact root is unavailable: $artifact_root" >&2
  exit 1
fi

artifact_count="$(find "$artifact_root" -maxdepth 1 -type f -name '*.json' -print | wc -l | tr -d '[:space:]')"
if (( artifact_count < minimum_count )); then
  echo "Theme Research artifact count $artifact_count is below $minimum_count" >&2
  exit 1
fi
if [[ ! -f "$artifact_root/${required_theme_id}.json" ]]; then
  echo "Theme Research required artifact is missing: ${required_theme_id}.json" >&2
  exit 1
fi

echo "Theme Research canonical artifacts valid: $artifact_count"
