#!/bin/sh
set -e
export PATH="$PATH:/sbin:/usr/sbin"
cd "$(dirname "$0")"

# The completion button reloads only after the user has read the task output.
if [ "${1:-}" = reload ]; then
    touch .reload
    kill "$(cat .recovery.pid)"
    exit 0
fi
log_dest=${1:-}
if [ -z "$log_dest" ]; then
    for mp in /mnt/exUDISK /mnt/UDISK; do
        if mount | grep -q " on $mp "; then log_dest=$mp; break; fi
    done
fi
log_dest=${log_dest:-$PWD}
chmod a+x ./recovery ./bind-shell
for proc in app ec-eeb001-gui; do
    pids=$(pidof "$proc" 2>/dev/null) || continue
    # shellcheck disable=SC2086
    kill $pids || true
done
echo 3 > /proc/sys/vm/drop_caches || true
trap 'rm -f .recovery.pid .reload' EXIT
rm -f .reload
while :; do
    action=Install
    [ ! -f /etc/init.d/oc-shell ] || action=Remove
    sed -i "s/Install root shell/$action root shell/g; s/Remove root shell/$action root shell/g" ./config.toml
    ./recovery ./config.toml >> "$log_dest/recovery.log" 2>&1 &
    echo $! > .recovery.pid
    rc=0
    wait "$!" || rc=$?
    [ -f .reload ] || break
    rm .reload
done
dd if=/dev/zero of=/dev/fb0 2>/dev/null || true
exit "$rc"
