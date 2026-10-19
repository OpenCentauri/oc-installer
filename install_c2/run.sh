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
mount | grep -q ' on /mnt/exUDISK ' || { echo "ERROR: USB log destination is not mounted"; exit 1; }
exec >> /mnt/exUDISK/OCInstaller.log 2>&1
printf '[%s] Starting installer GUI\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
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
    ./recovery ./config.toml &
    echo $! > .recovery.pid
    rc=0
    wait "$!" || rc=$?
    [ -f .reload ] || break
    rm .reload
done
dd if=/dev/zero of=/dev/fb0 2>/dev/null || true
exit "$rc"
