#!/bin/sh
set -e
exec 2>&1
export PATH="$PATH:/sbin:/usr/sbin"
cd "$(dirname "$0")"

swu=${1:-/opt/usr/update.swu}
# Only the downloaded copy belongs to us; never delete the USB original.
if [ "$#" -eq 0 ]; then
    trap 'rm -f "$swu"' EXIT
fi
trap 'exit 1' HUP INT TERM
[ -s "$swu" ] || { echo "ERROR: update.swu missing - download or copy it first"; exit 1; }
slot=$(sh ./check-boot-slot.sh)
# sw-description is first in the archive; stock BusyBox has no cpio.
if ! dd if="$swu" bs=8192 count=1 2>/dev/null | grep -aq 'elegoo-centauri-carbon2'; then
    echo "ERROR: not a C2/CC2 COSMOS SWU."
    exit 1
fi
sel=stable
if dd if="$swu" bs=8192 count=1 2>/dev/null | grep -aq 'cosmos[[:space:]]*='; then
    sel=cosmos
fi
set -- -i "$swu" -e "$sel,$slot"
if swupdate -h 2>&1 | grep -q -- '-k'; then
    set -- "$@" -k ./swupdate_public_cosmos.pem
fi
echo "Installing: selection=$sel,$slot"
swupdate "$@" || { rc=$?; echo "ERROR: swupdate failed ($rc); do not reboot."; exit "$rc"; }
sync
echo "Install complete. Reboot when ready."
