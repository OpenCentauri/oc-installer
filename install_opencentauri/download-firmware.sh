#!/bin/sh

set -e

target="$1"

case "$target" in
    patched)
        output_file="update.swu"
        url="https://github.com/OpenCentauri/cc-fw-tools/releases/latest/download/update.swu"
        ;;
    cosmos)
        output_file="update.swu"
        url="https://github.com/OpenCentauri/cosmos/releases/latest/download/update.swu"
        ;;
    1.4.46)
        output_file="update.bin"
        url="https://download.chitubox.com/chitusystems/chitusystems/public/printer/firmware/release/1/ca8e1d9a20974a5896f8f744e780a8a7/1/1.4.46/2026-05-08/104101205ee740a68a3bc049f0b03c70.bin"
        ;;
    1.1.46)
        output_file="update.bin"
        url="https://download.chitubox.com/chitusystems/chitusystems/public/printer/firmware/release/1/ca8e1d9a20974a5896f8f744e780a8a7/1/01.01.46/2025-10-22/f9bd2b9b1926408ca238de8e7eac69b6.bin"
        ;;
    1.1.40)
        output_file="update.bin"
        url="https://s3.devminer.xyz/archive/ELEGOO_Centauri_Update_1.1.40.bin"
        ;;
    1.1.25)
        output_file="update.bin"
        url="https://download.chitubox.com/chitusystems/chitusystems/public/printer/firmware/release/1/ca8e1d9a20974a5896f8f744e780a8a7/1/1.1.25/2025-05-09/219b4c9e67de4a1d99c7680164911ab5.bin"
        ;;
    *)
        echo "Usage: $0 {patched|cosmos|1.4.46|1.1.46|1.1.40|1.1.25}" >&2
        exit 1
        ;;
esac

cd /user-resource/update_tmp
curl -k -o "$output_file" -L "$url"