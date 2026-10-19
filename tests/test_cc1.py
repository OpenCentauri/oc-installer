#!/usr/bin/env python3
"""CC1 utility menu, shell dispatch and packaged USB payload checks."""
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import tomllib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NOTE = "ERROR: Root shell already installed/running"


class LauncherTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="oc-cc1-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.usb = self.root / "mnt/exUDISK"
        self.source = self.usb / "install_opencentauri"
        self.payload = self.root / "user-resource/update_tmp"
        self.bin = self.root / "bin"
        for p in (self.source, self.bin, self.root / "etc/init.d"):
            p.mkdir(parents=True)
        self.env = dict(os.environ, PATH=f"{self.bin}:/usr/bin:/bin",
                        TEST_ROOT=str(self.root), ROOT_SHELL_BUSY="0", GUI_RC="0", REFRESH="0")
        for name in ("run.sh", "install-shell.sh"):
            text = (ROOT / "install_opencentauri" / name).read_text()
            for prefix in ("/user-resource", "/etc", "/mnt", "/proc/sys/vm/drop_caches"):
                text = text.replace(prefix, str(self.root) + prefix)
            self.put(self.source / name, text)
        self.put(self.source / "config.toml", (ROOT / "install_opencentauri/config.toml").read_text())
        self.put(self.source / "log-task.sh", (ROOT / "install_c2/log-task.sh").read_text()
                 .replace("/mnt/", str(self.root) + "/mnt/"))
        self.put(self.source / "shell-service.sh", '''#!/bin/sh
printf '%s\n' "$@" >> "$TEST_ROOT/service-calls"
if [ -f "$TEST_ROOT/etc/init.d/oc-shell" ]; then
    rm "$TEST_ROOT/etc/init.d/oc-shell"
else
    [ "$ROOT_SHELL_BUSY" != 1 ] || { echo "ERROR: Root shell already installed/running"; exit 1; }
    touch "$TEST_ROOT/etc/init.d/oc-shell"
fi
''')
        for name in ("decrypt", "utf8-fix", "wifi-network-config-tool", "bind-shell"):
            self.put(self.source / name, "#!/bin/sh\nexit 0\n")
        self.put(self.source / "recovery", '''#!/bin/sh
if [ ! -f "$TEST_ROOT/before.toml" ]; then
    cp config.toml "$TEST_ROOT/before.toml"
    if [ "$REFRESH" = 1 ]; then
        sh ./install-shell.sh || exit 99
        sh ./run.sh reload
        exit 98
    fi
else
    cp config.toml "$TEST_ROOT/after.toml"
fi
if [ "${RUN_SHELL:-0}" = 1 ]; then
    sh ./log-task.sh sh ./install-shell.sh
    echo "$?" > "$TEST_ROOT/task-status"
fi
exit "$GUI_RC"
''')
        self.put(self.root / "proc/sys/vm/drop_caches", "")
        self.put(self.bin / "mount", '#!/bin/sh\necho "usb on $TEST_ROOT/mnt/exUDISK type vfat (rw)"\n')
        self.put(self.bin / "pidof", "#!/bin/sh\nexit 1\n")
        self.put(self.bin / "dd", "#!/bin/sh\nexit 0\n")

    def put(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o755)

    def run_script(self, script="run.sh", code=0):
        result = subprocess.run(["/bin/sh", str(self.source / script)], env=self.env,
                                cwd=self.source, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def menu(self, filename="before.toml", action="Install"):
        config = tomllib.loads((self.root / filename).read_text())
        return config["submenus"]["Utils"][f"{action} root shell (port 4567)"]

    def test_stock_menu_and_shared_helpers_are_staged(self):
        self.run_script()
        entry = self.menu()
        self.assertNotIn("disabled", entry)
        self.assertNotIn("disabled_reason", entry)
        self.assertEqual(entry["index"], 1)
        for name in ("bind-shell", "shell-service.sh"):
            self.assertTrue((self.payload / name).is_file())
        self.assertIn("Starting CC1 installer GUI", (self.usb / "OCInstaller.log").read_text())


    def test_install_and_remove_refresh_only_on_reload(self):
        for installed in (False, True):
            with self.subTest(installed=installed):
                for name in ("before.toml", "after.toml"):
                    (self.root / name).unlink(missing_ok=True)
                init = self.root / "etc/init.d/oc-shell"
                init.unlink(missing_ok=True)
                if installed:
                    init.touch()
                self.env["REFRESH"] = "1"
                self.run_script()
                self.menu(action="Remove" if installed else "Install")
                self.menu("after.toml", action="Install" if installed else "Remove")
                self.assertEqual(init.exists(), not installed)
                self.assertFalse((self.payload / ".recovery.pid").exists())
                self.assertFalse((self.payload / ".reload").exists())
        self.assertIn(str(self.root / "user-resource/sig-dump-emmc"),
                      (self.root / "service-calls").read_text())


    def test_busy_shell_action_reports_error_without_installing(self):
        self.env.update(ROOT_SHELL_BUSY="1", RUN_SHELL="1")
        self.run_script()
        entry = self.menu()
        self.assertNotIn("disabled", entry)
        self.assertTrue(entry["tasks"][0]["show_stdout"])
        self.assertTrue(entry["tasks"][0]["stop_on_failure"])
        self.assertEqual((self.root / "task-status").read_text(), "1\n")
        self.assertIn(NOTE, (self.usb / "OCInstaller.log").read_text())
        self.assertFalse((self.root / "etc/init.d/oc-shell").exists())

    def test_gui_failure_is_not_hidden(self):
        self.env["GUI_RC"] = "13"
        self.run_script(code=13)


class PackageTest(unittest.TestCase):
    def test_cc1_scripts_are_posix_and_lint_clean(self):
        for name in ("run.sh", "install-shell.sh"):
            path = ROOT / "install_opencentauri" / name
            for command in (["sh", "-n", str(path)], ["shellcheck", "-s", "sh", str(path)]):
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_cc1_zip_contains_real_shared_utilities_and_exploit(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("make_cc1", ROOT / "tools/make_cc1.py")
        packer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packer)
        with tempfile.TemporaryDirectory(prefix="oc-cc1-package-") as tmp:
            archive = packer.build(tmp)
            with zipfile.ZipFile(archive) as zf:
                names = set(zf.namelist())
                prefix = "install_opencentauri/"
                for name in ("install-shell.sh", "shell-service.sh",
                             "log-task.sh", "bind-shell"):
                    self.assertIn(prefix + name, names)
                self.assertTrue(any(Path(n).name.startswith("IMPORT_ME_DO_NOT_PRINT") for n in names))
                self.assertFalse(any(n.endswith(".log") for n in names))
                for name in ("recovery", "bind-shell", "decrypt", "utf8-fix", "wifi-network-config-tool"):
                    data = zf.read(prefix + name)
                    self.assertEqual(data[:6], b"\x7fELF\x01\x01", name)
                    self.assertEqual(struct.unpack_from("<HH", data, 16), (2, 0x28), name)
                    self.assertEqual((zf.getinfo(prefix + name).external_attr >> 16) & 0o777, 0o755)
                self.assertEqual(zf.read(prefix + "recovery"), (ROOT / "install_c2/recovery").read_bytes())
                for staged, shared in (("shell-service.sh", "install-shell.sh"),
                                       ("log-task.sh", "log-task.sh")):
                    self.assertEqual(zf.read(prefix + staged), (ROOT / "install_c2" / shared).read_bytes())
                config = tomllib.loads(zf.read(prefix + "config.toml").decode())
                for group in config["submenus"].values():
                    indexes = [entry["index"] for entry in group.values()]
                    self.assertEqual(len(indexes), len(set(indexes)))
                    for entry in group.values():
                        for task in entry["tasks"] + entry.get("completed_actions", []):
                            for arg in task["command"]:
                                if arg.startswith("/user-resource/update_tmp/"):
                                    self.assertIn(prefix + Path(arg).name, names)


if __name__ == "__main__":
    unittest.main()
