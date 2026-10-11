#!/usr/bin/env python3
"""Wrap a plain SWU into Elegoo C2/CC2 OTA bundles (.zip.sig).

Port of meta-opencentauri/classes/elegoo-ota.bbclass (OpenCentauri/cosmos,
sims) to standalone Python. ELEG header is 512 bytes, little-endian:
  0x00 magic "ELEG"           0x08 plain filesize (u64)
  0x04 type | (0x80 if enc)   0x10 filename (48 bytes)
  0x05 major (u8), 0x06 minor (u16)  0x90 encrypt_offset (u64) = 0
  0x98 encrypt_length (u64) = enc size if enc else 0
  0xA0 AES IV (16 bytes)      0xB0 encrypt_filesize (u64)
  0xE0 sha256(payload as shipped) (32 bytes)
  0x100 RSA-2048 PKCS1v15 signature over the payload (256 bytes)

Usage: make_zipsig.py <input.swu> [--version 26.09.00.00] [--out build/]
"""
import argparse
import hashlib
import hmac
import io
import json
import os
import struct
import subprocess
import sys
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AES_KEY = "d14e150843e9d16893890756d8f77f674e161a8bebb8f720737ee60e7f8c7e68"
PRIV_KEY = os.path.join(ROOT, "keys", "swupdate_private.pem")

# (short prefix, header minor) — verified against stock bundles:
# cc2 = minor 2, c2 = minor 3. Names must keep "eeb001" (stock updater match)
# and embedded names must fit the 48-byte header field, so "installer" appears
# only in the output filename, not in the embedded member names.
VARIANTS = [("cc2_eeb001", 2), ("c2_eeb001", 3)]


def run(args, data):
    r = subprocess.run(args, input=data, capture_output=True)
    if r.returncode != 0:
        sys.exit(f"make_zipsig: {args[0]} failed: {r.stderr.decode(errors='replace')}")
    return r.stdout


def aes_cbc_encrypt(key_hex, iv, plain):
    pad_len = (-len(plain)) % 16 or 16
    padded = plain + b"\x00" * pad_len
    enc = run(["openssl", "enc", "-aes-256-cbc", "-nopad", "-K", key_hex, "-iv", iv.hex()], padded)
    return enc, len(padded)


def build_header(*, package_type, encrypted, header_minor, filename, filesize,
                 encrypt_filesize, iv, payload):
    hdr = bytearray(512)
    hdr[0:4] = b"ELEG"
    hdr[0x04] = (package_type & 0x7F) | (0x80 if encrypted else 0)
    hdr[0x05] = 1
    struct.pack_into("<H", hdr, 0x06, header_minor)
    struct.pack_into("<Q", hdr, 0x08, filesize)
    name = filename.encode("ascii")
    if len(name) >= 48:
        sys.exit(f"make_zipsig: filename too long: {filename}")
    hdr[0x10:0x10 + len(name)] = name
    struct.pack_into("<Q", hdr, 0x90, 0)
    struct.pack_into("<Q", hdr, 0x98, encrypt_filesize if encrypted else 0)
    hdr[0xA0:0xB0] = iv
    struct.pack_into("<Q", hdr, 0xB0, encrypt_filesize)
    hdr[0xE0:0x100] = hashlib.sha256(payload).digest()
    sig = run(["openssl", "dgst", "-sha256", "-sign", PRIV_KEY], payload)
    if len(sig) != 256:
        sys.exit(f"make_zipsig: RSA signature is {len(sig)} bytes, expected 256")
    hdr[0x100:0x200] = sig
    return bytes(hdr)


def eleg_encrypt(pkg_type, filename, plain, header_minor):
    iv = hmac.new(bytes.fromhex(AES_KEY), filename.encode("ascii") + b"\0" + plain,
                  hashlib.sha256).digest()[:16]
    enc, enc_size = aes_cbc_encrypt(AES_KEY, iv, plain)
    return build_header(package_type=pkg_type, encrypted=True,
                        header_minor=header_minor, filename=filename,
                        filesize=len(plain), encrypt_filesize=enc_size,
                        iv=iv, payload=enc) + enc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("swu")
    ap.add_argument("--version", default="26.09.00.00")
    ap.add_argument("--out", default=os.path.join(ROOT, "build"))
    args = ap.parse_args()

    with open(args.swu, "rb") as f:
        swu = f.read()
    sde = time.gmtime(int(os.environ.get("SOURCE_DATE_EPOCH", "1767225600")))
    stamp = time.strftime("%Y%m%d%H%M%S", sde)

    os.makedirs(args.out, exist_ok=True)
    for prefix, minor in VARIANTS:
        base = f"{prefix}_{args.version}_{stamp}"
        swu_sig = eleg_encrypt(0, f"{base}.swu", swu, minor)
        pkglist = {"packages": [{"file": f"{base}.swu.sig",
                                 "hash": hashlib.sha256(swu_sig).hexdigest()}],
                   "version": args.version, "update_class": "00.00.00.00"}
        json_sig = eleg_encrypt(3, "ota-package-list.json",
                                json.dumps(pkglist).encode("ascii"), minor)
        zbio = io.BytesIO()
        with zipfile.ZipFile(zbio, "w") as zf:
            for name, data in (("ota-package-list.json.sig", json_sig),
                               (f"{base}.swu.sig", swu_sig)):
                zi = zipfile.ZipInfo(name, date_time=sde[:6])
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                zf.writestr(zi, data)
        blob = zbio.getvalue()
        outer = build_header(package_type=4, encrypted=False, header_minor=minor,
                             filename=f"{base}.zip", filesize=len(blob),
                             encrypt_filesize=len(blob), iv=b"\x00" * 16,
                             payload=blob) + blob
        out_path = os.path.join(args.out, f"{prefix}_installer_{args.version}.zip.sig")
        with open(out_path, "wb") as f:
            f.write(outer)
        print(f"wrote {out_path} ({len(outer)} bytes), swu member {base}.swu.sig")


if __name__ == "__main__":
    main()
