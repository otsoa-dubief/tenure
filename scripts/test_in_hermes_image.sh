#!/usr/bin/env bash
# Checks tenure against a fresh, throwaway container of the official Hermes Agent image:
# catalog validation, plugin doctor, and the end-to-end check through Hermes' own approval gate
# (tests/integration/run_in_hermes.py).
#
# Usage: scripts/test_in_hermes_image.sh [image]     (default: nousresearch/hermes-agent:latest)
# Exit code 0 when everything passes.
set -euo pipefail

IMAGE="${1:-nousresearch/hermes-agent:latest}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NAME="tenure-test-$$"

h() { docker exec -i -u hermes -e HERMES_HOME=/opt/data "$NAME" "$@"; }

docker run -d --rm --name "$NAME" "$IMAGE" sleep infinity >/dev/null
trap 'docker rm -f "$NAME" >/dev/null 2>&1' EXIT
for _ in $(seq 1 60); do h hermes --version >/dev/null 2>&1 && break; sleep 2; done
echo "Hermes under test: $(h hermes --version | head -1)"

docker cp "$ROOT" "$NAME:/tmp/tenure"
docker exec "$NAME" sh -c 'rm -rf /tmp/tenure/.venv /tmp/tenure/.git && chown -R hermes:hermes /tmp/tenure'

h hermes plugins validate /tmp/tenure/tenure
h hermes plugins doctor /tmp/tenure/tenure --ci
h env HERMES_AGENT_DIR=/opt/hermes /opt/hermes/.venv/bin/python /tmp/tenure/tests/integration/run_in_hermes.py
