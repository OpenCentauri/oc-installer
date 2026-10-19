#!/bin/sh
set -eu
cd "$(dirname "$0")"

sh tools/build-pigz.sh
sh tools/build-curl.sh
sh tools/fetch-binaries.sh

[ -s install_opencentauri/decrypt ] || curl -fLsS -o install_opencentauri/decrypt https://github.com/OpenCentauri/OpenCentauri/releases/download/v0.0.0/decrypt
[ -s install_opencentauri/utf8-fix ] || curl -fLsS -o install_opencentauri/utf8-fix https://github.com/OpenCentauri/OpenCentauri/releases/latest/download/utf8-fix-linux-armv7
[ -s install_opencentauri/wifi-network-config-tool ] || curl -fLsS -o install_opencentauri/wifi-network-config-tool https://github.com/OpenCentauri/OpenCentauri/releases/latest/download/wifi-network-config-tool-linux-armv7

python3 tests/test_build.py
python3 -m unittest discover -s tests -p "test_*.py"
python3 tests/test_install_scripts.py

python3 tools/make_cc1.py
rm -f build/c2-tools-bootstrap.swu build/*_eeb001_*.zip.sig
python3 tools/make_swu.py
python3 tools/make_zipsig.py build/c2-tools-bootstrap.swu --out build/

python3 tests/test_build.py --post-build

ls -l build/
