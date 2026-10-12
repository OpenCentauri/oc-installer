#!/bin/sh
# Install the downloaded COSMOS SWU to the inactive slot, then clean up the
# staged file. sw_description is always the first cpio member, so a grep of
# the first blocks detects a "cosmos =" section without a cpio tool (stock
# busybox has none).
set -e
cd /opt/usr
PAYLOAD=/opt/usr/oc-installer
[ -s update.swu ] || { echo "ERROR: update.swu missing - download first" >&2; exit 1; }
slot="$(sh "$PAYLOAD/check-boot-slot.sh")"
if dd if=update.swu bs=8192 count=1 2>/dev/null | grep -q "cosmos ="; then sel="cosmos"; else sel="stable"; fi
KEY=""
swupdate -h 2>&1 | grep -q -- '-k' && [ -f "$PAYLOAD/swupdate_public_cosmos.pem" ] && KEY="-k $PAYLOAD/swupdate_public_cosmos.pem"
echo "Installing: selection=$sel,$slot"
# shellcheck disable=SC2086
swupdate -i update.swu -e "$sel,$slot" $KEY || rc=$?
rm -f update.swu
sync
if [ "${rc:-0}" -eq 0 ]; then
    echo "Install complete. Reboot when ready."
else
    echo "ERROR: swupdate failed ($rc)" >&2
    exit "$rc"
fi
