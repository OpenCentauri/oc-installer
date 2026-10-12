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
cd "$(dirname "$0")"
slot="$(sh ./check-boot-slot.sh)"
if dd if="$SWU" bs=8192 count=1 2>/dev/null | grep -q "cosmos ="; then sel="cosmos"; else sel="stable"; fi
KEY=""
swupdate -h 2>&1 | grep -q -- '-k' && [ -f swupdate_public_cosmos.pem ] && KEY="-k swupdate_public_cosmos.pem"
echo "Installing: selection=$sel,$slot from USB"
# shellcheck disable=SC2086
swupdate -i "$SWU" -e "$sel,$slot" $KEY
sync
echo "Install complete. Reboot when ready."
