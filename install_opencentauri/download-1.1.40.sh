#!/bin/sh

set -e

cd /user-resource/update_tmp
curl -k -o update.bin -L https://s3.devminer.xyz/archive/ELEGOO_Centauri_Update_1.1.40.bin
