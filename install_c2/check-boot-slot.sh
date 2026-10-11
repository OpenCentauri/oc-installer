#!/bin/sh
# Print the SWUpdate selection suffix for the *other* slot.
# Stock CC2/C2: boot_partition=bootA|bootB. Cosmos mainline: systemAB_next=A|B.
curr=$(fw_printenv boot_partition 2>/dev/null | awk -F= '{print $2}' | tr -d '[:space:]')
case "$curr" in
    bootA) echo "now_A_next_B"; exit 0 ;;
    bootB) echo "now_B_next_A"; exit 0 ;;
esac
curr=$(fw_printenv systemAB_next 2>/dev/null | awk -F= '{print $2}' | tr -d '[:space:]')
case "$curr" in
    A) echo "now_A_next_B"; exit 0 ;;
    B) echo "now_B_next_A"; exit 0 ;;
esac
echo "ERROR: cannot determine boot slot (boot_partition/systemAB_next unreadable)" >&2
exit 1
