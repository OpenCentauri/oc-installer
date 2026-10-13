#!/bin/sh

set -eu
repo=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$repo/build/pigz"
cd "$repo/build/pigz"
root=$PWD
export LC_ALL=C
unset GZIP PIGZ REALGCC CFLAGS CPPFLAGS LDFLAGS LIBRARY_PATH CPATH C_INCLUDE_PATH
cross=arm-linux-gnueabihf-
compiler=$("${cross}gcc" -dumpfullversion)
key=$(printf '%s\n%s\n' "$(sha256sum "$repo/tools/build-pigz.sh")" "$compiler" | sha256sum)
if [ -x pigz ] && [ -f build.key ] && [ "$(cat build.key)" = "$key" ]; then
    exit 0
fi

fetch() {
    url=$1
    hash=$2
    name=${url##*/}
    if [ ! -f "$name" ]; then
        curl -fL --retry 3 -o "$name.part" "$url"
        printf '%s  %s\n' "$hash" "$name.part" | sha256sum -c -
        mv "$name.part" "$name"
    fi
    printf '%s  %s\n' "$hash" "$name" | sha256sum -c -
    tar -xzf "$name"
}

fetch https://musl.libc.org/releases/musl-1.2.6.tar.gz d585fd3b613c66151fc3249e8ed44f77020cb5e6c1e635a616d3f9f82460512a
fetch https://zlib.net/zlib-1.3.2.tar.gz bb329a0a2cd0274d05519d61c667c062e06990d72e125ee2dfa8de64f0119d16
fetch https://zlib.net/pigz/pigz-2.8.tar.gz eb872b4f0e1f0ebe59c9f7bd8c506c4204893ba6a8492de31df416f0d5170fd0

arch='-march=armv7-a -mtune=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard'
cflags="-O3 -D_FILE_OFFSET_BITS=64 -ffunction-sections -fdata-sections $arch"
cd "$root/musl-1.2.6"
make distclean
CC="${cross}gcc" CROSS_COMPILE="$cross" CFLAGS="$cflags" ./configure \
    --target=arm-linux-musleabihf --prefix="$root/musl" --disable-shared --enable-wrapper=gcc
make -j2
make install
cc="$root/musl/bin/musl-gcc"

cd "$root/zlib-1.3.2"
make distclean
# Configure probes must also be static when using the static-only musl wrapper.
CC="$cc" AR="${cross}ar" RANLIB="${cross}ranlib" CFLAGS="$cflags" \
    LDFLAGS="-static -no-pie $arch" ./configure --static
make -j2 libz.a
cd "$root/pigz-2.8"
make clean
make -j2 pigz ZOP= CC="$cc" CFLAGS="$cflags -pthread -DNOZOPFLI -I$root/zlib-1.3.2" \
    LDFLAGS="-static -no-pie -Wl,--gc-sections $arch" LIBS="$root/zlib-1.3.2/libz.a -pthread -lm"
# These musl routines have security advisories and must not be linked here.
symbols=$("${cross}nm" --defined-only pigz)
case "$symbols" in *' qsort'*|*' __qsort'*|*' iconv'*|*' __iconv'*) exit 1 ;; esac
"${cross}strip" -o "$root/pigz" pigz
printf '%s\n' "$key" > "$root/build.key"
