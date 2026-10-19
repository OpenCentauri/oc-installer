#!/usr/bin/env python3
"""Package the CC1 USB installer with the shared C2/CC2 utility payload."""
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def build(out=None):
    out = Path(out) if out is not None else ROOT / "build"
    source = ROOT / "install_opencentauri"
    shared = ROOT / "install_c2"
    files = {p.name: p for p in source.iterdir()
             if p.is_file() and (p.suffix in (".sh", ".toml")
                                 or p.name.startswith("IMPORT_ME_DO_NOT_PRINT"))}
    files.update({name: source / name for name in
                  ("decrypt", "utf8-fix", "wifi-network-config-tool", "run.sh",
                   "config.toml", "install-shell.sh")})
    files.update({name: shared / name for name in
                  ("bind-shell.sha256", "pigz-LICENSE.txt", "backup-emmc.sh", "log-task.sh")})
    files["shell-service.sh"] = shared / "install-shell.sh"
    files["pigz"] = ROOT / "build/pigz/pigz"
    files["recovery"] = ROOT / "build/recovery/recovery"
    files["bind-shell"] = ROOT / "build/bind-shell/bind-shell"
    for path in files.values():
        if not path.is_file():
            raise FileNotFoundError(f"Missing CC1 payload: {path}")

    stage = out / "cc1/install_opencentauri"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    binaries = {"recovery", "bind-shell", "pigz", "decrypt", "utf8-fix",
                "wifi-network-config-tool"}
    for name, path in files.items():
        target = stage / name
        shutil.copyfile(path, target)
        target.chmod(0o755 if name in binaries or name.endswith(".sh") else 0o644)
    archive = out / "oc-installer.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name in sorted(files):
            zf.write(stage / name, f"install_opencentauri/{name}")
    print(f"wrote {archive} ({archive.stat().st_size} bytes)")
    return archive


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else None)
