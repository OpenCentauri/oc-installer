#!/bin/sh

set -e

cd /user-resource/update_tmp
curl -k -o update.swu -L https://github.com/OpenCentauri/cosmos/releases/latest/download/update.swu
