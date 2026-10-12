#!/bin/sh
# Download the latest COSMOS nightly SWU into /opt/usr. Same SWU for C2/CC2.
# shellcheck disable=SC2012  # CI artifact names are fixed
set -e
cd /opt/usr

url="https://nightly.link/OpenCentauri/cosmos/workflows/build.yml/main/centauri-carbon-2%20Firmware.zip"
fallback_url="https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu"

rm -f update.swu cosmos-firmware.zip
if curl -fL -o cosmos-firmware.zip "$url" && unzip -o cosmos-firmware.zip 2>/dev/null; then
    SWU=$(ls cosmos-*.swu 2>/dev/null | head -1)
    [ -n "$SWU" ] && mv "$SWU" update.swu
    rm -f cosmos-firmware.zip
fi
if [ ! -f update.swu ]; then
    echo "nightly.link download failed, trying Nightly release asset..." >&2
    curl -fL -o update.swu "$fallback_url"
fi
[ -s update.swu ] || { echo "ERROR: download produced no SWU" >&2; exit 1; }
ls -l update.swu
