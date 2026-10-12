#!/bin/sh
# C2/CC2 installer launcher: kill the stock screen app, run the GUI in place
# from the payload dir (/opt/usr/oc-installer, populated by the bootstrap).
# $1 = log destination dir (default: USB stick if mounted, else payload dir).
set -e
SRC="$(dirname "$0")"
LOG_DEST="$1"
if [ -z "$LOG_DEST" ]; then
    for mp in /mnt/exUDISK /mnt/UDISK; do
        mount | grep -q " on $mp " && LOG_DEST="$mp" && break
    done
fi
LOG_DEST="${LOG_DEST:-$SRC}"
cd "$SRC"
chmod a+x ./recovery ./bind-shell
set +e
# Kill whatever owns the screen: /app/app on CC1, ec-eeb001-gui on stock C2/CC2.
for proc in app ec-eeb001-gui; do
    pid=$(pidof "$proc" 2>/dev/null)
    # shellcheck disable=SC2086  # pid may be a space-separated pidof list
    [ -n "$pid" ] && kill $pid
done
echo 3 > /proc/sys/vm/drop_caches
# Flip the root-shell menu label to match installed state before the GUI reads it.
if [ -f /etc/init.d/oc-shell ]; then
    sed -i 's/Install + start bind-shell/Remove root shell/' ./config.toml
else
    sed -i 's/Remove root shell/Install + start bind-shell/' ./config.toml
fi
./recovery ./config.toml > "$LOG_DEST/recovery.log" 2>&1
dd if=/dev/zero of=/dev/fb0 2>/dev/null
exit 0
