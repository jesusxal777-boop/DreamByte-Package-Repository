#!/usr/bin/env python3
"""Verify that every installable manifest points to a real HTTPS asset with the declared hash."""
from __future__ import annotations
import hashlib, json, sys, tempfile, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent

def main():
    index = json.loads((ROOT / "repository.json").read_text())
    for entry in index["packages"]:
        if entry["status"] in ("planned", "metadata-only"):
            continue
        manifest = json.loads((ROOT / entry["manifest"]).read_text())
        download = manifest["download"]
        entries = [download] if "url" in download else list(download.values())
        for artifact in entries:
            url = artifact["url"]
            if not url.startswith("https://"):
                raise SystemExit(f"{entry['name']}: non-HTTPS URL {url}")
            digest = hashlib.sha256()
            size = 0
            request = urllib.request.Request(url, headers={"User-Agent": "DreamByte-Repository-CI/1"})
            with urllib.request.urlopen(request, timeout=60) as response:
                if response.geturl().split(":", 1)[0].lower() != "https":
                    raise SystemExit(f"{entry['name']}: final URL is not HTTPS")
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    digest.update(chunk); size += len(chunk)
            if digest.hexdigest() != artifact["sha256"]:
                raise SystemExit(f"{entry['name']}: SHA-256 mismatch")
            if "size" in artifact and size != artifact["size"]:
                raise SystemExit(f"{entry['name']}: size mismatch ({size} != {artifact['size']})")
            print(f"OK: {entry['name']} {url} sha256={digest.hexdigest()}")
    return 0
if __name__ == "__main__": sys.exit(main())
