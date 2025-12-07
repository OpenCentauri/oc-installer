#!/bin/sh

set -e

cd /user-resource/update_tmp
curl -k -o update.bin -L https://download.chitubox.com/chitusystems/chitusystems/public/printer/firmware/release/1/ca8e1d9a20974a5896f8f744e780a8a7/1/01.01.46/2025-10-22/f9bd2b9b1926408ca238de8e7eac69b6.bin
