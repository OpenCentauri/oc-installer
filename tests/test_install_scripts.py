#!/usr/bin/env python3
"""Run C2/CC2 scripts in a temporary tree with mocked hardware/network commands."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib
import zipfile

SOURCE = Path(__file__).resolve().parents[1] / "install_c2"
SCRIPTS = (
    "run.sh", "install-shell.sh", "check-boot-slot.sh", "download-firmware.sh",
    "install-cosmos.sh", "install-cosmos-local.sh",
)
SWU = b'070702\0sw-description\0software = { stable = { elegoo-centauri-carbon2.dtb }; };'


def exercise(shell):
    with tempfile.TemporaryDirectory(prefix="oc-scripts-") as directory:
        root = Path(directory)
        payload = root / "opt/usr/oc-installer"
        commands = root / "bin"
        env = dict(os.environ, PATH=f"{commands}:/usr/bin:/bin", TEST_ROOT=str(root),
                   BOOT="bootA", NEXT="A", KEY="", SWUPDATE_RC="0", DOWNLOAD="ok",
                   GUI_RC="0", REFRESH="0", FAIL_COPY="0", FAIL_START="0", FAIL_STOP="0")

        def put(path, content, executable=False):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            if executable:
                path.chmod(0o755)

        # Redirect every write outside the payload before executing anything.
        for name in SCRIPTS:
            text = (SOURCE / name).read_text()
            for prefix in ("/opt/usr", "/opt/bin", "/user-resource", "/etc", "/app", "/mnt", "/proc/net", "/proc/cmdline",
                           "/proc/sys/vm/drop_caches"):
                text = text.replace(prefix, str(root) + prefix)
            put(payload / name, text)
        put(payload / "config.toml", (SOURCE / "config.toml").read_text())
        put(payload / "swupdate_public_cosmos.pem", "mock key\n")
        put(root / "proc/cmdline", "console=ttyS0 root=/dev/mmcblk0p7 rootwait\n")
        put(root / "proc/net/tcp", "")
        put(root / "proc/sys/vm/drop_caches", "")
        (root / "etc/init.d").mkdir(parents=True)
        (root / "etc/rc.d").mkdir()
        put(root / "etc/rc.common", 'kill() { [ "$FAIL_STOP" = 0 ] && rm -f "$TEST_ROOT/running"; }\n. "$1"\nshift\n"$@"\n')
        put(payload / "bind-shell", '#!/bin/sh\n[ "$FAIL_START" = 0 ] && touch "$TEST_ROOT/running"\n', True)
        stubs = {
            "fw_printenv": 'case "$1" in\nboot_partition) [ -n "$BOOT" ] || exit 1; echo "boot_partition=$BOOT";;\nsystemAB_next) [ -n "$NEXT" ] || exit 1; echo "systemAB_next=$NEXT";;\nesac\n',
            "pidof": '[ "$1" = bind-shell ] && [ -f "$TEST_ROOT/running" ] || exit 1\necho 123456\n',
            "swupdate": 'if [ "$1" = -h ]; then echo "usage $KEY"; exit 1; fi\nprintf "%s\\n" "$@" >> "$TEST_ROOT/flash.log"\nexit "$SWUPDATE_RC"\n',
            "sync": ':\n',
            "mount": 'echo "usb on $TEST_ROOT/mnt/exUDISK type vfat (rw)"\n',
            "dd": 'if [ "$1" = if=/dev/zero ]; then exit 0; fi\nexec /usr/bin/busybox dd "$@"\n',
            "cp": '[ "$FAIL_COPY" = 0 ] || exit 23\nexec /usr/bin/busybox cp "$@"\n',
            "curl": 'printf "%s\\n" "$4" >> "$TEST_ROOT/download.log"\ncase "$4" in\n*nightly.link*) [ "$DOWNLOAD" != offline ] && [ "$DOWNLOAD" != fallback ] || exit 22; cp "$TEST_ROOT/nightly.zip" "$3";;\n*) [ "$DOWNLOAD" != offline ] || { echo partial > "$3"; exit 22; }; cp "$TEST_ROOT/fallback.swu" "$3";;\nesac\n',
        }
        for name, text in stubs.items():
            put(commands / name, "#!/bin/sh\n" + text, True)
        # Exercise BusyBox's actual utility flags too, not just its shell parser.
        for name in ("grep", "sed", "tr", "unzip", "rm", "mkdir", "mv", "chmod", "ln", "cat", "sleep", "touch", "dirname", "sh"):
            (commands / name).symlink_to("/usr/bin/busybox")

        def run(name, *args, code=0):
            result = subprocess.run(shell + [str(payload / name), *args], env=env,
                                    cwd=payload, capture_output=True, text=True, timeout=20)
            assert result.returncode == code, (name, result.returncode, result.stdout, result.stderr)
            return result.stdout + result.stderr

        def flashed():
            log = root / "flash.log"
            text = log.read_text() if log.exists() else ""
            log.unlink(missing_ok=True)
            return text

        # Fail closed on unknown roots, bad environment, and either mismatch.
        for boot, next_slot, cmdline, code, selection in (
            ("bootA", "B", "root=/dev/mmcblk0p7", 0, "now_A_next_B"),
            ("bootB", "A", "root=/dev/mmcblk0p8 rootwait", 0, "now_B_next_A"),
            ("", "A", "console=x root=/dev/mmcblk0p7 ro", 0, "now_A_next_B"),
            ("", "B", "root=/dev/mmcblk0p8", 0, "now_B_next_A"),
            ("bootB", "B", "root=/dev/mmcblk0p7", 1, "disagrees"),
            ("bootA", "A", "root=/dev/mmcblk0p8", 1, "disagrees"),
            ("broken", "A", "root=/dev/mmcblk0p7", 1, "invalid"),
            ("bootA", "A", "root=/dev/mmcblk0p70", 1, "cannot determine"),
            ("bootA", "A", "root=PARTUUID=unknown", 1, "cannot determine"),
            ("bootA", "A", "root=/dev/mmcblk0p7 root=/dev/mmcblk0p8", 1, "cannot determine"),
            ("", "", "root=/dev/mmcblk0p7", 1, ""),
        ):
            env.update(BOOT=boot, NEXT=next_slot)
            put(root / "proc/cmdline", cmdline + "\n")
            assert selection in run("check-boot-slot.sh", code=code)
        env.update(BOOT="bootA", NEXT="A")

        usb = root / "mnt/exUDISK/install_c2/update.swu"
        usb.parent.mkdir(parents=True)
        download = root / "opt/usr/update.swu"
        for local in (False, True):
            target = usb if local else download
            name = "install-cosmos-local.sh" if local else "install-cosmos.sh"
            for data, boot, swupdate_rc, code in (
                (SWU, "bootA", "0", 0),
                (SWU.replace(b"carbon2", b"carbon"), "bootA", "0", 1),
                (SWU, "bootB", "0", 1),
                (SWU, "bootA", "17", 17),
            ):
                target.write_bytes(data)
                env.update(BOOT=boot, SWUPDATE_RC=swupdate_rc)
                run(name, code=code)
                log = flashed()
                assert bool(log) == (code in (0, 17)), (name, code, log)
                if log:
                    assert "stable,now_A_next_B" in log and "-k" not in log
                assert target.exists() == local
            target.unlink(missing_ok=True)
        env.update(BOOT="bootA", SWUPDATE_RC="0", KEY="-k public-key")
        usb.write_bytes(SWU.replace(b"stable =", b"cosmos\t="))
        run("install-cosmos-local.sh")
        log = flashed()
        assert "cosmos,now_A_next_B" in log and "-k\n./swupdate_public_cosmos.pem" in log
        usb.unlink()
        run("install-cosmos-local.sh", code=1)
        run("install-cosmos.sh", code=1)
        assert not flashed()

        # Exact ZIP member only; stale files are neither selected nor deleted.
        stale = root / "opt/usr/cosmos-stale.swu"
        stale.write_bytes(b"stale")
        (root / "fallback.swu").write_bytes(SWU + b"fallback")
        for mode, member, expected_code in (
            ("ok", "cosmos-centauri-carbon-2.swu", 0),
            ("ok", "wrong-machine.swu", 0),
            ("fallback", "cosmos-centauri-carbon-2.swu", 0),
            ("offline", "cosmos-centauri-carbon-2.swu", 22),
        ):
            with zipfile.ZipFile(root / "nightly.zip", "w") as archive:
                archive.writestr(member, SWU)
            env["DOWNLOAD"] = mode
            download.write_bytes(b"old download")
            run("download-firmware.sh", code=expected_code)
            assert not (download.parent / "cosmos-firmware.zip").exists()
            assert not (download.parent / "update.swu.part").exists()
            assert stale.read_bytes() == b"stale"
            if expected_code:
                assert not download.exists()
            else:
                expected = SWU if mode == "ok" and member.startswith("cosmos-") else SWU + b"fallback"
                assert download.read_bytes() == expected
        urls = (root / "download.log").read_text()
        assert "https://nightly.link/OpenCentauri/cosmos/workflows/build.yml/main/centauri-carbon-2%20Firmware.zip" in urls
        assert "https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu" in urls

        # Native rc.common dispatch, immediate start, OTA restore, removal, failures.
        init = root / "etc/init.d/oc-shell"
        save = root / "opt/usr/oc-root-shell"
        put(root / "etc/hotplug.d/block/12-shell", "legacy")
        put(root / "app/bind-shell", "legacy")
        put(root / "etc/rc.local", "keep\n# BEGIN oc-installer bind-shell\nlegacy\n# END oc-installer bind-shell\nexit 0\n")
        for table, address in (("tcp", "00000000"), ("tcp6", "0" * 32)):
            put(root / "proc/net" / table, f"0: {address}:11D7 00000000:0000 0A\n")
            output = run("install-shell.sh", code=1)
            assert "Root shell already installed/running" in output
            assert not init.exists() and not save.exists()
            assert (root / "etc/hotplug.d/block/12-shell").read_text() == "legacy"
            assert (root / "app/bind-shell").read_text() == "legacy"
            put(root / "proc/net" / table, "")
        (root / "proc/net/tcp").unlink()
        (root / "proc/net/tcp6").unlink()
        assert "cannot check root shell port" in run("install-shell.sh", code=1)
        assert (root / "etc/hotplug.d/block/12-shell").read_text() == "legacy"
        # An established connection is not a listener on this port.
        put(root / "proc/net/tcp", "0: 00000000:11D7 00000000:0000 01\n")
        env["FAIL_COPY"] = "1"
        run("install-shell.sh", code=23)
        assert not init.exists()
        assert not (root / "etc/hotplug.d/block/12-shell").exists()
        assert not (root / "app/bind-shell").exists()
        assert (root / "etc/rc.local").read_text() == "keep\nexit 0\n"
        env.update(FAIL_COPY="0", FAIL_START="1")
        run("install-shell.sh", code=1)
        assert init.exists() and not (root / "running").exists()
        run("install-shell.sh")
        env["FAIL_START"] = "0"
        run("install-shell.sh")
        assert (root / "running").exists()
        assert init.read_text().startswith(f"#!/bin/sh {root}/etc/rc.common\n")
        assert not (root / "opt/usr/sig-dump-emmc").exists()
        for link in ("S98oc-shell", "K98oc-shell"):
            assert (root / "etc/rc.d" / link).resolve() == init
        for path in (init, save / "reinstall.sh"):
            subprocess.run(["shellcheck", "-s", "sh", str(path)], check=True)
        init.unlink()
        (root / "opt/bin/bind-shell").unlink()
        (root / "running").unlink()
        subprocess.run(shell + [str(save / "reinstall.sh")], env=env, check=True, timeout=10)
        assert init.exists() and (root / "running").exists()
        env["FAIL_STOP"] = "1"
        run("install-shell.sh", code=1)
        assert init.exists()
        env["FAIL_STOP"] = "0"
        put(root / "proc/net/tcp", "0: 00000000:11D7 00000000:0000 0A\n")
        run("install-shell.sh")
        assert not init.exists() and not save.exists() and not (root / "running").exists()
        put(root / "proc/net/tcp", "")
        assert not (root / "opt/bin/bind-shell").exists()
        assert not any((root / "etc/rc.d").iterdir())

        # CC1 uses the same service with its own OTA-persistent storage.
        cc1_save = root / "user-resource/oc-root-shell"
        run("install-shell.sh", str(cc1_save))
        assert init.exists() and (cc1_save / "reinstall.sh").is_file()
        assert not (root / "user-resource/sig-dump-emmc").exists()
        assert (root / "running").exists()
        run("install-shell.sh", str(cc1_save))
        assert not init.exists() and not cc1_save.exists()
        run("install-shell.sh", "/unsupported", code=1)
        assert not init.exists()

        # Reload is user-initiated after completion, not a timer that hides output.
        put(payload / "recovery", '''#!/bin/sh
if [ ! -f "$TEST_ROOT/gui-before.toml" ]; then
    cp config.toml "$TEST_ROOT/gui-before.toml"
    if [ "$REFRESH" = 1 ]; then
        sh ./install-shell.sh || exit 99
        sh ./run.sh reload
        exit 98
    fi
else
    cp config.toml "$TEST_ROOT/gui-after.toml"
fi
exit "$GUI_RC"
''', True)
        env["REFRESH"] = "1"
        run("run.sh", str(payload))
        for filename, action in (("gui-before.toml", "Install"), ("gui-after.toml", "Remove")):
            cfg = tomllib.loads((root / filename).read_text())
            label = f"{action} root shell (port 4567)"
            entry = cfg["submenus"]["Utils"][label]
            assert entry["tasks"][0]["name"] == label
            assert entry["completed_actions"][0]["command"][-1] == "reload"
        assert not (payload / ".recovery.pid").exists()
        assert not (payload / ".reload").exists()
        env.update(REFRESH="0", GUI_RC="13")
        run("run.sh", str(payload), code=13)
        run("install-shell.sh")
        run("run.sh", str(payload), code=13)
        assert "Install root shell (port 4567)" in tomllib.loads((payload / "config.toml").read_text())["submenus"]["Utils"]
        print(f"PASS: {' '.join(shell)}: slot guards, shared flash/cleanup, download, shell lifecycle, GUI reload")


if __name__ == "__main__":
    assert shutil.which("busybox"), "busybox is required for these compatibility checks"
    cfg = tomllib.loads((SOURCE / "config.toml").read_text())
    for group in cfg["submenus"].values():
        indexes = [entry["index"] for entry in group.values()]
        assert len(indexes) == len(set(indexes))
        for entry in group.values():
            for task in entry["tasks"]:
                assert task["stop_on_failure"] is True
            for task in entry["tasks"] + entry.get("completed_actions", []):
                for part in task["command"]:
                    if part.startswith("/opt/usr/oc-installer/"):
                        assert (SOURCE / Path(part).name).is_file(), part
    for shell in (["/bin/sh"], ["/usr/bin/busybox", "sh"]):
        exercise(shell)
