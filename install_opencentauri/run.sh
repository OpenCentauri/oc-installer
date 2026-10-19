#!/bin/sh
set -e
export PATH="$PATH:/sbin:/usr/sbin"

if [ "${1:-}" = reload ]; then
    cd /user-resource/update_tmp
    touch .reload
    kill "$(cat .recovery.pid)"
    exit 0
fi
mount | grep -q ' on /mnt/exUDISK ' || { echo "ERROR: USB log destination is not mounted"; exit 1; }
exec >> /mnt/exUDISK/OCInstaller.log 2>&1
printf '[%s] Starting CC1 installer GUI\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"

rm -f "/user-resource/IMPORT_ME_DO_NOT_PRINT______________________'\$(sh \$(printf %.1smnt%.1sexUDISK%.1sinstall_opencentauri%.1srun.sh \$PWD \$PWD \$PWD \$PWD))'.gcode"

mkdir -p /user-resource/update_tmp
cd /mnt/exUDISK/install_opencentauri

cp ./*.sh /user-resource/update_tmp
cp ./*.toml /user-resource/update_tmp
cp ./recovery /user-resource/update_tmp
cp ./decrypt /user-resource/update_tmp
cp ./utf8-fix /user-resource/update_tmp
cp ./wifi-network-config-tool /user-resource/update_tmp
cp ./bind-shell ./pigz /user-resource/update_tmp
cd /user-resource/update_tmp

printf '%b' "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvkLL7VK9svGKBM4Q39uB\nZNkkxy6zqQeCInOE3PeIhvRa3teowz7MLiYJi+CI/4q6mPysLCo3lfY+cWFCc+U3\n2lhhHJZy2+gEoTt0ecEWKIznd1GNaUMJFzHIHPCc4LssZFQ9ahZPPuoU/wYtguxA\nqPSWsH+SNe8xihy5WRG4363FdvwBQc+Q7DTE7firafCzjfaPuoSClDQsyTcGByxs\n78s23DXbvQ8jLLlVffLMFD4y9KNbuEdyswe9QEUQar+XEwFm7EkVTX+TAHzHn40s\nhW+mpfZZgMxJ6a88A527e7DfBlAnt1ZSIh4xXZMlniv40kdXyqSWO/wqJcbmnUTn\ncQIDAQAB\n-----END PUBLIC KEY-----\n" > swupdate_public.pem
printf '%b' "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAnFBZ/+BuRCESalxGqlEE\nhe3eRigUHAZZdW1nPEQZT/6V1gARirJMzT+KUFKqMgtaQuZTtizB3Uo+PbXXwkEl\nMaGUwRYHOY5ebTt+DfBBWEXvvklKIoKypWF6ta6B37PyHJz4ssnCcCtQRroOllXm\nvrYLjt5tinKJUx3XoO6iLYf2R5r6+8FB3J/i1ZhJuwCBDtIsivyxdQSHsH9pX55V\nMOsWKKyuOVyixL42hwiMxOL8HkmumLVDLeXsl0gp34JRN9tR80H5W5+8TUUXnKst\nvjf+YfzbKCIvvLl3qjDDZW9AlwrWE1mhfxFA/N2qjDQ2rsoquLPiLm3CDVBlKCUP\nfwIDAQAB\n-----END PUBLIC KEY-----\n" > swupdate_public_elegoo.pem

chmod a+x ./recovery ./decrypt ./wifi-network-config-tool ./utf8-fix ./bind-shell ./pigz

pids=$(pidof app 2>/dev/null) || pids=""
if [ -n "$pids" ]; then
    # shellcheck disable=SC2086
    kill $pids || true
fi
echo 3 > /proc/sys/vm/drop_caches || true
# shellcheck disable=SC3045
ulimit -c unlimited
trap 'rm -f .recovery.pid .reload' EXIT
rm -f .reload
while :; do
    action=Install
    [ ! -f /etc/init.d/oc-shell ] || action=Remove
    sed -i "s/Install root shell/$action root shell/g; s/Remove root shell/$action root shell/g" ./config.toml
    ./recovery ./config.toml &
    echo $! > .recovery.pid
    rc=0
    wait "$!" || rc=$?
    [ -f .reload ] || break
    rm .reload
done

dd if=/dev/zero of=/dev/fb0 2>/dev/null || true
exit "$rc"
