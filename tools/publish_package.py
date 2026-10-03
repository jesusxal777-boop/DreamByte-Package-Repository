#!/usr/bin/env python3
"""Publish a built .dbpkg as a GitHub Release asset using gh CLI."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("artifact", help="built .dbpkg file")
    ap.add_argument("--tag", required=True, help="immutable release tag, e.g. hello-v1.0.0-x86_64")
    ap.add_argument("--title", default=None)
    ap.add_argument("--repo", default=None, help="owner/repository; defaults to git remote")
    ap.add_argument("--draft", action="store_true", help="create a draft release")
    args = ap.parse_args()
    artifact = Path(args.artifact).resolve()
    if not artifact.is_file() or artifact.suffix != ".dbpkg":
        raise SystemExit(f"artifact does not exist or is not a .dbpkg: {artifact}")
    title = args.title or f"DreamByte package {args.tag}"
    command = ["gh", "release", "create", args.tag, str(artifact), "--title", title, "--notes", f"Automated package release for {artifact.name}"]
    if args.repo: command += ["--repo", args.repo]
    if args.draft: command.append("--draft")
    subprocess.run(command, cwd=ROOT, check=True)
    repo = args.repo
    if not repo:
        repo = subprocess.check_output(["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"], cwd=ROOT, text=True).strip()
    url = f"https://github.com/{repo}/releases/download/{args.tag}/{artifact.name}"
    print(json.dumps({"tag": args.tag, "artifact": artifact.name, "url": url}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
