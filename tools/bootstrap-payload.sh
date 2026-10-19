#!/bin/sh

set -e

# SWUpdate calls shellscript handlers before and after installation.
[ "${1:-preinst}" = preinst ] || exit 0

mount | grep -q ' on /mnt/exUDISK ' || { echo "ERROR: USB log destination is not mounted"; exit 1; }
exec >> /mnt/exUDISK/OCInstaller.log 2>&1
printf '\n[%s] OCInstaller bootstrap\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
set -x

# Stop the updater from retrying while the installer owns the screen.
killall daemon-000 2>/dev/null || :
fw_setenv swu_next ""
fw_setenv parts_clean ""

dest=/oc-installer
rm -rf "$dest"
mkdir -p "$dest"
trap 'rm -rf "$dest"' EXIT
trap 'exit 1' HUP INT TERM

# Stock BusyBox has no base64. The build appends the tar.gz at this offset.
tail -c +@OFFSET@ "$0" | tar xz -C "$dest"
sh "$dest/run.sh"
exit 0
