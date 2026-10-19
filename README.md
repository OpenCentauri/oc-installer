# oc-installer
Exploit + Installer tools for the Centauri Carbon

This installer can
- Install OpenCentauri
- Update OpenCentauri
- Uninstall OpenCentauri
- Install or remove a root shell (port 4567)

In `Utils`, stock CC1 can install or remove the root shell. Installation refuses
if TCP port 4567 is already listening, reporting
`ERROR: Root shell already installed/running` without changing anything.
An installer-managed shell can still be removed.
CC1 shell recovery files are stored in `/user-resource/sig-dump-emmc`.
After a stock OTA, restore with `sh /user-resource/sig-dump-emmc/reinstall.sh`.

## Usage
1. [Download](https://github.com/OpenCentauri/oc-installer/releases/latest/download/oc-installer.zip) the latest release
2. Insert a fat32-formatted thumbdrive into your pc
3. Extract the `install_opencentauri` folder from `oc-installer.zip` onto the thumbdrive
4. Eject your thumbdrive from your pc and insert it into your Centauri Carbon
5. On your Centauri Carbon, navigate to the files tab, `Usb Drive`, then `install_opencentauri`
6. Touch hold the `IMPORT_ME_DO_NOT_PRINT` file, then select `Import`
7. Run `Install OpenCentauri (Online)`
8. Restart when the install process finished

## Centauri 2 / Centauri Carbon 2

This installer can
- Install COSMOS online or from USB
- Check the boot slot
- Install or remove a root shell
- Back up the eMMC to USB

### Usage
1. Download `installer-c2` or `installer-cc2` from the build artifacts
2. Extract the `.zip.sig` file onto a FAT32-formatted thumbdrive
3. Insert the drive and select the update in the printer's update menu
4. Choose a tool, then `Exit and Reboot` when finished

The update opens the installer without flashing firmware. It stops the stock
updater and clears its pending update flags. Only the COSMOS install buttons
flash firmware. C2 and CC2 use the same COSMOS image.

For an offline install, put `cosmos-centauri-carbon-2.swu` on the drive as
`install_c2/update.swu`.

### Root shell

Installing starts the shell immediately and at boot. Connect with
`nc <printer-ip> 4567`. There is no authentication; use a trusted network and
remove the shell when finished. `Reload menu` updates the install/remove label.
After a stock OTA wipe, reinstall with
`sh /opt/usr/sig-dump-emmc/reinstall.sh`.

### eMMC backup

Keep at least 5 GiB free. Do not print or remove the USB drive during backup.
The screen shows bytes read and percentage, then checks the gzip archive.
Compression uses two-worker pigz at level 1; the bundled static binary also
checks the archive.
This copies a running system, not a consistent filesystem snapshot.

Each run creates a dated `c2-emmc-backup-*` directory. Previous backups are
left alone. A `.partial` directory is incomplete; a finished backup contains
`OK.txt`. Remove unwanted backups on your computer to reclaim space.

FAT32 output is split into 1 GiB parts. exFAT/ext4 output is a single gzip file,
if the printer supports and mounts that filesystem. On a computer:

```sh
# FAT32: reassemble the parts inside the backup directory
cat c2-emmc-backup.bin.gz.part-* > c2-emmc-backup.bin.gz

gzip -t c2-emmc-backup.bin.gz
gzip -dc c2-emmc-backup.bin.gz | wc -c
```

The decompressed size on the tested C2/CC2 eMMC is `7837581312` bytes. Use host
tools for this check; the stock printer's `wc` counter wraps above 4 GiB.

### Building

Run `./build.sh` with Python 3.11+, OpenSSL, BusyBox, ShellCheck, curl, make
and `gcc-arm-linux-gnueabihf` installed.
It builds static pigz from pinned musl/zlib/pigz sources, tests the scripts,
and writes both `.zip.sig` files under `build/`. CI caches the pigz build.
Third-party notices are included in the installer.
The GUI and root-shell binaries come from OpenCentauri releases. The OTA
wrapper follows the format used by [COSMOS](https://github.com/OpenCentauri/cosmos).
