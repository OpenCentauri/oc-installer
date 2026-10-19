#!/bin/sh
set -e
log=/mnt/exUDISK/OCInstaller.log
printf 'Removing /oc-installer before reboot.\n' >> "$log" || :
cd /
rm -rf /oc-installer
printf 'Installer cleanup complete; reboot requested.\n' >> "$log" || :
sync
reboot
