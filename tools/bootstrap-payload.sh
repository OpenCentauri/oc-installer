#!/bin/sh
# Self-extracting C2/CC2 installer bootstrap. Raw tar.gz payload appended at
# the byte offset in the tail line (stock busybox has no base64/cpio).
# Extracts to /opt/usr/oc-installer, runs the GUI, cleans up on exit
# (the stock updater reboots right after this script returns).
set +e
DESTDIR=/opt/usr/oc-installer
rm -rf "$DESTDIR"
mkdir -p "$DESTDIR"
tail -c +@OFFSET@ "$0" | tar xz -C "$DESTDIR"
echo "oc-installer bootstrap: extracted to $DESTDIR" > /dev/kmsg 2>/dev/null

# The stock OTA daemon blocks on swupdate (which blocks on our GUI) and can
# time out / retry mid-session. Kill it; our Exit & Reboot covers the reboot
# it would have done. Clear the update state it armed for this no-flash
# bundle so the next boot/update cycle starts clean.
# shellcheck disable=SC2046  # pidof list should word-split
kill $(pidof daemon-000 2>/dev/null) 2>/dev/null
fw_setenv swu_next "" 2>/dev/null
fw_setenv parts_clean "" 2>/dev/null

[ -f "$DESTDIR/run.sh" ] && sh "$DESTDIR/run.sh"
rm -rf "$DESTDIR"
echo "oc-installer bootstrap: GUI exited, cleaned up, returning to updater" > /dev/kmsg 2>/dev/null
exit 0
