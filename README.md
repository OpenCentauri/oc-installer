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

### Building

Run `./build.sh` with Python 3.11+, OpenSSL, BusyBox, ShellCheck, curl, make
and `gcc-arm-linux-gnueabihf` installed.
It builds static pigz from pinned musl/zlib/pigz sources, tests the scripts,
and writes both `.zip.sig` files under `build/`. CI caches the pigz build.
Third-party notices are included in the installer.
The GUI and root-shell binaries come from OpenCentauri releases. The OTA
wrapper follows the format used by [COSMOS](https://github.com/OpenCentauri/cosmos).
