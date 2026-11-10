#!/usr/bin/env bash
# Same checks as test_in_hermes_image.sh, against a local Hermes checkout and its environment, without Docker.
#
# Usage: scripts/test_in_hermes.sh HERMES_SOURCE_DIR HERMES_PYTHON
#   e.g. git clone --depth 1 --branch v0.23.0 https://github.com/NousResearch/hermes-agent /tmp/hermes-src
#        (cd /tmp/hermes-src && UV_PROJECT_ENVIRONMENT=/tmp/hermes-env uv sync --frozen --python 3.14)
#        scripts/test_in_hermes.sh /tmp/hermes-src /tmp/hermes-env/bin/python
# A throwaway HERMES_HOME is used; your own profiles are never touched.
set -euo pipefail

SRC="$1"
PY="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP_HOME="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME"' EXIT

HERMES="$(dirname "$PY")/hermes"
HERMES_HOME="$TMP_HOME" "$HERMES" plugins validate "$ROOT/tenure"
HERMES_HOME="$TMP_HOME" "$HERMES" plugins doctor "$ROOT/tenure" --ci
HERMES_AGENT_DIR="$SRC" "$PY" "$ROOT/tests/integration/run_in_hermes.py"
