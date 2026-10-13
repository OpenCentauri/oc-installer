#!/bin/sh

set -e

# SWUpdate calls shellscript handlers before and after installation.
[ "${1:-preinst}" = preinst ] || exit 0

# Stop the updater from retrying while the installer owns the screen.
killall daemon-000 2>/dev/null || :
fw_setenv swu_next ""
fw_setenv parts_clean ""

dest=/opt/usr/oc-installer
rm -rf "$dest"
mkdir -p "$dest"
trap 'rm -rf "$dest"' EXIT
trap 'exit 1' HUP INT TERM

# Stock BusyBox has no base64. The build appends the tar.gz at this offset.
tail -c +@OFFSET@ "$0" | tar xz -C "$dest"
sh "$dest/run.sh"
exit 0
