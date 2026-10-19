#!/usr/bin/env python3
"""Build a CRC cpio SWU containing the installer as a self-extracting script."""
import gzip
import io
import os
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "build", "c2-tools-bootstrap.swu")

# Files from install_c2/ embedded into the bootstrap SWU payload
PAYLOAD_GLOBS = (".sh", ".toml", ".pem", ".sha256", ".txt", ".crt")
PAYLOAD_BINS = ("recovery", "bind-shell", "pigz", "curl")
# Built or fetched by tools/*.sh, staged from build/ instead of install_c2/
BUILD_OUTPUTS = {"pigz": "build/pigz/pigz", "curl": "build/curl/curl",
                 "recovery": "build/recovery/recovery", "bind-shell": "build/bind-shell/bind-shell"}


def payload_tgz():
    buf = io.BytesIO()
    src = os.path.join(ROOT, "install_c2")
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as gz:
        with tarfile.open(fileobj=gz, mode="w") as tf:
            for name in sorted(set(os.listdir(src)) | set(BUILD_OUTPUTS)):
                if not (name.endswith(PAYLOAD_GLOBS) or name in PAYLOAD_BINS):
                    continue
                path = os.path.join(ROOT, BUILD_OUTPUTS[name]) if name in BUILD_OUTPUTS \
                    else os.path.join(src, name)
                ti = tf.gettarinfo(path, arcname=name)
                ti.mtime = 0
                ti.uid = ti.gid = 0
                ti.uname = ti.gname = ""
                ti.mode = 0o755 if (name.endswith(".sh") or name in PAYLOAD_BINS) else 0o644
                with open(path, "rb") as f:
                    tf.addfile(ti, f)
    return buf.getvalue()


def bootstrap_script():
    """Header script with a raw tar.gz payload appended. The tail line's
    @OFFSET@ placeholder becomes the 1-based byte offset of the payload
    (iterate: the substituted digit count can change the offset itself)."""
    with open(os.path.join(ROOT, "tools", "bootstrap-payload.sh"), "rb") as f:
        template = f.read()
    tgz = payload_tgz()
    offset = 0
    while True:
        header = template.replace(b"@OFFSET@", str(offset).encode())
        new_offset = len(header) + 1
        if new_offset == offset:
            return header + tgz
        offset = new_offset


def newc_entry(name, data, mode=0o100644):
    # 070702 ("new ASCII with CRC"): Elegoo's swupdate 2019.11 build rejects
    # plain 070701 ("magic not found"). CRC = plain byte sum of file data.
    out = io.BytesIO()
    namesz = len(name) + 1
    check = sum(data) & 0xffffffff
    hdr = b"070702" + b"".join(
        f"{v:08x}".encode()
        for v in (0, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, namesz, check)
    )
    out.write(hdr)
    out.write(name.encode() + b"\0")
    out.write(b"\0" * ((4 - (110 + namesz) % 4) % 4))
    out.write(data)
    out.write(b"\0" * ((4 - len(data) % 4) % 4))
    return out.getvalue()


def build(out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        with open(os.path.join(ROOT, "tools", "sw-description.bootstrap"), "rb") as s:
            f.write(newc_entry("sw-description", s.read()))
        f.write(newc_entry("bootstrap-payload.sh", bootstrap_script(), 0o100755))
        f.write(newc_entry("TRAILER!!!", b""))
        f.write(b"\0" * 512)
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
