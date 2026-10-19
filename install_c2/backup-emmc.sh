#!/bin/sh

set -e
export LC_ALL=C
model=${1:-c2}
case "$model" in c2|cc1) ;; *) echo "Unknown backup target"; exit 1 ;; esac
name=$model-emmc-backup

cd "$(dirname "$0")"
compressor="$PWD/pigz"
[ -x "$compressor" ] || { echo "Missing pigz in installer"; exit 1; }

usb=""
for path in /mnt/exUDISK /mnt/UDISK; do
    if awk -v path="$path" '$2 == path && $1 ~ /^\/dev\/sd/ { found=1 } END { exit !found }' /proc/mounts; then
        usb="$path"
        break
    fi
done
if [ -z "$usb" ]; then
    echo "No USB drive found"
    exit 1
fi

free=$(df -Pk "$usb" | awk 'END {print $4}')
if [ "${free:-0}" -lt 5242880 ]; then
    echo "At least 5 GiB of free space is required. Existing backups have not been changed."
    exit 1
fi

# Keep arithmetic in blocks so it fits in the stock 32-bit shell.
sectors=$(cat /sys/class/block/mmcblk0/size)
case "$sectors" in ''|*[!0-9]*) echo "Cannot read eMMC size"; exit 1 ;; esac
[ "$sectors" -gt 0 ] && [ "$((sectors % 64))" -eq 0 ] || exit 1
blocks=$((sectors / 64))
total=$(awk -v n="$blocks" 'BEGIN {printf "%.0f", n * 32768}')
chunk_blocks=1024
part_size=1073741824

# Each run gets its own directory. Never overwrite a previous backup.
backup="$usb/$name-$(date +%Y%m%d-%H%M%S)"
work="$backup.partial"
if [ -e "$backup" ] || ! mkdir "$work"; then
    echo "Backup directory already exists or is not writable: $work"
    exit 1
fi
cleanup() {
    rc=$?
    trap - EXIT
    if [ "$rc" -ne 0 ]; then
        echo "Backup failed. Previous backups have not been changed."
        echo "Backup incomplete" > "$work/FAILED.txt" 2>/dev/null || :
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 1' HUP INT TERM
printf '%s bytes\n' "$total" > "$work/STARTED.txt"
echo "Backing up $total bytes to $backup"
echo "Do not print, remove the drive or turn off the printer during the backup."
sync

# fd 3 is the GUI output; stdout in this function carries only disk data.
exec 3>&1
read_emmc() {
    offset=0
    while [ "$offset" -lt "$blocks" ]; do
        count=$((blocks - offset))
        [ "$count" -le "$chunk_blocks" ] || count=$chunk_blocks
        if ! dd if=/dev/mmcblk0 bs=32768 skip="$offset" count="$count" 2> "$work/dd.log"; then
            cat "$work/dd.log" >&3
            return 1
        fi
        # dd returns success at early EOF too. Require every requested block.
        grep -qx "$count+0 records out" "$work/dd.log" || return 1
        offset=$((offset + count))
        awk -v n="$offset" -v total="$total" 'BEGIN {
            printf "Read %.0f / %s bytes (%d%%)\n", n * 32768, total, n * 32768 * 100 / total
        }' >&3
    done
    touch "$work/read.ok"
}

write_archive() {
    if awk -v path="$usb" '$2 == path && $3 == "vfat" { found=1 } END { exit !found }' /proc/mounts; then
        part=0
        while :; do
            file=$(printf '%s/%s.bin.gz.part-%03d' "$work" "$name" "$part")
            # Stock busybox head -c over-reads pipes and drops the surplus on
            # exit; dd with a fixed block count stops cleanly at part edges.
            dd bs=32768 count=$((part_size / 32768)) of="$file" 2>/dev/null || return 1
            if [ ! -s "$file" ]; then
                rm "$file"
                break
            fi
            part=$((part + 1))
        done
    else
        cat > "$work/$name.bin.gz"
    fi
}

read_emmc | { "$compressor" -1 -p 2 && touch "$work/gzip.ok"; } | write_archive
# POSIX pipelines only return the last command's status.
[ -f "$work/read.ok" ] && [ -f "$work/gzip.ok" ] || exit 1
sync

echo "Read complete. Checking gzip archive..."
cat "$work/$name.bin.gz"* | "$compressor" -t
rm "$work/read.ok" "$work/gzip.ok" "$work/dd.log"
printf '%s bytes read; gzip integrity checked\n' "$total" > "$work/OK.txt"
mv "$work" "$backup"
sync
trap - EXIT HUP INT TERM
echo "Backup complete: $backup"
echo "Safe to reboot."
