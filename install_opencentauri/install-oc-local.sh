#!/bin/sh
set -e
cd /user-resource/update_tmp

curr=$(fw_printenv boot_partition | awk -F= '{ print $2 }' | tr -d '[:space:]')
case "$curr" in
    bootA) boot_partition=now_A_next_B ;;
    bootB) boot_partition=now_B_next_A ;;
    *) exit 1 ;;
esac

for swu in /mnt/exUDISK/install_opencentauri/update.swu \
           /mnt/exUDISK/install_opencentauri/cosmos-centauri-carbon-1.swu; do
    if [ -f "$swu" ] && [ -s "$swu" ]; then
        echo "Using local firmware: $swu"
        swupdate -i "$swu" -e "stable,$boot_partition" -k /user-resource/update_tmp/swupdate_public.pem
        rm /board-resource/printer.cfg
        sync
        exit 0
    fi
done
echo "File not found: put update.swu or cosmos-centauri-carbon-1.swu in usb://install_opencentauri/"
exit 1
