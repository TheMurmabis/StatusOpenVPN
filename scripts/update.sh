#!/bin/bash

set -e

export STATUSOPENVPN_SILENT=1
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
UPDATE_LOCK="/tmp/statusopenvpn-update.lock"

cleanup() {
    rm -f "$UPDATE_LOCK"
}

trap cleanup EXIT

SCRIPT_DIR="/root/web/scripts"

if [[ -n "${1:-}" ]]; then
    export STATUSOPENVPN_UPDATE_TAG="$1"
fi

bash "$SCRIPT_DIR/setup.sh"
