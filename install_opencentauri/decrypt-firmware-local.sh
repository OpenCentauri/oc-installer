#!/bin/sh

if [[ ! -f "/mnt/exUDISK/update.bin" ]]; then
    echo "usb:/update.bin does not exist!"
fi

set -e
cd /user-resource/update_tmp
./decrypt /mnt/exUDISK/update.bin update.swu