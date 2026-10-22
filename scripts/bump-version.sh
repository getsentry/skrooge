#!/usr/bin/env bash
set -euxo pipefail

# Craft provides the new version via CRAFT_NEW_VERSION (older versions only pass it as the last argument).
NEW_VERSION="${CRAFT_NEW_VERSION:-${2}}"

# Update the version in pyproject.toml and re-lock so uv.lock stays in sync
uv version --no-sync "${NEW_VERSION}"
