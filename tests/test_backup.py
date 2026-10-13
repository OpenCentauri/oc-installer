#!/usr/bin/env python3
"""Exercise the backup with regular files, including failing pipeline stages."""
import gzip
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BackupTest(unittest.TestCase):
    def run_backup(self, filesystem="vfat", fault="", shell="sh", repeat=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            usb = root / "usb"
            usb.mkdir()
            old = usb / "c2-emmc-backup.bin.gz.part-000"
            old.write_bytes(b"previous backup")
            data = os.urandom(32768 * 12)
            disk = root / "disk"
            disk.write_bytes(data[:32768] if fault == "short" else data)
            (root / "size").write_text(str(len(data) // 512))
            source = "/dev/mmcblk0p12" if fault == "internal" else "/dev/sda1"
            (root / "mounts").write_text(f"{source} {usb} {filesystem} rw 0 0\n")
            script = (ROOT / "install_c2/backup-emmc.sh").read_text()
            for before, after in {
                "/mnt/exUDISK": str(usb), "/mnt/UDISK": str(root / "absent"),
                "/sys/class/block/mmcblk0/size": str(root / "size"),
                "/dev/mmcblk0": str(disk), "/proc/mounts": str(root / "mounts"),
                "chunk_blocks=1024": "chunk_blocks=4",
                "part_size=1073741824": "part_size=65536",
            }.items():
                script = script.replace(before, after)
            target = root / "backup.sh"
            target.write_text(script)
            compressor = root / "pigz"
            compressor.write_text('#!/bin/sh\nif [ "$1" = -1 ]; then shift 3; exec gzip -1 "$@"; fi\nexec gzip "$@"\n')
            compressor.chmod(0o755)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            stubs = {
                "df": '#!/bin/sh\nprintf "Filesystem 1K-blocks Used Available Use%% Mounted\\n/dev/sda1 9999999 0 %s 0%% /usb\\n" ' + ("1" if fault == "space" else "9999999") + "\n",
                "sync": "#!/bin/sh\nexit 0\n",
                "date": "#!/bin/sh\necho 20260101-010101\n",
            }
            if fault == "reader":
                stubs["dd"] = "#!/bin/sh\nexit 1\n"
            if fault in ("compress", "verify"):
                stubs["gzip"] = '#!/bin/sh\ncase "$1" in ' + ("-1" if fault == "compress" else "-t") + ') exit 1 ;; esac\nexec /usr/bin/gzip "$@"\n'
            if fault == "writer":
                stubs["head"] = "#!/bin/sh\nexit 1\n"
            for name, body in stubs.items():
                path = bin_dir / name
                path.write_text(body)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
            command = ["busybox", "ash"] if shell == "busybox" else [shell]
            result = subprocess.run(command + [str(target)], env=env, capture_output=True, timeout=20)
            self.assertEqual(old.read_bytes(), b"previous backup")
            backups = sorted(p for p in usb.iterdir() if p.is_dir())
            if fault:
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertFalse(any((p / "OK.txt").exists() for p in backups))
                self.assertNotIn(b"Backup complete:", result.stdout)
                if fault not in ("space", "internal"):
                    self.assertTrue(any((p / "FAILED.txt").exists() for p in backups))
                return
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(len(backups), 1)
            folder = backups[0]
            self.assertFalse(folder.name.endswith(".partial"))
            files = sorted(folder.glob("c2-emmc-backup.bin.gz*"))
            self.assertEqual(gzip.decompress(b"".join(f.read_bytes() for f in files)), data)
            self.assertEqual(len(files) > 1, filesystem == "vfat")
            self.assertIn(f"Read {len(data)} / {len(data)} bytes (100%)".encode(), result.stdout)
            self.assertIn(b"Checking gzip archive", result.stdout)
            self.assertIn(str(len(data)), (folder / "OK.txt").read_text())
            if repeat:
                second = subprocess.run(command + [str(target)], env=env, capture_output=True, timeout=20)
                self.assertNotEqual(second.returncode, 0)
                self.assertEqual(gzip.decompress(b"".join(f.read_bytes() for f in files)), data)

    def test_filesystems_and_progress(self):
        for fs in ("vfat", "exfat", "ext4"):
            with self.subTest(filesystem=fs):
                self.run_backup(filesystem=fs)

    def test_failure_paths_preserve_previous_backup(self):
        for fault in ("short", "reader", "compress", "writer", "verify", "space", "internal"):
            with self.subTest(fault=fault):
                self.run_backup(fault=fault)

    def test_existing_directory_is_not_reused(self):
        self.run_backup(repeat=True)

    @unittest.skipUnless(shutil.which("busybox"), "BusyBox not installed")
    def test_busybox_ash(self):
        self.run_backup(shell="busybox")
        self.run_backup(shell="busybox", fault="short")


if __name__ == "__main__":
    unittest.main()
