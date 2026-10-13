#!/bin/sh
set -e
exec 2>&1
cd /opt/usr

url="https://nightly.link/OpenCentauri/cosmos/workflows/build.yml/main/centauri-carbon-2%20Firmware.zip"
fallback_url="https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu"

trap 'rm -f cosmos-firmware.zip update.swu.part' EXIT
trap 'exit 1' HUP INT TERM
rm -f update.swu
if ! { curl -fL -o cosmos-firmware.zip "$url" &&
       unzip -p cosmos-firmware.zip cosmos-centauri-carbon-2.swu > update.swu.part &&
       [ -s update.swu.part ]; }; then
    echo "nightly.link download failed, trying Nightly release asset..."
    curl -fL -o update.swu.part "$fallback_url"
fi
[ -s update.swu.part ] || { echo "ERROR: download produced no SWU"; exit 1; }
mv update.swu.part update.swu
echo "Downloaded COSMOS for C2/CC2."
