#!/bin/bash

set -e

export STATUSOPENVPN_SILENT=1
UPDATE_LOCK="/tmp/statusopenvpn-update.lock"

cleanup() {
    rm -f "$UPDATE_LOCK"
}

trap cleanup EXIT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -n "${1:-}" ]]; then
    export STATUSOPENVPN_UPDATE_TAG="$1"
fi

bash "$SCRIPT_DIR/setup.sh"
