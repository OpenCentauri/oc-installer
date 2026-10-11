#!/bin/sh
# Download COSMOS firmware for the detected target into /user-resource/update_tmp.
# shellcheck disable=SC2012  # CI artifact names are fixed
set -e
target="$1"

# Target detection: device-tree model, override with C2_TARGET=cc2|c2.
detect_target() {
    [ -n "$C2_TARGET" ] && { echo "$C2_TARGET"; return; }
    model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null)
    case "$model" in
        *arbon*2*|*CC2*|*cc2*) echo cc2 ;;
        *entauri\ 2*|*C2*|*c2*) echo c2 ;;
        *) echo unknown ;;
    esac
}

case "$target" in
    cosmos)
        case "$(detect_target)" in
            cc2)
                # nightly.link: latest successful main-branch CI artifact zip
                url="https://nightly.link/OpenCentauri/cosmos/workflows/build.yml/main/centauri-carbon-2%20Firmware.zip"
                zip_out="cosmos-firmware.zip"
                # Fallback (nightly.link outage): rolling Nightly release asset
                fallback_url="https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu"
                ;;
            *)
                echo "No online COSMOS build for this target yet." >&2
                echo "Use 'Install COSMOS From USB' with a downloaded .swu instead." >&2
                exit 1 ;;
        esac
        ;;
    *)
        echo "Usage: $0 {cosmos}" >&2
        exit 1 ;;
esac

cd /user-resource/update_tmp
rm -f update.swu "$zip_out"
if curl -fL -o "$zip_out" "$url" && unzip -o "$zip_out" 2>/dev/null; then
    SWU=$(ls cosmos-*.swu 2>/dev/null | head -1)
    [ -n "$SWU" ] && mv "$SWU" update.swu
fi
if [ ! -f update.swu ]; then
    echo "nightly.link download failed, trying Nightly release asset..." >&2
    curl -fL -o update.swu "$fallback_url"
fi
[ -s update.swu ] || { echo "ERROR: download produced no SWU" >&2; exit 1; }
ls -l update.swu
