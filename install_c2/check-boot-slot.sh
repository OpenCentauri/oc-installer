#!/bin/sh
export PATH="$PATH:/sbin:/usr/sbin"

running=$(tr ' ' '\n' < /proc/cmdline | sed -n 's/^root=//p')
case "$running" in
    /dev/mmcblk0p7) running=A ;;
    /dev/mmcblk0p8) running=B ;;
    *) echo "ERROR: cannot determine running C2/CC2 slot from /proc/cmdline" >&2; exit 1 ;;
esac

curr=$(fw_printenv boot_partition 2>/dev/null) || curr=""
case "$curr" in
    boot_partition=bootA) curr=A ;;
    boot_partition=bootB) curr=B ;;
    "") curr=$(fw_printenv systemAB_next 2>/dev/null) || {
            echo "ERROR: cannot read boot_partition or systemAB_next" >&2; exit 1;
        }
        curr=${curr#systemAB_next=} ;;
    *) echo "ERROR: invalid boot_partition: $curr" >&2; exit 1 ;;
esac
if [ "$curr" != "$running" ]; then
    echo "ERROR: boot environment ($curr) disagrees with running slot $running; refusing to flash." >&2
    echo "Repair boot_partition to boot$running and systemAB_next to $running before retrying." >&2
    exit 1
fi
case "$running" in
    A) echo now_A_next_B ;;
    B) echo now_B_next_A ;;
esac
