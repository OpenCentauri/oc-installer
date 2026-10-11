#!/usr/bin/env python3
"""Build the C2/CC2 bootstrap SWU (cpio newc, sw-description first).

Usage: make_swu.py [output.swu]
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT = os.path.join(ROOT, "build", "c2-tools-bootstrap.swu")

# cpio member name -> repo source path
MEMBERS = [
    ("sw-description", "tools/sw-description.bootstrap"),
    ("bootstrap-payload.sh", "tools/bootstrap-payload.sh"),
]


def newc_entry(name, data, mode=0o100644):
    out = io.BytesIO()
    namesz = len(name) + 1
    hdr = b"070701" + b"".join(
        f"{v:08x}".encode()
        for v in (0, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, namesz, 0)
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
        for name, src in MEMBERS:
            with open(os.path.join(ROOT, src), "rb") as s:
                mode = 0o100755 if src.endswith(".sh") else 0o100644
                f.write(newc_entry(name, s.read(), mode))
        f.write(newc_entry("TRAILER!!!", b""))
        f.write(b"\0" * 512)
    print(f"wrote {out_path} ({os.path.getsize(out_path)} bytes)")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_OUT)
