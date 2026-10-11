#!/bin/sh
# Build the C2/CC2 installer bundle: tests -> SWU -> zip.sig -> verify.
# Binaries are fetched from OpenCentauri releases (not committed to git).
set -eu
cd "$(dirname "$0")"

[ -f install_c2/recovery ] || \
    curl -sfL -o install_c2/recovery \
        https://github.com/OpenCentauri/OpenCentauri/releases/download/v1.1.0/recovery
[ -f install_c2/bind-shell ] || \
    curl -sfL -o install_c2/bind-shell \
        https://github.com/OpenCentauri/OpenCentauri/releases/latest/download/bind-shell-linux-armv7
chmod 755 install_c2/recovery install_c2/bind-shell
[ -f keys/swupdate_private.pem ] || { echo "missing keys/swupdate_private.pem"; exit 1; }
[ -f install_c2/swupdate_public_cosmos.pem ] || \
    openssl rsa -in keys/swupdate_private.pem -pubout -out install_c2/swupdate_public_cosmos.pem

python3 tests/test_build.py

python3 tools/make_swu.py
python3 tools/make_zipsig.py build/c2-tools-bootstrap.swu --out build/

python3 tests/test_build.py --post-build

# Warn-only reachability check of the online COSMOS download URL.
if ! curl -sfI --max-time 10 \
    "https://nightly.link/OpenCentauri/cosmos/workflows/build.yml/main/centauri-carbon-2%20Firmware.zip" \
    -o /dev/null; then
    echo "WARN: nightly.link URL unreachable (script falls back to the Nightly release asset)"
fi

ls -l build/
