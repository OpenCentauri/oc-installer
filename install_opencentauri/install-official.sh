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

set -e

swupdate -i /user-resource/update_tmp/update.swu -e stable,${boot_partition} -k /user-resource/update_tmp/swupdate_public_elegoo.pem
rm /board-resource/printer.cfg
sync