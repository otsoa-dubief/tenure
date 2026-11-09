#!/usr/bin/env bash
# Prepares the throwaway demo area: /tmp/acme/.hermes (plugin only) and /tmp/acme/shop (+ bare remote).
# Never touches ~/.hermes. Never overwrites or reads config.yaml / auth files in /tmp/acme/.hermes:
# the owner logs in there himself. Usage: setup.sh [--dry-run]
set -euo pipefail

case "${1:-}" in ""|--dry-run) ;; *) echo "usage: setup.sh [--dry-run]" >&2; exit 2;; esac
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
ROOT=/tmp/acme
HH=$ROOT/.hermes
SHOP=$ROOT/shop
REMOTE=$ROOT/remote.git
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="$(cd "$HERE/../.." && pwd)/clearance"
HERMES="${HERMES_BIN:-hermes}"

[ -d "$SRC" ] || { echo "plugin source not found: $SRC" >&2; exit 1; }
case "$HH" in "$HOME/.hermes"*) echo "refusing: $HH is inside ~/.hermes" >&2; exit 1;; esac

run() { if [ "$DRY" = 1 ]; then echo "  would run: $*"; else "$@"; fi; }
say() { echo "== $*"; }

say "plan ($([ "$DRY" = 1 ] && echo dry-run || echo real))"
echo "  HERMES_HOME     $HH   (config.yaml and auth files are never read or overwritten)"
echo "  plugin source   $SRC (local working copy, no network)"
echo "  demo project    $SHOP  remote $REMOTE"

say "HERMES_HOME"
run mkdir -p "$HH/plugins"
if [ -e "$HH/config.yaml" ]; then echo "  config.yaml exists: left as is (settings go through 'hermes config set' only)"
else echo "  no config.yaml yet: the owner logs in with his own subscription (hermes setup / hermes login)"; fi

say "plugin"
# copy to a temp name inside plugins/, then swap it in; only a real directory under plugins/ is ever removed
TMP="$HH/plugins/.clearance.new"
run rm -rf "$TMP"
run cp -R "$SRC" "$TMP"
if [ -d "$HH/plugins/clearance" ] && [ ! -L "$HH/plugins/clearance" ]; then
  echo "  replacing the previous copy of the plugin directory only"
  run rm -rf "$HH/plugins/clearance"
elif [ -L "$HH/plugins/clearance" ]; then echo "refusing: $HH/plugins/clearance is a symlink" >&2; exit 1; fi
run mv "$TMP" "$HH/plugins/clearance"
run env HERMES_HOME="$HH" "$HERMES" plugins enable clearance
echo "  settings stay at their defaults (no config edit); change one with:"
echo "    HERMES_HOME=$HH $HERMES config set plugins.clearance.<key> <value>"

say "demo project"
if [ -d "$SHOP/.git" ]; then echo "  $SHOP already exists: kept"; else
  run mkdir -p "$SHOP"
  if [ "$DRY" = 1 ]; then echo "  would write shop.py, test_shop.py, README.md, commit, add origin $REMOTE, push main"; else
    cat > "$SHOP/shop.py" <<'PY'
"""Tiny shop helpers."""


def total(prices):
    return sum(prices)


def discount(price, percent):
    return price - percent
PY
    cat > "$SHOP/test_shop.py" <<'PY'
from shop import total, discount


def test_total():
    assert total([1, 2, 3]) == 6


def test_discount():
    assert discount(200, 10) == 180  # 10 % off
PY
    printf '# acme shop\n\nA small project for the clearance demo.\n' > "$SHOP/README.md"
    git init -q -b main "$SHOP"
    git -C "$SHOP" -c user.name=Acme -c user.email=dev@acme.test add -A
    git -C "$SHOP" -c user.name=Acme -c user.email=dev@acme.test commit -q -m "Initial shop"
  fi
fi
if [ -d "$REMOTE" ]; then echo "  $REMOTE already exists: kept"; else run git init -q --bare -b main "$REMOTE"; fi
if [ "$DRY" = 1 ]; then echo "  would make sure origin is $REMOTE and push main"; else
  git -C "$SHOP" remote get-url origin >/dev/null 2>&1 || git -C "$SHOP" remote add origin "$REMOTE"
  git -C "$SHOP" push -q -u origin main
fi

say "next"
echo "  1. Owner logs in:  HERMES_HOME=$HH $HERMES setup   (his own subscription)"
echo "  2. Record:         python scripts/demo/record.py /tmp/acme/demo.cast --cmd 'cd $SHOP && HERMES_HOME=$HH $HERMES'"
