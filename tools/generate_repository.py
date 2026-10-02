#!/usr/bin/env python3
"""DreamByte Package Repository - validator and index generator.

Usage:
    python tools/generate_repository.py           # validate packages/*/package.json and rewrite repository.json
    python tools/generate_repository.py --check   # validate only (used by CI); fails if repository.json is stale

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent

FORMAT_VERSION = 1
REPOSITORY_NAME = "DreamByte Official Package Repository"
BASE_URL = "https://raw.githubusercontent.com/jesusxal777-boop/DreamByte-Package-Repository/main/"

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,63}$")
SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LICENSE_RE = re.compile(r"^[A-Za-z0-9.+() -]+$")
DEP_RE = re.compile(r"^([a-z0-9][a-z0-9._+-]{0,63})(?:\s*(>=|<=|==|=|>|<)\s*(\S+))?$")

ARCHITECTURES = ("arm64-v8a", "armeabi-v7a", "x86_64", "x86", "all")
TYPES = ("app", "cli", "library", "runtime", "tool", "script", "resource", "os-m")
STATUSES = ("stable", "beta", "planned", "metadata-only", "deprecated")
INSTALLABLE = ("stable", "beta", "deprecated")      # must ship a download
NON_INSTALLABLE = ("planned", "metadata-only")      # may omit download
SCOPES = ("user", "system")
FORMATS = ("tar.gz", "tar.xz", "zip", "bin", "apk", "script")

REQUIRED_FIELDS = (
    "name", "version", "description", "maintainer", "license",
    "architecture", "dependencies", "type", "status",
)
OPTIONAL_FIELDS = ("download", "scope", "homepage")
ARTIFACT_KEYS = ("url", "sha256", "size", "format")


class Problems:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, path, field, message):
        self.errors.append((path, field, message))

    def warn(self, path, field, message):
        self.warnings.append((path, field, message))


# ---------------------------------------------------------------- JSON loading

def _no_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key '%s'" % key)
        out[key] = value
    return out


def load_json(path, rel, problems):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        problems.error(rel, None, "cannot read file: %s" % exc)
        return None
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError as exc:
        problems.error(rel, None, "invalid JSON: %s" % exc)
        return None


# ---------------------------------------------------------------- versions

def parse_version(value):
    m = SEMVER_RE.match(value)
    major, minor, patch, pre = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
    # a release sorts above its pre-releases; pre-release ids are compared as plain strings (simplified)
    return (major, minor, patch, 0 if pre else 1, pre or "")


def satisfies(version, op, wanted):
    a, b = parse_version(version), parse_version(wanted)
    if op == ">=":
        return a >= b
    if op == "<=":
        return a <= b
    if op == ">":
        return a > b
    if op == "<":
        return a < b
    return a == b  # "=" and "=="


def parse_dep(text):
    m = DEP_RE.match(text.strip())
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


# ---------------------------------------------------------------- manifest validation

def check_artifact(rel, field, entry, p):
    if not isinstance(entry, dict):
        p.error(rel, field, "must be an object with 'url' and 'sha256'")
        return
    for key in entry:
        if key not in ARTIFACT_KEYS:
            p.warn(rel, "%s.%s" % (field, key), "unknown field (ignored)")
    url = entry.get("url")
    if not isinstance(url, str) or not url:
        p.error(rel, field + ".url", "required: absolute HTTPS URL of the artifact")
    else:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.netloc:
            p.error(rel, field + ".url", "must be an absolute HTTPS URL, got '%s'" % url)
    sha = entry.get("sha256")
    if not isinstance(sha, str) or not SHA256_RE.match(sha):
        p.error(rel, field + ".sha256", "required: 64 lowercase hexadecimal characters (SHA-256)")
    if "size" in entry:
        size = entry["size"]
        if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
            p.error(rel, field + ".size", "must be a positive integer (bytes)")
    if "format" in entry and entry["format"] not in FORMATS:
        p.error(rel, field + ".format", "must be one of %s" % ", ".join(FORMATS))


def validate_download(rel, download, archs, status, p):
    if not isinstance(download, dict) or not download:
        p.error(rel, "download", "must be an object: {url, sha256} or a map architecture -> {url, sha256}")
        return
    if "url" in download or "sha256" in download:
        check_artifact(rel, "download", download, p)
        return
    if "all" in archs:
        p.error(rel, "download", "architecture 'all' requires a single download {url, sha256}, not a per-architecture map")
        return
    for arch, entry in download.items():
        field = "download.%s" % arch
        if arch not in ARCHITECTURES or arch == "all":
            p.error(rel, field, "key must be a concrete architecture: %s" % ", ".join(a for a in ARCHITECTURES if a != "all"))
            continue
        if arch not in archs:
            p.error(rel, field, "architecture '%s' is not listed in 'architecture'" % arch)
        check_artifact(rel, field, entry, p)
    if status in INSTALLABLE:
        missing = [a for a in archs if a not in download]
        if missing:
            p.error(rel, "download", "missing artifact for architecture(s): %s" % ", ".join(missing))


def validate_manifest(rel, dirname, data, p):
    for field in REQUIRED_FIELDS:
        if field not in data:
            p.error(rel, field, "required field is missing")
    for field in data:
        if field not in REQUIRED_FIELDS and field not in OPTIONAL_FIELDS:
            p.warn(rel, field, "unknown field (ignored)")

    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not NAME_RE.match(name):
            p.error(rel, "name", "must match %s" % NAME_RE.pattern)
        elif name != dirname:
            p.error(rel, "name", "'%s' must be identical to its folder name '%s'" % (name, dirname))

    if "version" in data:
        version = data["version"]
        if not isinstance(version, str) or not SEMVER_RE.match(version):
            p.error(rel, "version", "must be a semantic version MAJOR.MINOR.PATCH, got %r (use 0.0.0 while a package is only planned)" % (version,))

    for field in ("description", "maintainer"):
        if field in data and (not isinstance(data[field], str) or not data[field].strip()):
            p.error(rel, field, "must be a non-empty string")

    if "license" in data:
        lic = data["license"]
        if not isinstance(lic, str) or not LICENSE_RE.match(lic):
            p.error(rel, "license", "must be an SPDX identifier such as 'MIT' or 'GPL-3.0-or-later' (or 'NOASSERTION' if undecided)")

    archs = []
    if "architecture" in data:
        arch = data["architecture"]
        if not isinstance(arch, list) or not arch:
            p.error(rel, "architecture", "must be a non-empty list, allowed values: %s" % ", ".join(ARCHITECTURES))
        else:
            bad = [a for a in arch if not isinstance(a, str) or a not in ARCHITECTURES]
            if bad:
                p.error(rel, "architecture", "invalid value(s) %s, allowed: %s" % (bad, ", ".join(ARCHITECTURES)))
            texts = [str(a) for a in arch]
            if len(set(texts)) != len(texts):
                p.error(rel, "architecture", "contains duplicate entries")
            if "all" in arch and len(arch) > 1:
                p.error(rel, "architecture", "'all' cannot be combined with other architectures")
            archs = [a for a in arch if isinstance(a, str) and a in ARCHITECTURES]

    if "dependencies" in data and not isinstance(data["dependencies"], list):
        p.error(rel, "dependencies", "must be a list of strings like \"name\" or \"name>=1.0.0\"")

    if "type" in data and data["type"] not in TYPES:
        p.error(rel, "type", "must be one of %s" % ", ".join(TYPES))

    status = data.get("status")
    if "status" in data and status not in STATUSES:
        p.error(rel, "status", "must be one of %s" % ", ".join(STATUSES))

    if "scope" in data and data["scope"] not in SCOPES:
        p.error(rel, "scope", "must be one of %s" % ", ".join(SCOPES))

    if "homepage" in data:
        hp = data["homepage"]
        if not isinstance(hp, str) or urlparse(hp).scheme != "https" or not urlparse(hp).netloc:
            p.error(rel, "homepage", "must be an absolute HTTPS URL")

    if status in INSTALLABLE and "download" not in data:
        p.error(rel, "download", "required when status is '%s' (use 'planned' or 'metadata-only' until a real artifact exists)" % status)
    if "download" in data:
        validate_download(rel, data["download"], archs, status, p)


def load_all(root, p):
    packages_dir = root / "packages"
    manifests = {}
    if not packages_dir.is_dir():
        p.error("packages/", None, "directory not found")
        return manifests
    names_seen = {}
    folders_lower = {}
    for entry in sorted(packages_dir.iterdir(), key=lambda e: e.name):
        if entry.name.startswith("."):
            continue
        if not entry.is_dir():
            p.warn("packages/%s" % entry.name, None, "unexpected file in packages/ (only package folders are expected)")
            continue
        rel = "packages/%s/package.json" % entry.name
        low = entry.name.lower()
        if low in folders_lower:
            p.error(rel, "name", "folder name collides (case-insensitively) with packages/%s" % folders_lower[low])
        folders_lower[low] = entry.name
        mpath = entry / "package.json"
        if not mpath.is_file():
            p.error(rel, None, "missing package.json")
            continue
        data = load_json(mpath, rel, p)
        if data is None:
            continue
        if not isinstance(data, dict):
            p.error(rel, None, "the document root must be a JSON object")
            continue
        validate_manifest(rel, entry.name, data, p)
        name = data.get("name")
        if isinstance(name, str):
            if name in names_seen:
                p.error(rel, "name", "duplicate package name '%s' (also defined in %s)" % (name, names_seen[name]))
            else:
                names_seen[name] = rel
        manifests[entry.name] = {"rel": rel, "data": data, "path": mpath}
    return manifests


def check_dependencies(manifests, p):
    graph = {}
    for dirname, m in manifests.items():
        data, rel = m["data"], m["rel"]
        deps = data.get("dependencies")
        if not isinstance(deps, list):
            continue
        graph[dirname] = []
        for i, dep in enumerate(deps):
            field = "dependencies[%d]" % i
            if not isinstance(dep, str):
                p.error(rel, field, "must be a string like \"name\" or \"name>=1.0.0\"")
                continue
            parsed = parse_dep(dep)
            if not parsed:
                p.error(rel, field, "invalid dependency '%s' (expected 'name' or 'name>=1.0.0'; operators: >= <= > < =)" % dep)
                continue
            dname, op, wanted = parsed
            if dname == dirname:
                p.error(rel, field, "a package cannot depend on itself")
                continue
            target = manifests.get(dname)
            if target is None:
                p.error(rel, field, "dependency '%s' does not exist in packages/" % dname)
                continue
            graph[dirname].append(dname)
            if op:
                if not SEMVER_RE.match(wanted):
                    p.error(rel, field, "constraint version '%s' must be MAJOR.MINOR.PATCH" % wanted)
                else:
                    have = target["data"].get("version")
                    if isinstance(have, str) and SEMVER_RE.match(have) and not satisfies(have, op, wanted):
                        p.error(rel, field, "'%s' is at version %s, which does not satisfy '%s'" % (dname, have, dep))
            tstatus = target["data"].get("status")
            if data.get("status") in INSTALLABLE and tstatus in NON_INSTALLABLE:
                p.error(rel, field, "'%s' is '%s' and cannot be installed yet, so this package cannot be '%s'" % (dname, tstatus, data.get("status")))

    state = {}

    def visit(node, stack):
        state[node] = 1
        for nxt in graph.get(node, []):
            if state.get(nxt) == 1:
                cycle = stack[stack.index(nxt):] + [nxt]
                p.error(manifests[node]["rel"], "dependencies", "dependency cycle: %s" % " -> ".join(cycle))
            elif nxt not in state:
                visit(nxt, stack + [nxt])
        state[node] = 2

    for node in sorted(graph):
        if node not in state:
            visit(node, [node])


# ---------------------------------------------------------------- index

def build_entries(manifests):
    entries = []
    for dirname in sorted(manifests):
        m = manifests[dirname]
        d = m["data"]
        entries.append({
            "name": d["name"],
            "version": d["version"],
            "description": d["description"],
            "type": d["type"],
            "status": d["status"],
            "architecture": d["architecture"],
            "dependencies": d["dependencies"],
            "manifest": "packages/%s/package.json" % dirname,
            "manifest_sha256": hashlib.sha256(m["path"].read_bytes()).hexdigest(),
        })
    return entries


def build_index(entries, existing, now):
    core = {
        "format_version": FORMAT_VERSION,
        "name": REPOSITORY_NAME,
        "base_url": BASE_URL,
        "packages": entries,
    }
    old_core = None
    old_version = 0
    old_updated = None
    if isinstance(existing, dict):
        old_core = {k: existing.get(k) for k in core}
        if isinstance(existing.get("repository_version"), int):
            old_version = existing["repository_version"]
        old_updated = existing.get("updated_at")
    if old_core == core and old_updated:
        version, updated = old_version, old_updated      # nothing changed: keep output stable
    else:
        version, updated = old_version + 1, now
    return {
        "format_version": FORMAT_VERSION,
        "name": REPOSITORY_NAME,
        "repository_version": version,
        "base_url": BASE_URL,
        "updated_at": updated,
        "package_count": len(entries),
        "packages": entries,
    }


def serialize(index):
    return json.dumps(index, indent=2, ensure_ascii=False) + "\n"


def diff_index(existing, expected):
    msgs = []
    if not isinstance(existing, dict):
        return [("repository.json", None, "missing or not a JSON object")]
    for key in ("format_version", "name", "base_url"):
        if existing.get(key) != expected[key]:
            msgs.append(("repository.json", key, "is %r but expected %r" % (existing.get(key), expected[key])))
    raw = existing.get("packages")
    listed = {}
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and isinstance(item.get("name"), str):
                listed[item["name"]] = item
    else:
        msgs.append(("repository.json", "packages", "must be a list"))
    wanted = {e["name"]: e for e in expected["packages"]}
    for name in sorted(set(listed) | set(wanted)):
        if name not in listed:
            msgs.append(("repository.json", "packages", "package '%s' exists in packages/ but is missing from the index" % name))
        elif name not in wanted:
            msgs.append(("repository.json", "packages", "package '%s' is listed but packages/%s/package.json does not exist or is invalid" % (name, name)))
        else:
            for key in wanted[name]:
                if listed[name].get(key) != wanted[name][key]:
                    msgs.append(("repository.json", "packages.%s.%s" % (name, key),
                                 "index has %r but packages/%s/package.json gives %r" % (listed[name].get(key), name, wanted[name][key])))
    return msgs


# ---------------------------------------------------------------- reporting / main

def report(p):
    on_actions = os.environ.get("GITHUB_ACTIONS") == "true"
    for level, items in (("WARNING", p.warnings), ("ERROR", p.errors)):
        for path, field, message in items:
            where = path if field is None else "%s [%s]" % (path, field)
            print("%s %s: %s" % (level, where, message))
            if on_actions:
                print("::%s file=%s::%s%s" % (level.lower(), path, "" if field is None else "[%s] " % field, message))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Validate packages and (re)generate repository.json")
    ap.add_argument("--check", action="store_true", help="validate only; fail if repository.json is stale")
    ap.add_argument("--root", default=str(ROOT), help="repository root (default: parent of tools/)")
    ap.add_argument("--updated-at", default=None, help="override the updated_at timestamp (ISO 8601, UTC)")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    index_path = root / "repository.json"
    p = Problems()

    manifests = load_all(root, p)
    check_dependencies(manifests, p)

    existing = None
    if index_path.exists():
        existing = load_json(index_path, "repository.json", p if args.check else Problems())
    elif args.check:
        p.error("repository.json", None, "file not found; run: python tools/generate_repository.py")

    if p.errors:
        report(p)
        print("\nFAILED: %d error(s), %d warning(s)" % (len(p.errors), len(p.warnings)))
        return 1

    now = args.updated_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries = build_entries(manifests)
    index = build_index(entries, existing, now)
    text = serialize(index)

    if args.check:
        for path, field, message in diff_index(existing, index):
            p.error(path, field, message)
        current = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
        if not p.errors and current != text:
            p.error("repository.json", None, "content differs from generated output (formatting or metadata)")
        if p.errors:
            report(p)
            print("\nFAILED: repository.json is out of date. Run: python tools/generate_repository.py")
            return 1
        report(p)
        print("OK: %d package(s) validated, repository.json is up to date (repository_version %d)" % (len(entries), index["repository_version"]))
        return 0

    report(p)
    current = index_path.read_text(encoding="utf-8") if index_path.exists() else None
    if current == text:
        print("repository.json already up to date (%d package(s))" % len(entries))
    else:
        index_path.write_text(text, encoding="utf-8", newline="\n")
        print("repository.json written: %d package(s), repository_version %d" % (len(entries), index["repository_version"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
