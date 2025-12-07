#!/bin/sh

curr=$(fw_printenv boot_partition | awk -F= '{ print $2 }' | tr -d '[:space:]')

if [[ "$curr" == "bootA" ]]; then
    boot_partition="now_A_next_B"
elif [[ "$curr" == "bootB" ]]; then
    boot_partition="now_B_next_A"
else
    exit 1
fi

echo "$boot_partition"