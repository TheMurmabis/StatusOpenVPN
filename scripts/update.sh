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
SCRIPT_PATH="$SCRIPT_DIR/setup.sh"

if [[ -n "${1:-}" ]]; then
    export STATUSOPENVPN_UPDATE_TAG="$1"
fi

curl -sSL https://raw.githubusercontent.com/TheMurmabis/StatusOpenVPN/main/scripts/setup.sh -o "$SCRIPT_PATH"
bash "$SCRIPT_PATH"
