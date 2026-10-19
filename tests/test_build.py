#!/usr/bin/env python3
"""Host-side tests for the C2/CC2 installer branch.

Default mode: pre-build checks (scripts, config, no-flash guards).
--post-build: verify build/ artifacts (SWU cpio structure, zip.sig round-trip).
"""
import hashlib
import io
import os
import re
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AES_KEY = "d14e150843e9d16893890756d8f77f674e161a8bebb8f720737ee60e7f8c7e68"
BUILD = os.path.join(ROOT, "build")

FAILS = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}: {name}" + (f" ({detail})" if detail and not ok else ""))
    if not ok:
        FAILS.append(name)


def sh_syntax():
    have_shellcheck = subprocess.run(["which", "shellcheck"], capture_output=True).returncode == 0
    for base in ("install_c2", "tools"):
        for f in sorted(os.listdir(os.path.join(ROOT, base))):
            if f.endswith(".sh"):
                p = os.path.join(ROOT, base, f)
                r = subprocess.run(["sh", "-n", p], capture_output=True)
                check(f"sh -n {base}/{f}", r.returncode == 0, r.stderr.decode())
                if have_shellcheck:
                    r = subprocess.run(["shellcheck", "-s", "sh", p], capture_output=True)
                    check(f"shellcheck {base}/{f}", r.returncode == 0, r.stdout.decode()[:200])


def vendored_binaries():
    for rel in ("build/recovery/recovery", "build/bind-shell/bind-shell",
                "build/pigz/pigz", "build/curl/curl"):
        with open(os.path.join(ROOT, rel), "rb") as f:
            data = f.read()
        arm = data[:4] == b"\x7fELF" and data[4:6] == b"\x01\x01" and \
            struct.unpack_from("<HH", data, 16) == (2, 0x28)
        check(f"{rel}: 32-bit ARM ELF", arm)
        if arm:
            offset = struct.unpack_from("<I", data, 28)[0]
            size, count = struct.unpack_from("<HH", data, 42)
            headers = [struct.unpack_from("<I", data, offset + i * size)[0] for i in range(count)]
            check(f"{rel}: statically linked", 2 not in headers and 3 not in headers)
    want = open(os.path.join(ROOT, "install_c2", "bind-shell.sha256")).read().split()[0]
    got = hashlib.sha256(open(os.path.join(ROOT, "build", "bind-shell", "bind-shell"), "rb").read()).hexdigest()
    check("bind-shell.sha256 matches binary", want == got)
    # Vendored CA bundle (curl.se/caextract); pinned so changes are reviewed.
    ca = hashlib.sha256(open(os.path.join(ROOT, "install_c2", "ca-certificates.crt"), "rb").read()).hexdigest()
    check("ca-certificates.crt matches pinned bundle",
          ca == "a41b5d356aea97a529fe27e0f7316d2f9d946d75927476cf9cf1b90637d00505")
    derived = subprocess.run(["openssl", "rsa", "-in",
                              os.path.join(ROOT, "keys", "swupdate_private.pem"), "-pubout"],
                             capture_output=True).stdout
    shipped = open(os.path.join(ROOT, "install_c2", "swupdate_public_cosmos.pem"), "rb").read()
    check("shipped pubkey matches vendored private key", derived == shipped)


def config():
    with open(os.path.join(ROOT, "install_c2", "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    check("config.toml parses", True)
    for group, entries in cfg.get("submenus", {}).items():
        idxs = []
        for entry, body in entries.items():
            idxs.append(body.get("index"))
            for task in body.get("tasks", []) + body.get("completed_actions", []):
                cmd = task.get("command", [])
                check(f"{entry}/{task['name']}: command is logged", cmd[:3] == ["/bin/sh", "/oc-installer/log-task.sh", "/bin/sh"])
                if task["name"] == "Reboot":
                    check(f"{entry}: reboot uses cleanup handler", cmd[-1] == "/oc-installer/reboot.sh")
                for part in cmd:
                    if part.startswith("/oc-installer/"):
                        exists = os.path.exists(os.path.join(
                            ROOT, "install_c2", part.rsplit("/", 1)[-1]))
                        check(f"{entry}: {os.path.basename(part)} exists in install_c2/", exists)
                    if part == "reboot" or part.endswith("; reboot"):
                        pass  # reboot allowed in GUI actions
        check(f"{group}: unique indexes", len(idxs) == len(set(idxs)), str(idxs))
    check("no plain Exit action", not any(k == "Exit" for k in cfg.get("scripts", {})))
    reboot = cfg["scripts"]["Exit and Reboot"]["tasks"][0]["command"]
    check("Exit and Reboot is logged and cleans extraction", reboot == ["/bin/sh", "/oc-installer/log-task.sh", "/bin/sh", "/oc-installer/reboot.sh"])


def no_flash_guards():
    # Only the explicit install actions may flash. The bootstrap clears
    # pending update flags but must not select a slot or write partitions.
    safe = ["tools/bootstrap-payload.sh", "tools/sw-description.bootstrap",
            "install_c2/run.sh", "install_c2/backup-emmc.sh",
            "install_c2/install-shell.sh", "install_c2/check-boot-slot.sh",
            "install_c2/download-firmware.sh",
            "install_opencentauri/run.sh", "install_opencentauri/install-shell.sh"]
    for rel in safe:
        with open(os.path.join(ROOT, rel)) as f:
            src = f.read()
        src_nocancel = re.sub(r'fw_setenv (swu_next|parts_clean) ""', "", src)
        check(f"{rel}: no fw_setenv besides swu-state cancels", "fw_setenv" not in src_nocancel)
        check(f"{rel}: no mmcblk writes", not re.search(r"of\s*=\s*[\"']?/dev/mmcblk", src))
    with open(os.path.join(ROOT, "tools", "sw-description.bootstrap")) as f:
        swd = f.read()
    for banned in ("bootenv", "images:", "swu_next", "boot_partition"):
        check(f"bootstrap descriptor: no {banned!r}", banned not in swd)
    check("bootstrap descriptor: has scripts:", "scripts:" in swd)
    check("bootstrap descriptor: stock shellscript handler", 'type = "shellscript"' in swd)


def read_newc(blob):
    """Parse cpio newc/crc, return [(name, data)]."""
    out = []
    off = 0
    while True:
        assert blob[off:off + 6] == b"070702", f"bad magic at {off}"
        fields = [int(blob[off + 6 + i * 8: off + 14 + i * 8], 16) for i in range(13)]
        namesz, filesize = fields[11], fields[6]
        name = blob[off + 110: off + 110 + namesz - 1].decode()
        off += 110 + namesz
        off += (4 - off % 4) % 4
        data = blob[off:off + filesize]
        assert len(data) == filesize and sum(data) & 0xffffffff == fields[12]
        out.append((name, data))
        off += filesize
        off += (4 - off % 4) % 4
        if name == "TRAILER!!!":
            break
    return out


def parse_eleg(blob):
    hdr = blob[:512]
    assert hdr[0:4] == b"ELEG"
    return {
        "type": hdr[4] & 0x7F, "encrypted": bool(hdr[4] & 0x80),
        "minor": struct.unpack("<H", hdr[6:8])[0],
        "filesize": struct.unpack("<Q", hdr[8:16])[0],
        "filename": hdr[0x10:0x40].split(b"\0")[0].decode(),
        "enc_filesize": struct.unpack("<Q", hdr[0xB0:0xB8])[0],
        "iv": hdr[0xA0:0xB0],
        "sha256": hdr[0xE0:0x100],
        "sig": hdr[0x100:0x200],
    }, blob[512:]


def aes_decrypt(iv, enc):
    r = subprocess.run(["openssl", "enc", "-d", "-aes-256-cbc", "-nopad",
                        "-K", AES_KEY, "-iv", iv.hex()], input=enc, capture_output=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def rsa_verify(pubkey, payload, sig):
    with tempfile.TemporaryDirectory() as tmp:
        key_path, sig_path = os.path.join(tmp, "public.pem"), os.path.join(tmp, "signature")
        with open(key_path, "wb") as f:
            f.write(pubkey)
        with open(sig_path, "wb") as f:
            f.write(sig)
        r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", key_path,
                            "-signature", sig_path], input=payload, capture_output=True)
        return r.returncode == 0


def post_build():
    swu_path = os.path.join(BUILD, "c2-tools-bootstrap.swu")
    check("SWU exists", os.path.exists(swu_path))
    if not os.path.exists(swu_path):
        return
    members = read_newc(open(swu_path, "rb").read())
    names = [n for n, _ in members]
    check("SWU member order", names == ["sw-description", "bootstrap-payload.sh", "TRAILER!!!"], str(names))
    swd = dict(members)["sw-description"].decode()
    for m in re.finditer(r'filename\s*=\s*"([^"]+)"', swd):
        check(f"descriptor filename {m.group(1)} is a cpio member", m.group(1) in names)

    # Embedded payload round-trip: bootstrap script carries install_c2/ as a
    # raw tar.gz at the byte offset baked into its tail line.
    boot = dict(members)["bootstrap-payload.sh"]
    m = re.search(rb"tail -c \+(\d+) ", boot)
    check("bootstrap has payload offset", m is not None)
    if m:
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(boot[int(m.group(1)) - 1:]), mode="r:gz") as tf:
            members_t = set(tf.getnames())
            check("payload has all runtime files",
                  {"run.sh", "config.toml", "recovery", "bind-shell", "pigz", "pigz-LICENSE.txt",
                   "check-boot-slot.sh", "backup-emmc.sh", "install-shell.sh", "log-task.sh", "reboot.sh",
                   "download-firmware.sh", "install-cosmos.sh",
                   "install-cosmos-local.sh", "swupdate_public_cosmos.pem",
                   "curl", "ca-certificates.crt", "curl-LICENSE.txt"} <= members_t,
                  str(sorted(members_t)))
            eh = tf.extractfile("recovery").read(20)
            check("payload recovery is 32-bit ARM ELF",
                  eh[:4] == b"\x7fELF" and struct.unpack("<H", eh[18:20])[0] == 0x28)

    pub = open(os.path.join(ROOT, "install_c2", "swupdate_public_cosmos.pem"), "rb").read()
    swu = open(swu_path, "rb").read()
    variants = sorted(f for f in os.listdir(BUILD) if f.endswith(".zip.sig"))
    check("two zip.sig variants", len(variants) == 2, str(variants))
    for v in variants:
        check(f"{v}: labeled from a tag, not untagged", "untagged" not in v)
        blob = open(os.path.join(BUILD, v), "rb").read()
        hdr, payload = parse_eleg(blob)
        check(f"{v}: outer type 4 plain", hdr["type"] == 4 and not hdr["encrypted"])
        expect_minor = 2 if v.startswith("cc2_") else 3
        check(f"{v}: minor {expect_minor}", hdr["minor"] == expect_minor, str(hdr["minor"]))
        check(f"{v}: filename has eeb001", "eeb001" in hdr["filename"] and "eeb001" in v)
        check(f"{v}: sha256 ok", hdr["sha256"] == hashlib.sha256(payload).digest())
        check(f"{v}: RSA sig verifies", rsa_verify(pub, payload, hdr["sig"]))
        zf = zipfile.ZipFile(io.BytesIO(payload))
        names = zf.namelist()
        check(f"{v}: zip members", "ota-package-list.json.sig" in names and
              any(n.endswith(".swu.sig") for n in names), str(names))
        swu_sig = zf.read(next(n for n in names if n.endswith(".swu.sig")))
        jhdr, jenc = parse_eleg(zf.read("ota-package-list.json.sig"))
        manifest = __import__("json").loads(aes_decrypt(jhdr["iv"], jenc)[:jhdr["filesize"]])
        check(f"{v}: manifest version", manifest["version"] == "42.42.42.42", manifest["version"])
        check(f"{v}: filename omits manifest version",
              f"-{manifest['version']}.zip.sig" not in v)
        check(f"{v}: manifest hash matches swu.sig",
              manifest["packages"][0]["hash"] == hashlib.sha256(swu_sig).hexdigest())
        check(f"{v}: manifest member name", manifest["packages"][0]["file"] == next(
            n for n in names if n.endswith(".swu.sig")))
        shdr, senc = parse_eleg(swu_sig)
        plain = aes_decrypt(shdr["iv"], senc)[:shdr["filesize"]]
        check(f"{v}: swu decrypts byte-equal", plain == swu)


def bootstrap_smoke():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("make_swu", os.path.join(ROOT, "tools/make_swu.py"))
    assert spec is not None and spec.loader is not None
    packer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(packer)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "install_c2").mkdir()
        (root / "tools").mkdir()
        (root / "bin").mkdir()
        for rel in ("build/pigz/pigz", "build/curl/curl",
                    "build/recovery/recovery", "build/bind-shell/bind-shell"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(b"test binary")
        (root / "usb").mkdir()
        template = Path(ROOT, "tools/bootstrap-payload.sh").read_text().replace(
            "dest=/oc-installer", f"dest={root / 'unpacked'}").replace(
            "/mnt/exUDISK", str(root / "usb"))
        (root / "tools/bootstrap-payload.sh").write_text(template)
        (root / "install_c2/run.sh").write_text(f"#!/bin/sh\nprintf gui >> '{root}/calls'\n")
        for name in ("killall", "fw_setenv"):
            stub = root / "bin" / name
            stub.write_text("#!/bin/sh\nexit 0\n")
            stub.chmod(0o755)
        stub = root / "bin/mount"
        stub.write_text(f"#!/bin/sh\nprintf 'usb on {root}/usb type vfat (rw)\\n'\n")
        stub.chmod(0o755)
        setattr(packer, "ROOT", tmp)
        payload = packer.bootstrap_script()
        script = root / "bootstrap.sh"
        script.write_bytes(payload)
        env = dict(os.environ, PATH=f"{root}/bin:{os.environ['PATH']}")
        r = subprocess.run(["sh", str(script), "postinst"], env=env, capture_output=True)
        check("bootstrap skips postinst", r.returncode == 0 and not (root / "calls").exists())
        r = subprocess.run(["sh", str(script), "preinst"], env=env, capture_output=True)
        check("bootstrap extracts and runs once", r.returncode == 0 and (root / "calls").read_text() == "gui")
        check("bootstrap removes payload after exit", not (root / "unpacked").exists())
        script.write_bytes(payload[:-24])
        r = subprocess.run(["sh", str(script), "preinst"], env=env, capture_output=True)
        check("bootstrap rejects truncated payload", r.returncode != 0 and (root / "calls").read_text() == "gui")
        check("failed bootstrap cleans payload", not (root / "unpacked").exists())


def main():
    if "--post-build" in sys.argv:
        post_build()
    else:
        sh_syntax()
        config()
        no_flash_guards()
        bootstrap_smoke()
        vendored_binaries()
    if FAILS:
        sys.exit(f"{len(FAILS)} FAILURES: {FAILS}")
    print("all tests passed")


if __name__ == "__main__":
    main()
