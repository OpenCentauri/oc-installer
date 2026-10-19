#!/bin/sh
set -e
for mp in /mnt/exUDISK /mnt/UDISK; do
    for swu in "$mp/update.swu" "$mp/cosmos-centauri-carbon-2.swu" "$mp/install_c2/update.swu"; do
        if [ -f "$swu" ] && [ -s "$swu" ]; then
            echo "Using local firmware: $swu"
            exec sh "$(dirname "$0")/install-cosmos.sh" "$swu"
        fi
    done
done
echo "File not found: put update.swu or cosmos-centauri-carbon-2.swu in the USB root."
echo "The old install_c2/update.swu location is also accepted."
exit 1
