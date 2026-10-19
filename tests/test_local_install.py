#!/usr/bin/env python3
"""Exercise local CC1 SWU selection without touching printer devices."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NAMED = "cosmos-centauri-carbon-1.swu"


class LocalCC1InstallTest(unittest.TestCase):
    def exercise(self, files, selected=None, boot="bootA", updater_rc=0, busybox=False):
        with tempfile.TemporaryDirectory(prefix="oc-local-cc1-") as tmp:
            root = Path(tmp)
            payload = root / "user-resource/update_tmp"
            usb = root / "mnt/exUDISK/install_opencentauri"
            commands = root / "bin"
            for path in (payload, usb, commands, root / "board-resource"):
                path.mkdir(parents=True)
            config = root / "board-resource/printer.cfg"
            config.write_text("preserve on failure\n")
            for name, data in files.items():
                path = usb / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            script = (ROOT / "install_opencentauri/install-oc-local.sh").read_text()
            for prefix in ("/user-resource", "/mnt", "/board-resource"):
                script = script.replace(prefix, str(root) + prefix)
            target = payload / "install-oc-local.sh"
            target.write_text(script)
            stubs = {
                "fw_printenv": 'printf "boot_partition=%s\\n" "$BOOT"\n',
                "swupdate": 'printf "%s\\n" "$@" > "$TEST_ROOT/flash-args"\nexit "$UPDATER_RC"\n',
                "sync": ':\n',
            }
            for name, body in stubs.items():
                path = commands / name
                path.write_text("#!/bin/sh\n" + body)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f"{commands}:/usr/bin:/bin", TEST_ROOT=str(root),
                       BOOT=boot, UPDATER_RC=str(updater_rc))
            shell = ["/usr/bin/busybox", "sh"] if busybox else ["/bin/sh"]
            result = subprocess.run(shell + [str(target)], env=env, capture_output=True,
                                    text=True, timeout=10)
            expected_rc = updater_rc if selected is not None else 1
            self.assertEqual(result.returncode, expected_rc, result.stdout + result.stderr)
            log = root / "flash-args"
            self.assertEqual(log.exists(), selected is not None)
            if selected is not None:
                slot = "now_A_next_B" if boot == "bootA" else "now_B_next_A"
                self.assertEqual(log.read_text().splitlines(),
                                 ["-i", str(usb / selected), "-e", f"stable,{slot}",
                                  "-k", str(payload / "swupdate_public.pem")])
            self.assertEqual(config.exists(), expected_rc != 0)
            for name, data in files.items():
                self.assertEqual((usb / name).read_bytes(), data)

    def test_release_filename_is_accepted(self):
        self.exercise({NAMED: b"named fixture SWU"}, selected=NAMED, busybox=True)

    def test_aliases_slots_and_priority(self):
        for busybox in (False, True):
            for boot in ("bootA", "bootB"):
                for name in ("update.swu", NAMED):
                    self.exercise({name: b"fixture SWU"}, selected=name, boot=boot, busybox=busybox)
            self.exercise({"update.swu": b"explicit", NAMED: b"named"},
                          selected="update.swu", busybox=busybox)
            self.exercise({"update.swu": b"", NAMED: b"named"}, selected=NAMED, busybox=busybox)
            self.exercise({"other.swu": b"not a match"}, busybox=busybox)
            self.exercise({f"../{NAMED}": b"wrong directory"}, busybox=busybox)
            self.exercise({"cosmos-centauri-carbon-2.swu": b"wrong model"}, busybox=busybox)
            self.exercise({"update.swu": b""}, busybox=busybox)

    def test_failures_do_not_remove_config_or_original_swu(self):
        for busybox in (False, True):
            self.exercise({NAMED: b"fixture SWU"}, selected=NAMED, updater_rc=17, busybox=busybox)
            self.exercise({NAMED: b"fixture SWU"}, boot="unknown", busybox=busybox)


if __name__ == "__main__":
    unittest.main()
