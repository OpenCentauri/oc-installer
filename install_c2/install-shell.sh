#!/bin/sh
# Install bind-shell root shell on port 4567. Idempotent. Never fails hard.
set +e
cd "$(dirname "$0")" || exit 0
if touch /etc/.wtest 2>/dev/null; then
    rm -f /etc/.wtest
    mkdir -p /app /etc/hotplug.d/block
    cp ./bind-shell /app/bind-shell && chmod 755 /app/bind-shell
    printf '#!/bin/sh\npidof bind-shell >/dev/null 2>&1 || { chmod a+x /app/bind-shell; /app/bind-shell 4567 & }\n' > /etc/hotplug.d/block/12-shell
    chmod 755 /etc/hotplug.d/block/12-shell
    if ! grep -q 'oc-installer bind-shell' /etc/rc.local 2>/dev/null; then
        if grep -q '^exit 0' /etc/rc.local 2>/dev/null; then
            sed -i 's|^exit 0|# BEGIN oc-installer bind-shell\n[ -x /app/bind-shell ] \&\& /app/bind-shell 4567 \&\n# END oc-installer bind-shell\nexit 0|' /etc/rc.local 2>/dev/null
        else
            # Prepend; cat-through preserves the existing inode/mode.
            { printf '# BEGIN oc-installer bind-shell\n[ -x /app/bind-shell ] && /app/bind-shell 4567 &\n# END oc-installer bind-shell\n'; cat /etc/rc.local 2>/dev/null; } > /tmp/rc.local.new \
                && cat /tmp/rc.local.new > /etc/rc.local && rm -f /tmp/rc.local.new
        fi
    fi
    echo "installed to overlay (hotplug + rc.local)"
else
    echo "WARN: /etc not writable, overlay install skipped"
fi
mkdir -p /user-resource/sig-dump-emmc
cp ./bind-shell /user-resource/sig-dump-emmc/bind-shell
printf 'Reinstall after stock OTA wipe:\n  cp /user-resource/sig-dump-emmc/bind-shell /app/bind-shell\n  cp /user-resource/sig-dump-emmc/12-shell /etc/hotplug.d/block/12-shell\n  /app/bind-shell 4567 &\n' > /user-resource/sig-dump-emmc/README.txt
cp /etc/hotplug.d/block/12-shell /user-resource/sig-dump-emmc/ 2>/dev/null
/app/bind-shell 4567 2>/dev/null &
echo "root shell live on port 4567 (nc <printer-ip> 4567)"
exit 0
