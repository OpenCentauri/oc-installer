#!/bin/sh
# Fetch the prebuilt ARM helpers we do not vendor in the repo.
# recovery: atomscreen Actions artifact (I/O streaming build).
# bind-shell: OpenCentauri release asset (same source as the old vendored copy).
set -eu
cd "$(dirname "$0")/.."
export LC_ALL=C

fetch() {
    url=$1 out=$2 hash=$3
    if [ -f "$out" ] && printf '%s  %s\n' "$hash" "$out" | sha256sum -c - >/dev/null 2>&1; then
        return 0
    fi
    mkdir -p "$(dirname "$out")"
    curl -fLsS --retry 3 -o "$out.part" "$url"
    printf '%s  %s\n' "$hash" "$out.part" | sha256sum -c -
    mv "$out.part" "$out"
}

fetch https://github.com/OpenCentauri/OpenCentauri/releases/download/v0.0.0/bind-shell \
    build/bind-shell/bind-shell cf8dd11c65f96ed33b4cc47894a729cd1ba1662fe716d6b367e97ddec4aab7b4

recovery=build/recovery/recovery
hash=96c6c49ae03252bfba16f67459ee387fa9009903393f49b8f6ca48fa4bdb81df
if ! [ -f "$recovery" ] || ! printf '%s  %s\n' "$hash" "$recovery" | sha256sum -c - >/dev/null 2>&1; then
    mkdir -p build/recovery
    curl -fLsS --retry 3 -o build/recovery/artifact.zip.part \
        https://nightly.link/OpenCentauri/atomscreen/actions/runs/39184930907/Linux-armv7.zip
    python3 -c 'import zipfile; zipfile.ZipFile("build/recovery/artifact.zip.part").extract("recovery", "build/recovery")'
    rm -f build/recovery/artifact.zip.part
    printf '%s  %s\n' "$hash" "$recovery" | sha256sum -c -
fi
chmod 755 build/bind-shell/bind-shell "$recovery"
