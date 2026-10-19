#!/bin/sh
set -e
exec 2>&1
export PATH="$PATH:/sbin:/usr/sbin"
init=/etc/init.d/oc-shell
save=${1:-/opt/usr/oc-root-shell}
case "$save" in
    /opt/usr/oc-root-shell|/user-resource/oc-root-shell) ;;
    *) echo "ERROR: unsupported root shell location"; exit 1 ;;
esac

if [ ! -f "$init" ]; then
    # 11D7 is port 4567; 0A is TCP_LISTEN. Check IPv4 and IPv6 tables.
    listening=$(awk '$2 ~ /:11D7$/ && $4 == "0A" { busy=1 } END { print busy+0 }' /proc/net/tcp*) || {
        echo "ERROR: cannot check root shell port"; exit 1
    }
    if [ "$listening" -ne 0 ]; then
        echo "ERROR: Root shell already installed/running"; exit 1
    fi
fi

# Remove the old autostart paths so they cannot resurrect a disabled shell.
rm -f /etc/hotplug.d/block/12-shell /app/bind-shell
if [ -f /etc/rc.local ]; then
    sed -i '/# BEGIN oc-installer bind-shell/,/# END oc-installer bind-shell/d' /etc/rc.local
fi
if [ -f "$init" ]; then
    "$init" stop || true
    if pidof bind-shell >/dev/null 2>&1; then
        echo "ERROR: root shell did not stop"
        exit 1
    fi
    rm -f "$init" /etc/rc.d/S98oc-shell /etc/rc.d/K98oc-shell /opt/bin/bind-shell
    rm -rf "$save"
    echo "Root shell removed. Reload the menu to update its label."
    exit 0
fi

mkdir -p "$save"
cp "$(dirname "$0")/bind-shell" "$save/bind-shell"
# /opt/usr survives OTA, but mounts too late for rc.d; run the rootfs copy.
cat > "$save/oc-shell" <<'EOF'
#!/bin/sh /etc/rc.common
# shellcheck disable=SC2034
START=98
# shellcheck disable=SC2034
STOP=98

start() {
    pidof bind-shell >/dev/null 2>&1 && return 0
    [ -x /opt/bin/bind-shell ] || return 1
    /opt/bin/bind-shell 4567 </dev/null >/dev/null 2>&1 &
    sleep 1
    pidof bind-shell >/dev/null 2>&1
}

stop() {
    pids=$(pidof bind-shell) || return 0
    # shellcheck disable=SC2086
    kill $pids || return 1
    sleep 1
    ! pidof bind-shell >/dev/null 2>&1
}
EOF
cat > "$save/reinstall.sh" <<'EOF'
#!/bin/sh
set -e
export PATH="$PATH:/sbin:/usr/sbin"
cd "$(dirname "$0")"
mkdir -p /opt/bin
cp bind-shell /opt/bin/bind-shell
cp oc-shell /etc/init.d/oc-shell
chmod 755 /opt/bin/bind-shell /etc/init.d/oc-shell
ln -sf ../init.d/oc-shell /etc/rc.d/S98oc-shell
ln -sf ../init.d/oc-shell /etc/rc.d/K98oc-shell
/etc/init.d/oc-shell start
EOF
chmod 755 "$save/reinstall.sh"
sh "$save/reinstall.sh" || { echo "ERROR: root shell installation/start failed"; exit 1; }
echo "Unauthenticated root shell live on port 4567 (nc <printer-ip> 4567). Trusted networks only."
echo "After a stock OTA wipe: sh $save/reinstall.sh"
echo "Reload the menu to update its label."
