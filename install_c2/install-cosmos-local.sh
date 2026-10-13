#!/bin/sh
set -e
for mp in /mnt/exUDISK /mnt/UDISK; do
    if [ -s "$mp/install_c2/update.swu" ]; then
        exec sh "$(dirname "$0")/install-cosmos.sh" "$mp/install_c2/update.swu"
    fi
done
echo "File not found: usb://install_c2/update.swu"
echo "Copy a COSMOS .swu for C2/CC2 onto the stick first."
exit 1
