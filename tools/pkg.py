#!/usr/bin/env python3
"""Small reference pkg client for local/repository integration tests."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, tarfile
from pathlib import Path, PurePosixPath

def safe(name):
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and "\\" not in name

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--prefix", type=Path, default=Path(".dreambyte-install"))
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("update"); s = sub.add_parser("search"); s.add_argument("text")
    i = sub.add_parser("info"); i.add_argument("name")
    n = sub.add_parser("install"); n.add_argument("name")
    args = ap.parse_args(); root = args.repo_root.resolve(); index = json.loads((root / "repository.json").read_text())
    if args.command == "update": print(f"Updated repository: {index['package_count']} package(s)"); return 0
    packages = index["packages"]
    if args.command == "search":
        q = args.text.lower()
        for p in packages:
            if q in (p["name"] + " " + p["description"]).lower(): print(f"{p['name']} {p['version']} [{p['status']}]")
        return 0
    entry = next((p for p in packages if p["name"] == args.name), None)
    if not entry: raise SystemExit(f"package not found: {args.name}")
    manifest = json.loads((root / entry["manifest"]).read_text())
    if args.command == "info": print(json.dumps(manifest, indent=2)); return 0
    if manifest["status"] in ("planned", "metadata-only"): raise SystemExit("package has no installable artifact")
    arch = "x86_64" if os.uname().machine in ("x86_64", "amd64") else os.uname().machine
    if arch not in manifest["architecture"] and "all" not in manifest["architecture"]: raise SystemExit(f"unsupported architecture: {arch}")
    download = manifest["download"]
    if "url" not in download: download = download[arch]
    artifact = root / "dist" / Path(download["url"]).name
    if not artifact.is_file(): raise SystemExit(f"artifact not found locally: {artifact}")
    got = hashlib.sha256(artifact.read_bytes()).hexdigest()
    if got != download["sha256"]: raise SystemExit("SHA-256 mismatch; refusing installation")
    args.prefix.mkdir(parents=True, exist_ok=True)
    with tarfile.open(artifact, "r:gz") as tar:
        for member in tar.getmembers():
            if not safe(member.name) or member.issym() or member.islnk() or member.isdev(): raise SystemExit(f"unsafe archive path: {member.name}")
        tar.extractall(args.prefix, filter="data")
    executable = args.prefix / "bin" / manifest["name"]
    result = subprocess.run([str(executable)], text=True, capture_output=True, check=True)
    print(f"Installed {manifest['name']} {manifest['version']} to {args.prefix}")
    print(result.stdout, end="")
    return 0
if __name__ == "__main__": raise SystemExit(main())
