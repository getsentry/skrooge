#!/usr/bin/env bash
set -euxo pipefail

# Add backup and cleanup after for compatibility on MacOS and Linux
sed -i.bak "s/^version =.*/version = \"${2}\"/" pyproject.toml && rm pyproject.toml.bak
