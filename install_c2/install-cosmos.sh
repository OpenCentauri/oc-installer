#!/bin/sh
# Install the downloaded COSMOS SWU to the inactive slot.
set -e
cd /user-resource/update_tmp
[ -s update.swu ] || { echo "ERROR: update.swu missing - download first" >&2; exit 1; }
slot="$(sh ./check-boot-slot.sh)"
# Probe the SWU for a "cosmos =" machine section. If cpio is unavailable on
# this busybox build the probe silently degrades to "stable" - correct for
# stock SWUs; Cosmos rootfs ships cpio so the probe works where it matters.
cpio -i -F update.swu sw-description --to-stdout 2>/dev/null > /tmp/swd.txt || true
if grep -qs "cosmos =" /tmp/swd.txt; then sel="cosmos"; else sel="stable"; fi
KEY=""
swupdate -h 2>&1 | grep -q -- '-k' && [ -f swupdate_public_cosmos.pem ] && KEY="-k swupdate_public_cosmos.pem"
echo "Installing: selection=$sel,$slot"
# shellcheck disable=SC2086
swupdate -i update.swu -e "$sel,$slot" $KEY
sync
echo "Install complete. Reboot when ready."
