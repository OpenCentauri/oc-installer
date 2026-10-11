#!/bin/sh
# C2/CC2 installer launcher: stage to /user-resource, kill stock app, run GUI.
# $1 = USB mountpoint for the log (default /mnt/exUDISK).
set -e
SRC="$(dirname "$0")"
LOG_DEST="${1:-/mnt/exUDISK}"
mkdir -p /user-resource/update_tmp
cp "$SRC"/*.sh "$SRC"/*.toml "$SRC"/recovery "$SRC"/bind-shell /user-resource/update_tmp/
cp "$SRC"/*.pem /user-resource/update_tmp/ 2>/dev/null || true
cd /user-resource/update_tmp
chmod a+x ./recovery ./bind-shell
set +e
pid=$(pidof app 2>/dev/null)
[ -z "$pid" ] && pid=$(pgrep -f "/app/app" 2>/dev/null)
# shellcheck disable=SC2086  # pid may be a space-separated pidof list
[ -n "$pid" ] && kill $pid
echo 3 > /proc/sys/vm/drop_caches
./recovery ./config.toml > "$LOG_DEST/recovery.log" 2>&1
dd if=/dev/zero of=/dev/fb0 2>/dev/null
exit 0
