#!/usr/bin/env python3
"""Build a reproducible DreamByte .dbpkg archive from a package source tree."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def load_manifest(package_dir: Path) -> dict:
    path = package_dir / "package.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    required = {"name", "version", "architecture", "status"}
    missing = required - data.keys()
    if missing:
        raise SystemExit(f"missing package fields: {', '.join(sorted(missing))}")
    return data

def tar_info(name: str, source: Path, mode: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(name)
    info.size = source.stat().st_size
    info.mode = mode
    info.uid = info.gid = 0
    info.uname = info.gname = "root"
    info.mtime = 0
    return info

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("package", help="package directory, e.g. packages/hello")
    ap.add_argument("--output-dir", default="dist", help="directory for the .dbpkg")
    ap.add_argument("--arch", default=None, help="target architecture (default: host x86_64)")
    ap.add_argument("--cc", default=os.environ.get("CC", "gcc"))
    args = ap.parse_args()

    package_dir = (ROOT / args.package).resolve() if not Path(args.package).is_absolute() else Path(args.package).resolve()
    manifest = load_manifest(package_dir)
    arch = args.arch or ("x86_64" if os.uname().machine in ("x86_64", "amd64") else os.uname().machine)
    if arch not in manifest["architecture"] and "all" not in manifest["architecture"]:
        raise SystemExit(f"target architecture {arch!r} is not declared in package architecture {manifest['architecture']}")
    source = package_dir / "src" / "hello.c"
    if manifest["name"] == "hello" and not source.is_file():
        raise SystemExit(f"missing source file: {source}")

    out_dir = Path(args.output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dbpkg-build-") as tmp:
        stage = Path(tmp) / "stage"
        bin_dir = stage / "bin"
        meta_dir = stage / "META"
        bin_dir.mkdir(parents=True)
        meta_dir.mkdir()
        executable = bin_dir / manifest["name"]
        subprocess.run([args.cc, "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", str(source), "-o", str(executable)], check=True)
        os.chmod(executable, 0o755)

        files = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                rel = path.relative_to(stage).as_posix()
                files.append({"path": rel, "sha256": sha256(path), "mode": stat.S_IMODE(path.stat().st_mode)})
        archive_manifest = {
            "format": "dbpkg-1",
            "name": manifest["name"],
            "version": manifest["version"],
            "architecture": arch,
            "files": files,
        }
        manifest_path = meta_dir / "manifest.json"
        # META/manifest.json is intentionally excluded from its own file list;
        # otherwise its SHA-256 would be self-referential and non-reproducible.
        archive_manifest["files"] = sorted(files, key=lambda item: item["path"])
        manifest_path.write_text(json.dumps(archive_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        output = out_dir / f"{manifest['name']}-{manifest['version']}-{arch}.dbpkg"
        with output.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0, filename="") as compressed:
                with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar:
                    for path in sorted(stage.rglob("*")):
                        if path.is_file():
                            rel = path.relative_to(stage).as_posix()
                            mode = 0o755 if rel.startswith("bin/") else 0o644
                            with path.open("rb") as content:
                                tar.addfile(tar_info(rel, path, mode), content)
        print(json.dumps({"artifact": str(output), "sha256": sha256(output), "size": output.stat().st_size, "architecture": arch}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
