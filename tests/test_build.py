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
    for rel in ("install_c2/recovery", "install_c2/bind-shell"):
        with open(os.path.join(ROOT, rel), "rb") as f:
            ehdr = f.read(20)
        check(f"{rel}: 32-bit ARM static ELF",
              ehdr[:4] == b"\x7fELF" and ehdr[4] == 1 and
              struct.unpack("<H", ehdr[16:18])[0] == 2 and
              struct.unpack("<H", ehdr[18:20])[0] == 0x28)
    want = open(os.path.join(ROOT, "install_c2", "bind-shell.sha256")).read().split()[0]
    got = hashlib.sha256(open(os.path.join(ROOT, "install_c2", "bind-shell"), "rb").read()).hexdigest()
    check("bind-shell.sha256 matches binary", want == got)
    derived = subprocess.run(["openssl", "rsa", "-in",
                              os.path.join(ROOT, "keys", "swupdate_private.pem"), "-pubout"],
                             capture_output=True).stdout
    shipped = open(os.path.join(ROOT, "install_c2", "swupdate_public_cosmos.pem"), "rb").read()
    check("shipped pubkey matches vendored private key", derived == shipped)


def config():
    with open(os.path.join(ROOT, "install_c2", "config.toml"), "rb") as f:
        cfg = tomllib.load(f)
    check("config.toml parses", True)
    seen = {}
    for group, entries in cfg.get("submenus", {}).items():
        idxs = []
        for entry, body in entries.items():
            idxs.append(body.get("index"))
            for task in body.get("tasks", []) + body.get("completed_actions", []):
                cmd = task.get("command", [])
                for part in cmd:
                    if part.startswith("/user-resource/update_tmp/"):
                        exists = os.path.exists(os.path.join(
                            ROOT, "install_c2", part.rsplit("/", 1)[-1]))
                        check(f"{entry}: {os.path.basename(part)} exists in install_c2/", exists)
                    if part == "reboot" or part.endswith("; reboot"):
                        pass  # reboot allowed in GUI actions
        check(f"{group}: unique indexes", len(idxs) == len(set(idxs)), str(idxs))
    check("no plain Exit action", not any(k == "Exit" for k in cfg.get("scripts", {})))


def no_flash_guards():
    # The bootstrap path must never flash or write bootenv. Install scripts are
    # user-initiated flashers by design and are exempt.
    safe = ["tools/bootstrap-payload.sh", "tools/sw-description.bootstrap",
            "install_c2/run.sh", "install_c2/backup-emmc.sh",
            "install_c2/install-shell.sh", "install_c2/check-boot-slot.sh",
            "install_c2/download-firmware.sh"]
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


def read_newc(blob):
    """Parse cpio newc/crc, return [(name, data)]."""
    out = []
    off = 0
    while True:
        assert blob[off:off + 6] in (b"070701", b"070702"), f"bad magic at {off}"
        fields = [int(blob[off + 6 + i * 8: off + 14 + i * 8], 16) for i in range(13)]
        namesz, filesize = fields[11], fields[6]
        name = blob[off + 110: off + 110 + namesz - 1].decode()
        off += 110 + namesz
        off += (4 - off % 4) % 4
        out.append((name, blob[off:off + filesize]))
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
    with open("/tmp/sig-test-pub.pem", "wb") as f:
        f.write(pubkey)
    with open("/tmp/sig-test.bin", "wb") as f:
        f.write(sig)
    r = subprocess.run(["openssl", "dgst", "-sha256", "-verify", "/tmp/sig-test-pub.pem",
                        "-signature", "/tmp/sig-test.bin"], input=payload, capture_output=True)
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
                  {"run.sh", "config.toml", "recovery", "bind-shell",
                   "check-boot-slot.sh", "backup-emmc.sh", "install-shell.sh",
                   "download-firmware.sh", "install-cosmos.sh",
                   "install-cosmos-local.sh", "swupdate_public_cosmos.pem"} <= members_t,
                  str(sorted(members_t)))
            eh = tf.extractfile("recovery").read(20)
            check("payload recovery is 32-bit ARM ELF",
                  eh[:4] == b"\x7fELF" and struct.unpack("<H", eh[18:20])[0] == 0x28)

    pub = open(os.path.join(ROOT, "install_c2", "swupdate_public_cosmos.pem"), "rb").read()
    swu = open(swu_path, "rb").read()
    variants = sorted(f for f in os.listdir(BUILD) if f.endswith(".zip.sig"))
    check("two zip.sig variants", len(variants) == 2, str(variants))
    for v in variants:
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
        check(f"{v}: manifest hash matches swu.sig",
              manifest["packages"][0]["hash"] == hashlib.sha256(swu_sig).hexdigest())
        check(f"{v}: manifest member name", manifest["packages"][0]["file"] == next(
            n for n in names if n.endswith(".swu.sig")))
        shdr, senc = parse_eleg(swu_sig)
        plain = aes_decrypt(shdr["iv"], senc)[:shdr["filesize"]]
        check(f"{v}: swu decrypts byte-equal", plain == swu)


def main():
    if "--post-build" in sys.argv:
        post_build()
    else:
        sh_syntax()
        config()
        no_flash_guards()
        vendored_binaries()
    if FAILS:
        sys.exit(f"{len(FAILS)} FAILURES: {FAILS}")
    print("all tests passed")


if __name__ == "__main__":
    main()
