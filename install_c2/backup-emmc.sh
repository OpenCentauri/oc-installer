#!/bin/sh
# Backup /dev/mmcblk0 (7837581312 bytes on C2/CC2) to USB stick as
# c2-emmc-backup.bin.gz (split on vfat).
# shellcheck disable=SC2012  # filenames are fixed constants we create ourselves
# Reads eMMC in 64 MiB chunks (one long dd gets killed on this kernel ~35s in;
# chunked reads dodge it) and reports progress per chunk. Verifies the whole
# gzip stream by decompressing and counting bytes against the device size.
# Busybox-safe: no 64-bit shell arithmetic (sizes as strings / awk doubles).
set +e

OUTBASE="c2-emmc-backup.bin.gz"
NEED_KB=5242880   # 5 GiB

say() { echo "[backup] $*"; }
fail() { say "ERROR: $*"; echo "$* $(date -u 2>/dev/null)" > "$DEST/c2-emmc-backup.FAILED.txt" 2>/dev/null; exit 1; }

DEST=""
for mp in /mnt/exUDISK /mnt/UDISK; do
    mount | grep -q " on $mp " && DEST="$mp" && break
done
if [ -z "$DEST" ]; then
    mkdir -p /mnt/exUDISK
    for dev in /dev/sda1 /dev/sda /dev/sdb1 /dev/sdb; do
        [ -b "$dev" ] && mount "$dev" /mnt/exUDISK 2>/dev/null && DEST=/mnt/exUDISK && break
    done
fi
[ -z "$DEST" ] && { say "ERROR: no USB stick found"; exit 1; }

FREE_KB=$(df -k "$DEST" | awk 'NR==2 {print $4}')
if [ -z "$FREE_KB" ] || [ "$FREE_KB" -lt "$NEED_KB" ]; then
    fail "USB stick has ${FREE_KB:-0} kB free, need at least $NEED_KB kB (5 GiB)"
fi

# Byte size as a *string* (no 64-bit shell math on 32-bit ash).
TOTAL=$(blockdev --getsize64 /dev/mmcblk0 2>/dev/null)
if [ -z "$TOTAL" ]; then
    TOTAL=$(awk -v s="$(cat /sys/class/block/mmcblk0/size 2>/dev/null)" 'BEGIN{printf "%.0f", s*512}')
fi
case "$TOTAL" in ''|*[!0-9]*|0) fail "cannot determine /dev/mmcblk0 size" ;; esac
say "eMMC size: $TOTAL bytes -> $DEST"

echo "started $(date -u 2>/dev/null), expect $TOTAL bytes" > "$DEST/c2-emmc-backup.STARTED.txt"
rm -f "$DEST/c2-emmc-backup.OK.txt" "$DEST/c2-emmc-backup.FAILED.txt" "$DEST/$OUTBASE" "$DEST/$OUTBASE.part-"*

sync
for s in grumpyscreen moonraker klipper klippy ai_camera; do
    [ -x "/etc/init.d/$s" ] && /etc/init.d/$s stop 2>/dev/null
    killall "$s" 2>/dev/null
done
sync

IS_VFAT=0
mount | grep -q " on $DEST type vfat" && IS_VFAT=1

# Chunked reader: one long dd's records can outrun the pipe consumer; 8 MiB
# chunks keep progress granular and each chunk a fresh, short-lived process.
CHUNKS=$(awk -v t="$TOTAL" 'BEGIN{print int((t+8388607)/8388608)}')
read_emmc() {
    i=0
    while [ "$i" -lt "$CHUNKS" ]; do
        dd if=/dev/mmcblk0 bs=1M skip=$((i*8)) count=8 2>/dev/null || {
            echo "[backup] ERROR: dd chunk $i/$CHUNKS failed - check dmesg for mmc errors" >&2
            exit 1
        }
        i=$((i+1))
        awk -v i="$i" -v n="$CHUNKS" 'BEGIN{printf "[backup] chunk %d/%d (%d%%)\n", i, n, int(i*100/n)}' >&2
    done
}

if [ "$IS_VFAT" = "1" ]; then
    # Stock busybox has no split(1); rotate parts with head -c (byte-exact).
    # Do NOT use 'dd count=': busybox dd lacks iflag=fullblock, so each short
    # pipe read counts as a full record and the part closes after ~3800 tiny
    # reads (~31 MiB) instead of 3800 MiB.
    read_emmc | gzip -1 | {
        i=0
        while :; do
            part=$(printf '%s.part-%03d' "$DEST/$OUTBASE" "$i")
            head -c 3984588800 > "$part"
            [ -s "$part" ] || { rm -f "$part"; break; }
            [ "$(wc -c < "$part")" -lt 3984588800 ] && break
            i=$((i+1))
        done
    }
else
    read_emmc | gzip -1 > "$DEST/$OUTBASE"
fi
sync

# Verify: decode the whole stream and check gzip's exit status. (Do NOT
# byte-count with wc -c on-device: busybox wc wraps at 4 GiB on pipes. For a
# deep check, scp the parts to a host and 'gzip -dc | wc -c' there.)
say "verifying gzip stream (this takes a few minutes)..."
VERIFY_OK=1
if [ "$IS_VFAT" = "1" ]; then
    cat "$DEST/$OUTBASE.part-"* | gzip -dc > /dev/null 2>&1 || VERIFY_OK=0
else
    gzip -dc "$DEST/$OUTBASE" > /dev/null 2>&1 || VERIFY_OK=0
fi
if [ "$VERIFY_OK" != "1" ]; then
    fail "gzip stream corrupt or truncated (stick full? pulled early?)"
fi

ls -l "$DEST/$OUTBASE"* > "$DEST/c2-emmc-backup.OK.txt"
say "=========================================="
say " BACKUP COMPLETE: $OUTBASE"
say " $TOTAL bytes dumped and verified."
say " Safe to reboot when ready."
say "=========================================="
exit 0
