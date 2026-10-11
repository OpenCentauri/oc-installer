#!/bin/sh
# Install COSMOS from a user-supplied SWU on the USB stick.
set -e
SWU=""
for mp in /mnt/exUDISK /mnt/UDISK; do
    [ -f "$mp/install_c2/update.swu" ] && SWU="$mp/install_c2/update.swu" && break
done
if [ -z "$SWU" ]; then
    echo "File not found: usb://install_c2/update.swu" >&2
    echo "Copy a COSMOS .swu for this machine onto the stick first." >&2
    exit 1
fi
cd /user-resource/update_tmp
slot="$(sh ./check-boot-slot.sh)"
# Probe for "cosmos =" section; degrades to "stable" if cpio is missing
# (correct for stock SWUs; Cosmos rootfs ships cpio).
cpio -i -F "$SWU" sw-description --to-stdout 2>/dev/null > /tmp/swd.txt || true
if grep -qs "cosmos =" /tmp/swd.txt; then sel="cosmos"; else sel="stable"; fi
KEY=""
swupdate -h 2>&1 | grep -q -- '-k' && [ -f swupdate_public_cosmos.pem ] && KEY="-k swupdate_public_cosmos.pem"
echo "Installing: selection=$sel,$slot from USB"
# shellcheck disable=SC2086
swupdate -i "$SWU" -e "$sel,$slot" $KEY
sync
echo "Install complete. Reboot when ready."
