#!/bin/sh
# Keep task output live in the GUI and persist it on the USB stick.
cd "$(dirname "$0")" || exit 1
log=/mnt/exUDISK/OCInstaller.log
mount | grep -q ' on /mnt/exUDISK ' || { echo "ERROR: USB log destination is not mounted"; exit 1; }
printf '\n[%s] START %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >> "$log" || exit 1

# POSIX sh has no pipefail. Keep the command status separately from tee's.
status=$(mktemp /mnt/exUDISK/.oc-installer-task-status-XXXXXX) || exit 1
trap 'rm -f "$status"' EXIT
trap 'exit 1' HUP INT TERM
{
    "$@" 2>&1
    printf '%s\n' "$?" > "$status"
} | tee -a "$log"
tee_rc=$?
rc=$(cat "$status") || rc=1
case "$rc" in ''|*[!0-9]*) rc=1 ;; esac
[ "$tee_rc" -eq 0 ] || rc=$tee_rc
printf '[%s] EXIT %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$rc" >> "$log" || exit 1
exit "$rc"
