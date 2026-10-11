#!/bin/sh
# Bootstrap: stage installer from USB, launch GUI, block until it exits.
set +e
DEST=""
for mp in /mnt/exUDISK /mnt/UDISK; do
    if mount | grep -q " on $mp "; then DEST="$mp"; break; fi
done
if [ -z "$DEST" ]; then
    mkdir -p /mnt/exUDISK
    for dev in /dev/sda1 /dev/sda; do
        [ -b "$dev" ] && mount "$dev" /mnt/exUDISK 2>/dev/null && DEST=/mnt/exUDISK && break
    done
fi
echo "oc-installer bootstrap: usb=$DEST" > /dev/console
[ -n "$DEST" ] && [ -d "$DEST/install_c2" ] && sh "$DEST/install_c2/run.sh" "$DEST"
echo "oc-installer bootstrap: GUI exited, returning to updater" > /dev/console
exit 0
