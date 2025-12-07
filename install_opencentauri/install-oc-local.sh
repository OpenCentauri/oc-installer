#!/bin/sh

cd /user-resource/update_tmp

curr=$(fw_printenv boot_partition | awk -F= '{ print $2 }' | tr -d '[:space:]')

if [[ "$curr" == "bootA" ]]; then
    boot_partition="now_A_next_B"
elif [[ "$curr" == "bootB" ]]; then
    boot_partition="now_B_next_A"
else
    exit 1
fi

if [[ -f /mnt/exUDISK/install_opencentauri/update.swu ]]; then
    set -e
    swupdate -i /mnt/exUDISK/install_opencentauri/update.swu -e stable,${boot_partition} -k /user-resource/update_tmp/swupdate_public.pem
    rm /board-resource/printer.cfg
    sync
else
    echo -e "File does not exist.\nEnsure that usb://install_opencentauri/update.swu exists."
    exit 1
fi
