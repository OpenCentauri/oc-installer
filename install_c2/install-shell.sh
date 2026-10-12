#!/bin/sh
# Toggle the bind-shell root shell (port 4567): installs a native init.d
# service, or removes every trace if already installed. Never fails hard.
set +e

# /opt/bin is the vendor app dir (rootfs, mounted before rc.d runs - /opt/usr
# mounts too late for START=98). The /opt/usr helper copy survives OTA wipes.
BIN=/opt/bin/bind-shell
INIT=/etc/init.d/oc-shell

if [ -f "$INIT" ]; then
    "$INIT" stop 2>/dev/null
    # shellcheck disable=SC2046  # pidof list should word-split
    kill $(pidof bind-shell) 2>/dev/null
    rm -f "$INIT" /etc/rc.d/S98oc-shell /etc/rc.d/K98oc-shell "$BIN"
    rm -rf /opt/usr/sig-dump-emmc
    # Leftovers from the old hotplug/rc.local approach, if any.
    rm -f /etc/hotplug.d/block/12-shell /app/bind-shell
    sed -i '/# BEGIN oc-installer bind-shell/,/# END oc-installer bind-shell/d' /etc/rc.local 2>/dev/null
    echo "root shell removed"
    exit 0
fi

cp "$(dirname "$0")/bind-shell" "$BIN" && chmod 755 "$BIN"
cat > "$INIT" <<'EOF'
#!/bin/sh /etc/rc.common
# oc-installer: bind-shell root shell on port 4567
START=98

start() {
    pidof bind-shell >/dev/null 2>&1 && return 0
    [ -x /opt/bin/bind-shell ] || return 0
    /opt/bin/bind-shell 4567 </dev/null >/dev/null 2>&1 &
}

stop() {
    kill $(pidof bind-shell) 2>/dev/null
}
EOF
chmod 755 "$INIT"
ln -sf ../init.d/oc-shell /etc/rc.d/S98oc-shell
ln -sf ../init.d/oc-shell /etc/rc.d/K98oc-shell

# Remove leftovers from the old hotplug/rc.local approach.
rm -f /etc/hotplug.d/block/12-shell
sed -i '/# BEGIN oc-installer bind-shell/,/# END oc-installer bind-shell/d' /etc/rc.local 2>/dev/null

# Reinstall helper, for after a stock OTA wipe (overlay is wiped; /opt/usr is not).
mkdir -p /opt/usr/sig-dump-emmc
cp "$INIT" /opt/usr/sig-dump-emmc/
cp "$BIN" /opt/usr/sig-dump-emmc/
printf 'Reinstall after stock OTA wipe:\n  cp /opt/usr/sig-dump-emmc/bind-shell /opt/bin/bind-shell\n  cp /opt/usr/sig-dump-emmc/oc-shell /etc/init.d/oc-shell\n  chmod 755 /opt/bin/bind-shell /etc/init.d/oc-shell\n  ln -sf ../init.d/oc-shell /etc/rc.d/S98oc-shell\n  ln -sf ../init.d/oc-shell /etc/rc.d/K98oc-shell\n  /etc/init.d/oc-shell start\n' > /opt/usr/sig-dump-emmc/README.txt

"$INIT" start
sleep 1
if pidof bind-shell >/dev/null 2>&1; then
    echo "root shell live on port 4567 (nc <printer-ip> 4567)"
else
    echo "ERROR: bind-shell failed to start" >&2
fi
exit 0
