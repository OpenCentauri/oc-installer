#!/bin/sh
# Build the static musl+mbedtls curl (HTTPS-only) packed into install_c2.
# Native x86_64 twin + live TLS verification were run when this recipe was
# created (see skill musl-static-autotools-build); CI rebuilds are guarded
# by the ELF/symbol checks below and cached by recipe hash.
set -eu
repo=$(CDPATH='' cd -- "$(dirname "$0")/.." && pwd)
mkdir -p "$repo/build/curl"
cd "$repo/build/curl"
root=$PWD
export LC_ALL=C
unset GZIP REALGCC CFLAGS CPPFLAGS LDFLAGS LIBRARY_PATH CPATH C_INCLUDE_PATH
cross=arm-linux-gnueabihf-
compiler=$("${cross}gcc" -dumpfullversion)
key=$(printf '%s\n%s\n' "$(sha256sum "$repo/tools/build-curl.sh")" "$compiler" | sha256sum)
if [ -x curl ] && [ -f build.key ] && [ "$(cat build.key)" = "$key" ]; then
    exit 0
fi
jobs=$(nproc 2>/dev/null || echo 2)

fetch() {
    url=$1
    hash=$2
    name=${3:-${url##*/}}
    if [ ! -f "$name" ]; then
        curl -fL --retry 3 -o "$name.part" "$url"
        printf '%s  %s\n' "$hash" "$name.part" | sha256sum -c -
        mv "$name.part" "$name"
    fi
    printf '%s  %s\n' "$hash" "$name" | sha256sum -c -
}
# curl hash verified against the release PGP signature, key fingerprint
# 27EDEAF22F3ABCEB50DB9A125CC908FDB71E12C2 (Daniel Stenberg, curl.se).
# mbedtls hash from the GitHub release page. qsort-fixed.c is musl git
# src/stdlib/qsort.c @5122f9f3c99f, the three commits fixing CVE-2026-40200
# (qsort stack corruption on 32-bit); diff-verified against 1.2.6.
fetch https://musl.libc.org/releases/musl-1.2.6.tar.gz d585fd3b613c66151fc3249e8ed44f77020cb5e6c1e635a616d3f9f82460512a
fetch https://github.com/Mbed-TLS/mbedtls/releases/download/mbedtls-3.6.7/mbedtls-3.6.7.tar.bz2 a7e8bcbec0e6f761b4af24f25677626b35f762f68eef79c08677a363212d11f6
fetch https://curl.se/download/curl-8.22.0.tar.xz f7ef3ae8a22e521f289803fe93543eb64c329b58aa73a9e224dfd915a2a5f4f7
fetch 'https://git.musl-libc.org/cgit/musl/plain/src/stdlib/qsort.c?id=5122f9f3c99fee366167c5de98b31546312921ab' c7c9e1437e55ad9ac3f24f4b0eb54fbd09f8175a21299f4d7412181b27dfa57a qsort-fixed.c

arch='-march=armv7-a -mtune=cortex-a7 -mfpu=neon-vfpv4 -mfloat-abi=hard'
cflags="-O2 -D_FILE_OFFSET_BITS=64 -ffunction-sections -fdata-sections $arch"
# See below for why make-time LDFLAGS differ.
ldflags="-static -no-pie -Wl,--gc-sections $arch -Wl,-u,__aeabi_ldiv0"

rm -rf musl-1.2.6 mbedtls-3.6.7 curl-8.22.0 prefix
tar -xzf musl-1.2.6.tar.gz
tar -xjf mbedtls-3.6.7.tar.bz2
tar -xJf curl-8.22.0.tar.xz

# CVE-2026-40200: curl's tool code links qsort; use the upstream-fixed file.
cp qsort-fixed.c musl-1.2.6/src/stdlib/qsort.c
printf '%s  %s\n' c7c9e1437e55ad9ac3f24f4b0eb54fbd09f8175a21299f4d7412181b27dfa57a \
    musl-1.2.6/src/stdlib/qsort.c | sha256sum -c -

cd "$root/musl-1.2.6"
CC="${cross}gcc" CROSS_COMPILE="$cross" CFLAGS="$cflags" ./configure \
    --target=arm-linux-musleabihf --prefix="$root/prefix" --disable-shared --enable-wrapper=gcc
make -j"$jobs"
make install
cc="$root/prefix/bin/musl-gcc"

cd "$root/mbedtls-3.6.7"
# Client-side TLS 1.2/1.3 only: drop server, DTLS and unused crypto so the
# ciphersuite table can't drag them into the link. MBEDTLS_DHM_C must stay
# (unguarded ref in ssl_tls12_client.c). gc-sections discards the rest.
for sym in MBEDTLS_SSL_SRV_C MBEDTLS_SSL_PROTO_DTLS MBEDTLS_SSL_DTLS_ANTI_REPLAY \
    MBEDTLS_SSL_DTLS_HELLO_VERIFY MBEDTLS_SSL_DTLS_SRTP MBEDTLS_SSL_DTLS_CLIENT_PORT_REUSE \
    MBEDTLS_SSL_DTLS_CONNECTION_ID MBEDTLS_SSL_CACHE_C MBEDTLS_SSL_TICKET_C \
    MBEDTLS_CAMELLIA_C MBEDTLS_ARIA_C MBEDTLS_DES_C MBEDTLS_ECJPAKE_C \
    MBEDTLS_PKCS5_C MBEDTLS_PKCS7_C MBEDTLS_PKCS12_C MBEDTLS_PEM_WRITE_C \
    MBEDTLS_PK_WRITE_C MBEDTLS_PK_PARSE_EC_EXTENDED MBEDTLS_X509_CREATE \
    MBEDTLS_X509_CRT_WRITE_C MBEDTLS_X509_CSR_PARSE_C MBEDTLS_X509_CSR_WRITE_C \
    MBEDTLS_SELF_TEST; do
    python3 scripts/config.py unset "$sym" || :
done
make -j"$jobs" -C library libmbedtls.a libmbedx509.a libmbedcrypto.a \
    CC="$cc" AR="${cross}ar" RANLIB="${cross}ranlib" CFLAGS="$cflags"
mkdir -p "$root/prefix/include" "$root/prefix/lib"
cp -r include/mbedtls include/psa "$root/prefix/include/"
cp library/libmbedtls.a library/libmbedx509.a library/libmbedcrypto.a "$root/prefix/lib/"

cd "$root/curl-8.22.0"
# HTTP+HTTPS only, TLS via mbedtls, everything else off. No CA default: the
# caller passes --cacert ca-certificates.crt (stock device has none).
# Configure-time conftest links use raw $CC $LDFLAGS (no libtool), so only
# plain -static is allowed here; every link in curl's make goes through
# libtool, which strips -static, so make-time LDFLAGS carries -all-static
# (libtool translates it back to driver -static). Without driver -static the
# ARM link dies on '__aeabi_ldiv0: undefined reference to raise' (one-pass
# archive scanning); -Wl,-u,__aeabi_ldiv0 is belt-and-braces for that.
CC="$cc" AR="${cross}ar" RANLIB="${cross}ranlib" \
    CFLAGS="$cflags" LDFLAGS="$ldflags" \
    ./configure --host=arm-linux-musleabihf --prefix=/nonexistent \
    --disable-shared --enable-static --with-mbedtls="$root/prefix" \
    --without-gnutls --without-wolfssl --without-rustls --without-amissl \
    --without-zlib --without-brotli --without-zstd \
    --without-nghttp2 --without-nghttp3 --without-libidn2 \
    --without-libssh2 --without-libssh --without-libpsl --without-libgsasl \
    --without-gssapi --without-libuv --without-ca-bundle --without-ca-path \
    --disable-ares --disable-ldap --disable-ldaps \
    --disable-rtsp --disable-dict --disable-telnet --disable-tftp \
    --disable-pop3 --disable-imap --disable-smb --disable-smtp \
    --disable-gopher --disable-mqtt --disable-websockets --disable-ipfs \
    --disable-file --disable-ftp \
    --disable-cookies --disable-aws --disable-alt-svc --disable-hsts \
    --disable-netrc --disable-unix-sockets --disable-manual --disable-docs
make -j"$jobs" LDFLAGS="-all-static $ldflags"

# musl 1.2.6 iconv has an upstream advisory and must stay unlinked (curl only
# pulls iconv via libidn2, which is disabled). Check the UNstripped binary.
case $("${cross}nm" --defined-only src/curl) in
    *' iconv'*|*' __iconv'*) exit 1 ;;
esac
"${cross}strip" --strip-all -o "$root/curl" src/curl
elf=$("${cross}readelf" -h -l -d -A "$root/curl")
case "$elf" in *INTERP*|*NEEDED*|*DYNAMIC*) exit 1 ;; esac
for required in 'Machine:                           ARM' 'Version5 EABI' 'hard-float ABI' \
    'Tag_CPU_arch: v7' 'Tag_ABI_VFP_args: VFP registers'; do
    case "$elf" in *"$required"*) ;; *) exit 1 ;; esac
done
printf '%s\n' "$key" > "$root/build.key"
