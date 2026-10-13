#!/bin/sh
set -eu
cd "$(dirname "$0")"

sh tools/build-pigz.sh

python3 tests/test_build.py
python3 -m unittest discover -s tests -p "test_*.py"
python3 tests/test_install_scripts.py

python3 tools/make_swu.py
python3 tools/make_zipsig.py build/c2-tools-bootstrap.swu --out build/

python3 tests/test_build.py --post-build

ls -l build/
