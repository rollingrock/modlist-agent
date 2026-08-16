#!/usr/bin/env python3
"""Resolve null Nexus pins in a recipe manifest to concrete (fileId, filename, size).

Reads the manifest, asks the Nexus API which uploaded file corresponds to each entry's
pinned `version`, and PROPOSES the result. It does not write pins back by default:
per docs/MANIFEST_SCHEMA.md an absent pin may be resolved by the agent *under
supervision*, and a human commits it. `--write` exists for when you have read the table
and agree.

Metadata only. This never downloads a mod file and never touches download_link.json, so
it is safe to run on a free account and cheap against the rate limit (2 requests/mod).

    python core/tools/resolve_pins.py recipes/fo4vr/manifest.yaml
    python core/tools/resolve_pins.py recipes/fo4vr/manifest.yaml --write
"""
import argparse
import json
import os
import pathlib
import sys
import urllib.error
import urllib.request

import yaml

API = "https://api.nexusmods.com/v1"
KEY_FILE = pathlib.Path(os.path.expanduser("~")) / ".nexus-api-key"


def load_key():
    key = os.environ.get("NEXUS_API_KEY")
    if key:
        return key.strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    sys.exit(f"no API key: set NEXUS_API_KEY or write {KEY_FILE}")


def get(path, key):
    req = urllib.request.Request(
        f"{API}/{path}",
        headers={
            "apikey": key,
            "User-Agent": "modlist-agent/0.1",
            # The AUP asks that applications identify themselves. Do it properly.
            "Application-Name": "modlist-agent",
            "Application-Version": "0.1",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8")), dict(r.headers)


def norm(v):
    """Version strings are author-typed and inconsistent: '1.7.0' vs 'v1.7' vs '1.7.0.0'."""
    return (v or "").strip().lstrip("vV").rstrip(".0").lower() or "0"


def pick(files, want):
    """Return (exact_matches, all_main_files). Never guesses — the caller reports."""
    main = [f for f in files if f.get("category_name") in ("MAIN", "OLD_VERSION", None)]
    exact = [f for f in files if norm(f.get("version")) == norm(want)]
    return exact, (main or files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--write", action="store_true", help="apply resolved pins to the manifest")
    args = ap.parse_args()

    key = load_key()
    path = pathlib.Path(args.manifest)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    domain = doc["game"]["nexusDomain"]

    rows, resolved = [], {}
    remaining = None

    for mod in doc["mods"]:
        src = mod.get("source", {})
        if src.get("type") != "nexus":
            continue
        mid, want = src.get("modId"), src.get("version")
        try:
            info, _ = get(f"games/{domain}/mods/{mid}.json", key)
            data, hdrs = get(f"games/{domain}/mods/{mid}/files.json", key)
            remaining = hdrs.get("x-rl-hourly-remaining", remaining)
        except urllib.error.HTTPError as e:
            rows.append((mod["id"], mid, f"HTTP {e.code}", "", "", "", ""))
            continue

        files = data.get("files", [])
        exact, fallback = pick(files, want)
        status = info.get("status", "?")
        avail = "" if info.get("available", True) else " UNAVAILABLE"

        if len(exact) == 1:
            f = exact[0]
            rows.append((mod["id"], mid, "EXACT" + avail, f["file_id"], f.get("version"),
                         f.get("file_name"), f.get("size_in_bytes") or f.get("size_kb", 0) * 1024))
            resolved[mod["id"]] = f
        elif len(exact) > 1:
            rows.append((mod["id"], mid, f"AMBIGUOUS ({len(exact)})" + avail, "", want, "", ""))
            for f in exact:
                rows.append(("", "", "   candidate", f["file_id"], f.get("version"),
                             f.get("file_name"), f.get("size_in_bytes") or 0))
        else:
            latest = sorted(fallback, key=lambda f: f.get("uploaded_timestamp") or 0)[-1:] or []
            rows.append((mod["id"], mid, f"NO MATCH for {want}" + avail, "", status, "", ""))
            for f in latest:
                rows.append(("", "", "   newest is", f["file_id"], f.get("version"),
                             f.get("file_name"), f.get("size_in_bytes") or 0))

    w = [max(len(str(r[i])) for r in rows) for i in range(7)] if rows else []
    hdr = ("id", "modId", "status", "fileId", "version", "file_name", "bytes")
    w = [max(w[i], len(hdr[i])) for i in range(7)]
    line = lambda r: "  ".join(str(r[i]).ljust(w[i]) for i in range(7)).rstrip()
    print(line(hdr))
    print("  ".join("-" * w[i] for i in range(7)))
    for r in rows:
        print(line(r))
    print(f"\nresolved {len(resolved)} exact; rate limit remaining this hour: {remaining}")

    if not args.write:
        print("\nPROPOSED ONLY — nothing written. Re-run with --write to apply.")
        return

    # Surgical text edit rather than a YAML round-trip: dumping would destroy the comments,
    # which carry the reasoning and are the most valuable part of this file.
    text = path.read_text(encoding="utf-8")
    for mid_slug, f in resolved.items():
        needle = f"- id: {mid_slug}\n"
        i = text.find(needle)
        if i < 0:
            print(f"WARN could not locate {mid_slug}")
            continue
        seg_end = text.find("\n  - id:", i + 1)
        seg_end = len(text) if seg_end < 0 else seg_end
        seg = text[i:seg_end]
        new = seg.replace("fileId: null", f"fileId: {f['file_id']}", 1)
        size = f.get("size_in_bytes") or f.get("size_kb", 0) * 1024
        new = new.replace(
            "file: { name: null, sha256: null, size: null }",
            "file:\n      name: %r\n      sha256: null   # pending download\n      size: %d"
            % (f.get("file_name"), size),
            1,
        )
        text = text[:i] + new + text[seg_end:]
    path.write_text(text, encoding="utf-8")
    print(f"\nwrote {len(resolved)} pins into {path}")


if __name__ == "__main__":
    main()
