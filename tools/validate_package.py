#!/usr/bin/env python3
"""Validate a DreamByte .dbpkg without extracting untrusted paths."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import tarfile
from pathlib import Path, PurePosixPath


def digest_file(fileobj) -> str:
    digest = hashlib.sha256()
    for chunk in iter(lambda: fileobj.read(1024 * 1024), b""):
        digest.update(chunk)
    return digest.hexdigest()

def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts and "\\" not in name

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("package", help=".dbpkg archive")
    ap.add_argument("--expected-manifest", help="repository package.json to compare name/version")
    args = ap.parse_args()
    archive = Path(args.package)
    errors = []
    try:
        with tarfile.open(archive, "r:gz") as tar:
            members = tar.getmembers()
            names = [m.name for m in members]
            if len(names) != len(set(names)):
                errors.append("duplicate archive member")
            for member in members:
                if not safe_name(member.name):
                    errors.append(f"unsafe path: {member.name!r}")
                if member.issym() or member.islnk() or member.isdev():
                    errors.append(f"links and device files are forbidden: {member.name!r}")
            if "META/manifest.json" not in names:
                errors.append("missing META/manifest.json")
            meta_member = tar.getmember("META/manifest.json") if "META/manifest.json" in names else None
            meta = None
            if meta_member:
                try:
                    meta = json.load(tar.extractfile(meta_member))
                except (ValueError, TypeError):
                    errors.append("META/manifest.json is not valid JSON")
            if isinstance(meta, dict):
                if meta.get("format") != "dbpkg-1": errors.append("unsupported dbpkg format")
                listed = {item.get("path"): item for item in meta.get("files", []) if isinstance(item, dict)}
                if set(listed) != {n for n in names if n != "META/manifest.json"}:
                    errors.append("file list in META/manifest.json does not match archive")
                for name, item in listed.items():
                    if not safe_name(name): errors.append(f"unsafe manifest path: {name!r}"); continue
                    member = tar.getmember(name)
                    actual = digest_file(tar.extractfile(member))
                    if actual != item.get("sha256"):
                        errors.append(f"SHA-256 mismatch for {name}")
                    mode = item.get("mode")
                    if not isinstance(mode, int) or mode & ~0o777:
                        errors.append(f"invalid mode for {name}")
            if "bin/hello" not in names:
                errors.append("missing real executable bin/hello")
            else:
                mode = tar.getmember("bin/hello").mode
                if not (mode & stat.S_IXUSR): errors.append("bin/hello is not executable")
            if args.expected_manifest:
                expected = json.loads(Path(args.expected_manifest).read_text(encoding="utf-8"))
                if isinstance(meta, dict):
                    for key in ("name", "version"):
                        if meta.get(key) != expected.get(key): errors.append(f"archive {key} does not match package.json")
                    arch = expected.get("architecture", [])
                    if meta.get("architecture") not in arch and "all" not in arch:
                        errors.append("archive architecture is not declared in package.json")
    except (OSError, tarfile.TarError, json.JSONDecodeError) as exc:
        errors.append(str(exc))
    if errors:
        for error in errors: print(f"ERROR: {error}")
        return 1
    print(f"OK: {archive} is a valid dbpkg ({archive.stat().st_size} bytes)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
