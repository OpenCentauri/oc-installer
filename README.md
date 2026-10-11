# oc-installer
Exploit + Installer tools for the Centauri Carbon

This installer can
- Install OpenCentauri
- Update OpenCentauri
- Uninstall OpenCentauri

## Usage
1. [Download](https://github.com/OpenCentauri/oc-installer/releases/latest/download/oc-installer.zip) the latest release
2. Insert a fat32-formatted thumbdrive into your pc
3. Extract the `install_opencentauri` folder from `oc-installer.zip` onto the thumbdrive
4. Eject your thumbdrive from your pc and insert it into your Centauri Carbon
5. On your Centauri Carbon, navigate to the files tab, `Usb Drive`, then `install_opencentauri`
6. Touch hold the `IMPORT_ME_DO_NOT_PRINT` file, then select `Import`
7. Run `Install OpenCentauri (Online)`
8. Restart when the install process finished

## C2 / CC2 tools (branch `paul/add-c2-cc2`)

The `install_c2` folder is a touchscreen toolkit for the Centauri 2 and
Centauri Carbon 2. It can:

- Install COSMOS (Online — pulls the latest nightly CI build, or From USB)
- Check boot slot
- Install a root shell on port 4567 (`nc <printer-ip> 4567`)
- Back up the entire eMMC to the USB stick (`c2-emmc-backup.bin.gz`,
  byte-count verified)

### Usage (C2/CC2)

1. Run `./build.sh` on a Linux host (needs python3, openssl, curl). This runs
   the tests, builds the bootstrap SWU, and wraps it into
   `build/cc2_eeb001_installer_*.zip.sig` (CC2) and
   `build/c2_eeb001_installer_*.zip.sig` (C2).
2. Copy the `install_c2` folder **and** the right `.zip.sig` for your machine
   onto a FAT32-formatted thumbdrive (zip.sig at the root, `install_c2` folder
   beside it).
3. Insert into the printer and apply the update from the printer's update UI.
   Nothing is flashed: the update just launches the installer GUI. Use the
   buttons; "Exit and Reboot" when done.

Notes:
- The eMMC backup is a live-disk copy (crash-consistent). FAT32 sticks get
  split files (`c2-emmc-backup.bin.gz.part-*`); reassemble with
  `cat c2-emmc-backup.bin.gz.part-* > c2-emmc-backup.bin.gz`.
- The root shell is a LAN backdoor by design. Treat the stick like a key.
- The COSMOS buttons flash firmware when you confirm them; everything else in
  the toolkit never writes firmware or boot variables.
