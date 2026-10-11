#!/bin/sh
# Backup /dev/mmcblk0 to USB stick as c2-emmc-backup.bin.gz (split on vfat).
# shellcheck disable=SC2012  # filenames are fixed constants we create ourselves
# Verifies dd's reported bytes (when dd prints them) and the decompressed
# stream length against the eMMC device size. Progress via dd SIGUSR1 records.
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

DDLOG="$DEST/c2-emmc-backup.dd.log"
echo "started $(date -u 2>/dev/null), expect $TOTAL bytes" > "$DEST/c2-emmc-backup.STARTED.txt"
rm -f "$DEST/c2-emmc-backup.OK.txt" "$DEST/c2-emmc-backup.FAILED.txt" "$DEST/$OUTBASE" "$DEST/$OUTBASE.part-"*

sync
for s in grumpyscreen moonraker klipper klippy; do
    [ -x "/etc/init.d/$s" ] && /etc/init.d/$s stop 2>/dev/null
    killall "$s" 2>/dev/null
done
sync

IS_VFAT=0
mount | grep -q " on $DEST type vfat" && IS_VFAT=1

if [ "$IS_VFAT" = "1" ]; then
    dd if=/dev/mmcblk0 bs=4M 2>"$DDLOG" | gzip -1 | \
        split -b 3800m - "$DEST/$OUTBASE.part-" &
else
    dd if=/dev/mmcblk0 bs=4M 2>"$DDLOG" | gzip -1 > "$DEST/$OUTBASE" &
fi
PIPE_PID=$!

# Progress watcher: poke dd with SIGUSR1 so it logs "N+M records in" to DDLOG,
# then derive read bytes = records * 4MiB. Works on busybox and GNU dd.
while kill -0 "$PIPE_PID" 2>/dev/null; do
    DDPID=$(pidof dd 2>/dev/null | awk '{print $1}')
    [ -z "$DDPID" ] && DDPID=$(pgrep -x dd 2>/dev/null | head -n1)
    [ -n "$DDPID" ] && kill -USR1 "$DDPID" 2>/dev/null
    RECS=$(awk '/records in/ {print $1}' "$DDLOG" 2>/dev/null | tail -1); RECS=${RECS%%+*}
    if [ -n "$RECS" ]; then
        PCT=$(awk -v r="$RECS" -v t="$TOTAL" 'BEGIN{p=int(r*4194304*100/t); print (p>100)?100:p}')
    else
        PCT=0
    fi
    FILL=$((PCT/5)); BAR=""
    i=0; while [ $i -lt $FILL ]; do BAR="$BAR="; i=$((i+1)); done
    printf '[backup] [%-20s] %3d%%\r' "$BAR" "$PCT"
    sleep 10
done
wait "$PIPE_PID"; RC=$?
echo
sync

# Check 1: dd's accounting. GNU dd prints "bytes (...) copied"; busybox dd
# only prints "N+M records in/out" - parse whichever exists, tolerate neither.
DDBYTES=$(awk '/bytes.*copied/ {print $1}' "$DDLOG" | tail -1)
if [ -n "$DDBYTES" ] && [ "$DDBYTES" != "$TOTAL" ]; then
    say "dd output:"; cat "$DDLOG"
    fail "dd read $DDBYTES bytes but eMMC is $TOTAL bytes - dump is TRUNCATED (read error mid-disk? check dmesg for mmc errors)"
fi
RECS_IN=$(awk '/records in/ {print $1}' "$DDLOG" | tail -1); RECS_IN=${RECS_IN%%+*}
RECS_OUT=$(awk '/records out/ {print $1}' "$DDLOG" | tail -1); RECS_OUT=${RECS_OUT%%+*}
if [ "$RC" != "0" ] || { [ -n "$RECS_IN" ] && [ "$RECS_IN" != "$RECS_OUT" ]; }; then
    say "dd output:"; cat "$DDLOG"
    fail "dd pipeline failed (rc=$RC, records in=$RECS_IN out=$RECS_OUT) - check dmesg for mmc errors"
fi
say "dd finished, records in=$RECS_IN out=$RECS_OUT"

# Check 2: decompress the whole stream and count bytes (end-to-end proof).
say "verifying gzip stream (this takes a few minutes)..."
if [ "$IS_VFAT" = "1" ]; then
    OUTBYTES=$(cat "$DEST/$OUTBASE.part-"* | gzip -dc 2>/dev/null | wc -c)
else
    OUTBYTES=$(gzip -dc "$DEST/$OUTBASE" 2>/dev/null | wc -c)
fi
if [ "$OUTBYTES" != "$TOTAL" ]; then
    fail "decompressed backup is ${OUTBYTES:-0} bytes, expected $TOTAL - gzip stream corrupt or truncated (stick full? pulled early?)"
fi

ls -l "$DEST/$OUTBASE"* > "$DEST/c2-emmc-backup.OK.txt"
say "=========================================="
say " BACKUP COMPLETE: $OUTBASE"
say " $TOTAL bytes dumped and verified."
say " Safe to reboot when ready."
say "=========================================="
exit 0
