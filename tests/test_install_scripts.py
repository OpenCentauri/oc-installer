#!/usr/bin/env python3
"""Run C2/CC2 scripts in a temporary tree with mocked hardware/network commands."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import tomllib

SOURCE = Path(__file__).resolve().parents[1] / "install_c2"
SCRIPTS = (
    "run.sh", "install-shell.sh", "check-boot-slot.sh", "download-firmware.sh",
    "install-cosmos.sh", "install-cosmos-local.sh", "log-task.sh", "reboot.sh",
)
SWU = b'070702\0sw-description\0software = { stable = { elegoo-centauri-carbon2.dtb }; };'


def exercise(shell):
    with tempfile.TemporaryDirectory(prefix="oc-scripts-") as directory:
        root = Path(directory)
        payload = root / "oc-installer"
        commands = root / "bin"
        env = dict(os.environ, PATH=f"{commands}:/usr/bin:/bin", TEST_ROOT=str(root),
                   BOOT="bootA", NEXT="A", KEY="", SWUPDATE_RC="0", DOWNLOAD="ok",
                   GUI_RC="0", REFRESH="0", FAIL_COPY="0", FAIL_START="0", FAIL_STOP="0",
                   USB_MOUNTED="1", FAIL_CLEANUP="0")

        def put(path, content, executable=False):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            if executable:
                path.chmod(0o755)

        # Redirect every write outside the payload before executing anything.
        for name in SCRIPTS:
            text = (SOURCE / name).read_text()
            for prefix in ("/oc-installer", "/opt/usr", "/opt/bin", "/user-resource", "/etc", "/app", "/mnt", "/proc/net", "/proc/cmdline",
                           "/proc/sys/vm/drop_caches"):
                text = text.replace(prefix, str(root) + prefix)
            put(payload / name, text)
        put(payload / "config.toml", (SOURCE / "config.toml").read_text())
        put(payload / "swupdate_public_cosmos.pem", "mock key\n")
        put(root / "proc/cmdline", "console=ttyS0 root=/dev/mmcblk0p7 rootwait\n")
        put(root / "proc/net/tcp", "")
        put(root / "proc/sys/vm/drop_caches", "")
        (root / "etc/init.d").mkdir(parents=True)
        (root / "opt/usr").mkdir(parents=True)
        (root / "etc/rc.d").mkdir()
        put(root / "etc/rc.common", 'kill() { [ "$FAIL_STOP" = 0 ] && rm -f "$TEST_ROOT/running"; }\n. "$1"\nshift\n"$@"\n')
        bind_stub = '#!/bin/sh\n[ "$FAIL_START" = 0 ] || exit 1\nif [ "${TEMP_SHELL:-0}" = 1 ]; then\n    echo $$ > "$TEST_ROOT/temp-pid"\n    exec /usr/bin/sleep 30\nfi\ntouch "$TEST_ROOT/running"\n'
        put(payload / "bind-shell", bind_stub, True)
        stubs = {
            "fw_printenv": 'case "$1" in\nboot_partition) [ -n "$BOOT" ] || exit 1; echo "boot_partition=$BOOT";;\nsystemAB_next) [ -n "$NEXT" ] || exit 1; echo "systemAB_next=$NEXT";;\nesac\n',
            "pidof": '[ "$1" = bind-shell ] && [ -f "$TEST_ROOT/running" ] || exit 1\necho 123456\n',
            "swupdate": 'if [ "$1" = -h ]; then echo "usage $KEY"; exit 1; fi\nprintf "%s\\n" "$@" >> "$TEST_ROOT/flash.log"\nexit "$SWUPDATE_RC"\n',
            "sync": ':\n',
            "mount": '[ "$USB_MOUNTED" = 1 ] || exit 0\necho "usb on $TEST_ROOT/mnt/exUDISK type vfat (rw)"\n',
            "rm": '[ "$FAIL_CLEANUP" != 1 ] || { for arg do [ "$arg" != "$TEST_ROOT/oc-installer" ] || exit 23; done; }\nexec /usr/bin/busybox rm "$@"\n',
            "reboot": '[ ! -e "$TEST_ROOT/oc-installer" ] || exit 99\necho reboot >> "$TEST_ROOT/reboots"\n',
            "dd": 'if [ "$1" = if=/dev/zero ]; then exit 0; fi\nexec /usr/bin/busybox dd "$@"\n',
            "cp": '[ "$FAIL_COPY" = 0 ] || exit 23\nexec /usr/bin/busybox cp "$@"\n',
        }
        for name, text in stubs.items():
            put(commands / name, "#!/bin/sh\n" + text, True)
        # download-firmware.sh invokes the bundled static curl by payload path.
        put(payload / "ca-certificates.crt", "mock ca bundle\n")
        curl_stub = '''#!/bin/sh
[ "$1" = --cacert ] && [ "$2" = "$(dirname "$0")/ca-certificates.crt" ] || exit 24
[ "$3" = -sSfL ] && [ "$4" = -o ] || exit 26
echo "$6" >> "$TEST_ROOT/download.log"
[ "$6" = "https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu" ] || exit 25
[ "$DOWNLOAD" != offline ] || { echo partial > "$5"; exit 22; }
cp "$TEST_ROOT/opt/usr/official.swu" "$5"
'''
        put(payload / "curl", curl_stub, True)
        # Exercise BusyBox's actual utility flags too, not just its shell parser.
        for name in ("grep", "sed", "tr", "mkdir", "mv", "chmod", "ln", "cat", "tee", "date", "mktemp",
                     "sleep", "touch", "dirname", "sh", "awk", "tail"):
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

        # Preserve stdout, stderr and child exit status while logging to USB.
        usb_log = root / "mnt/exUDISK/OCInstaller.log"
        usb_log.parent.mkdir(parents=True)
        output = run("log-task.sh", "/bin/sh", "-c", "echo logged-stdout; echo logged-stderr >&2; exit 17", code=17)
        assert "logged-stdout" in output and "logged-stderr" in output
        assert "logged-stdout" in usb_log.read_text() and "logged-stderr" in usb_log.read_text()
        assert "EXIT 17" in usb_log.read_text()
        assert not list(usb_log.parent.glob(".oc-installer-task-status-*"))
        env["USB_MOUNTED"] = "0"
        run("log-task.sh", "/bin/sh", "-c", 'touch "$TEST_ROOT/must-not-run"', code=1)
        assert not (root / "must-not-run").exists()
        env["USB_MOUNTED"] = "1"
        saved_log = usb_log.with_suffix(".saved")
        usb_log.rename(saved_log)
        usb_log.symlink_to("/dev/full")
        run("log-task.sh", "/bin/sh", "-c", 'touch "$TEST_ROOT/must-not-run"', code=1)
        assert not (root / "must-not-run").exists()
        usb_log.unlink()
        saved_log.rename(usb_log)
        (commands / "tee").unlink()
        put(commands / "tee", "#!/bin/sh\ncat >/dev/null\nexit 19\n", True)
        run("log-task.sh", "/bin/sh", "-c", "echo writer-failure", code=19)
        (commands / "tee").unlink()
        (commands / "tee").symlink_to("/usr/bin/busybox")

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
                    # word-wise: a scratch path may contain "-k" by chance
                    assert "stable,now_A_next_B" in log and "-k" not in log.split()
                assert target.exists() == local
            target.unlink(missing_ok=True)
        env.update(BOOT="bootA", SWUPDATE_RC="0", KEY="-k public-key")
        usb.write_bytes(SWU + b'\ncentauri-carbon-2 = { cosmos = { ref = "#./../stable"; }; };')
        run("install-cosmos-local.sh")
        log = flashed()
        assert "stable,now_A_next_B" in log and "-k\n./swupdate_public_cosmos.pem" in log
        usb.unlink()
        run("install-cosmos-local.sh", code=1)
        run("install-cosmos.sh", code=1)
        assert not flashed()

        # Do not invoke the vendor retry loop or mutate its environment mailbox.
        put(commands / "swupdate_cmd.sh", "#!/bin/sh\nexit 99\n", True)
        env["KEY"] = ""
        usb.write_bytes(SWU)
        run("install-cosmos-local.sh")
        log = flashed()
        assert log.startswith("-i") and "-e\nstable,now_A_next_B" in log and "-k" not in log.split()
        usb.unlink()

        # Stock uses top-level stable, not the machine-specific cosmos alias.
        # The ref links and signature must remain untouched on every path.
        original = SWU + b'\ncentauri-carbon-2 = { cosmos = { now_A_next_B = { ref = "#./../../stable/now_A_next_B"; }; }; };'
        for boot, part, selection in (("bootA", 7, "now_A_next_B"),
                                      ("bootB", 8, "now_B_next_A")):
            env["BOOT"] = boot
            put(root / "proc/cmdline", f"root=/dev/mmcblk0p{part}\n")
            usb.write_bytes(original)
            run("install-cosmos-local.sh")
            log = flashed().split()
            assert f"stable,{selection}" in log and "-k" not in log
            assert usb.read_bytes() == original
        env["BOOT"] = "bootA"
        put(root / "proc/cmdline", "root=/dev/mmcblk0p7\n")
        (commands / "swupdate_cmd.sh").unlink()

        # Signature-capable updaters must receive the original description.
        env["KEY"] = "-k public-key"
        usb.write_bytes(original)
        run("install-cosmos-local.sh")
        assert "-k" in flashed().split()
        assert usb.read_bytes() == original
        usb.unlink()

        # Local installs accept root-level names, with the old folder as fallback.
        primary = root / "mnt/exUDISK"
        secondary = root / "mnt/UDISK"
        secondary.mkdir()
        for mountpoint in (primary, secondary):
            for relative in ("update.swu", "cosmos-centauri-carbon-2.swu", "install_c2/update.swu"):
                candidate = mountpoint / relative
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_bytes(SWU)
                run("install-cosmos-local.sh")
                args = flashed().splitlines()
                assert args[:2] == ["-i", str(candidate)], args
                assert candidate.read_bytes() == SWU
                candidate.unlink()
        root_update = primary / "update.swu"
        root_named = primary / "cosmos-centauri-carbon-2.swu"
        for candidate in (root_update, root_named, usb):
            candidate.write_bytes(SWU)
        run("install-cosmos-local.sh")
        assert flashed().splitlines()[:2] == ["-i", str(root_update)]
        # An explicitly selected invalid SWU must fail, not flash another file.
        root_update.write_bytes(SWU.replace(b"carbon2", b"carbon"))
        run("install-cosmos-local.sh", code=1)
        assert not flashed()
        root_update.write_bytes(b"")
        run("install-cosmos-local.sh")
        assert flashed().splitlines()[:2] == ["-i", str(root_named)]
        root_update.unlink()
        root_update.mkdir()
        run("install-cosmos-local.sh")
        assert flashed().splitlines()[:2] == ["-i", str(root_named)]
        root_update.rmdir()
        for candidate in (root_named, usb):
            assert candidate.read_bytes() == SWU
            candidate.unlink()
        ignored = primary / "cosmos-centauri-carbon-1.swu"
        ignored.write_bytes(SWU)
        run("install-cosmos-local.sh", code=1)
        assert not flashed() and ignored.read_bytes() == SWU
        ignored.unlink()

        # The official CC2 release asset is the only URL attempted.
        stale = root / "opt/usr/cosmos-stale.swu"
        stale.write_bytes(b"stale")
        (root / "opt/usr/official.swu").write_bytes(SWU + b"official")
        for mode, code in (("ok", 0), ("offline", 22)):
            env["DOWNLOAD"] = mode
            download.write_bytes(b"old download")
            run("download-firmware.sh", code=code)
            assert not (download.parent / "update.swu.part").exists()
            assert stale.read_bytes() == b"stale"
            if code:
                assert not download.exists()
            else:
                assert download.read_bytes() == SWU + b"official"
        urls = (root / "download.log").read_text().splitlines()
        official = "https://github.com/OpenCentauri/cosmos/releases/download/0.0.0/cosmos-centauri-carbon-2.swu"
        assert urls == [official, official]
        assert all("nightly.link" not in url for url in urls)

        # Native rc.common dispatch, immediate start, OTA restore, removal, failures.
        init = root / "etc/init.d/oc-shell"
        save = root / "opt/usr/oc-root-shell"
        put(root / "etc/hotplug.d/block/12-shell", "legacy")
        put(root / "app/bind-shell", "legacy")
        put(root / "etc/rc.local", "keep\n# BEGIN oc-installer bind-shell\nlegacy\n# END oc-installer bind-shell\nexit 0\n")
        for table, address in (("tcp", "00000000"), ("tcp6", "0" * 32)):
            put(root / "proc/net" / table, f"0: {address}:11D7 00000000:0000 0A\n")
            for args in ((), ("--temporary",)):
                output = run("install-shell.sh", *args, code=1)
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
        # The extracted copy outlives the task/logger, with no persistence writes.
        cc1_payload = root / "user-resource/update_tmp"
        put(cc1_payload / "shell-service.sh", (payload / "install-shell.sh").read_text())
        put(cc1_payload / "bind-shell", bind_stub, True)
        env["TEMP_SHELL"] = "1"
        for script in (payload / "install-shell.sh", cc1_payload / "shell-service.sh"):
            if script.parent == cc1_payload:
                put(init, "keep existing service\n")
            try:
                output = run("log-task.sh", "/bin/sh", str(script), "--temporary")
                assert "Temporary root shell live on port 4567 until reboot" in output
                pid = int((root / "temp-pid").read_text())
                for fd in (0, 1, 2):
                    assert os.readlink(f"/proc/{pid}/fd/{fd}") == "/dev/null"
                os.kill(pid, signal.SIGHUP)
                time.sleep(0.05)
                assert Path(f"/proc/{pid}/stat").read_text().split()[2] != "Z"
                assert not save.exists() and not (root / "user-resource/oc-root-shell").exists()
                assert not (root / "opt/bin/bind-shell").exists()
                assert not any((root / "etc/rc.d").iterdir())
                assert (root / "etc/hotplug.d/block/12-shell").read_text() == "legacy"
                assert (root / "app/bind-shell").read_text() == "legacy"
                if script.parent == cc1_payload:
                    assert init.read_text() == "keep existing service\n"
                else:
                    assert not init.exists()
            finally:
                pid_file = root / "temp-pid"
                if pid_file.exists():
                    try:
                        os.kill(int(pid_file.read_text()), signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    pid_file.unlink()
                init.unlink(missing_ok=True)
        env.update(TEMP_SHELL="0", FAIL_START="1")
        assert "temporary root shell failed to start" in run("install-shell.sh", "--temporary", code=1)
        assert not init.exists() and not save.exists()
        env["FAIL_START"] = "0"
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
        assert "Root shell already installed/running" in run("install-shell.sh", "--temporary", code=1)
        assert init.exists() and save.exists() and (root / "running").exists()
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
        run("run.sh")
        for filename, action in (("gui-before.toml", "Install"), ("gui-after.toml", "Remove")):
            cfg = tomllib.loads((root / filename).read_text())
            label = f"{action} root shell (port 4567)"
            entry = cfg["submenus"]["Utils"][label]
            assert entry["tasks"][0]["name"] == label
            assert entry["completed_actions"][0]["command"][-1] == "reload"
        assert not (payload / ".recovery.pid").exists()
        assert not (payload / ".reload").exists()
        env.update(REFRESH="0", GUI_RC="13")
        run("run.sh", code=13)
        run("install-shell.sh")
        run("run.sh", code=13)
        assert "Install root shell (port 4567)" in tomllib.loads((payload / "config.toml").read_text())["submenus"]["Utils"]
        assert not (payload / "recovery.log").exists()
        assert "Starting installer GUI" in usb_log.read_text()

        # Every reboot first removes the extraction; failed cleanup forbids reboot.
        env["FAIL_CLEANUP"] = "1"
        run("log-task.sh", "/bin/sh", str(payload / "reboot.sh"), code=23)
        assert payload.exists() and not (root / "reboots").exists()
        env["FAIL_CLEANUP"] = "0"
        run("log-task.sh", "/bin/sh", str(payload / "reboot.sh"))
        assert not payload.exists()
        assert (root / "reboots").read_text() == "reboot\n"
        assert "Installer cleanup complete; reboot requested." in usb_log.read_text()
        assert not list(usb_log.parent.glob(".oc-installer-task-status-*"))
        print(f"PASS: {' '.join(shell)}: guards, USB logs/status, shell lifecycle, GUI reload, cleanup before reboot")


if __name__ == "__main__":
    assert shutil.which("busybox"), "busybox is required for these compatibility checks"
    cfg = tomllib.loads((SOURCE / "config.toml").read_text())
    utils = cfg["submenus"]["Utils"]
    temporary = utils["Start temp root shell (port 4567)"]
    assert temporary["index"] == 1
    assert temporary["tasks"][0]["command"][-2:] == ["/oc-installer/install-shell.sh", "--temporary"]
    assert utils["Install root shell (port 4567)"]["index"] == 2
    for group in cfg["submenus"].values():
        indexes = [entry["index"] for entry in group.values()]
        assert len(indexes) == len(set(indexes))
        for entry in group.values():
            for task in entry["tasks"]:
                assert task["stop_on_failure"] is True
            for task in entry["tasks"] + entry.get("completed_actions", []):
                for part in task["command"]:
                    if part.startswith("/oc-installer/"):
                        assert (SOURCE / Path(part).name).is_file(), part
    for shell in (["/bin/sh"], ["/usr/bin/busybox", "sh"]):
        exercise(shell)
