#!/bin/sh

set -e

cd /user-resource/update_tmp
curl -k -o update.swu -L https://github.com/OpenCentauri/cc-fw-tools/releases/latest/download/update.swu
