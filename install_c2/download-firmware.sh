#!/bin/sh
set -e
exec 2>&1
payload=$(CDPATH='' cd -- "$(dirname "$0")" && pwd)
cd /opt/usr

url="https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu"

trap 'rm -f update.swu.part' EXIT HUP INT TERM
rm -f update.swu
# This is the official GitHub Release asset; do not route through nightly.link.
# -sS keeps curl's progress meter from fighting the GUI's task spinner but
# still prints transfer errors into the task output.
"$payload/curl" --cacert "$payload/ca-certificates.crt" -sSfL -o update.swu.part "$url"
[ -s update.swu.part ] || { echo "ERROR: download produced no SWU"; exit 1; }
mv update.swu.part update.swu
echo "Downloaded COSMOS for C2/CC2."
