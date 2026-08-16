"""Drift detection: are the pins still real?

Answers the CI half of open question #3. A pinned manifest goes stale silently — links
rot, authors delete files, mods get archived — and the first symptom is usually a user's
build failing months later.

**Metadata only, by default.** This is designed to run on a schedule, so it must be a good
API citizen: it asks whether a file still exists, not for the file. Re-downloading 54 MB of
mods every night to prove nothing changed would be rude and pointless. `--hashes` exists
for when a manifest changes and you actually want the bytes checked.
"""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass

from .nexus import Client, NexusError


@dataclass
class Finding:
    entry_id: str
    level: str          # ok | warn | dead
    message: str


def _norm(v: str | None) -> str:
    s = (v or "").strip().lstrip("vV").lower()
    parts = s.split(".")
    while len(parts) > 1 and parts[-1] in ("0", ""):
        parts.pop()
    return ".".join(parts) or "0"


def _newer_than(files: list[dict], file_id: int, pinned_version: str | None) -> dict | None:
    """The newest MAIN file, if it is a genuine upgrade over the pinned one.

    Multi-variant mods (No DLC / DLC / Automatron, or a FOMOD alongside standalones)
    publish siblings under the SAME version. Reporting those as "newer" is noise that
    trains the reader to ignore the check — so a candidate whose version matches the pin
    is treated as a variant, not an upgrade.
    """
    mains = [f for f in files if f.get("category_name") == "MAIN"]
    if not mains:
        return None
    newest = max(mains, key=lambda f: f.get("uploaded_timestamp") or 0)
    if newest.get("file_id") == file_id:
        return None
    if _norm(newest.get("version")) == _norm(pinned_version):
        return None
    return newest


def check_nexus(manifest, client: Client) -> list[Finding]:
    domain = manifest.game["nexusDomain"]
    out: list[Finding] = []
    for e in manifest.mods + manifest.tools:
        src = e.source
        if src.get("type") != "nexus" or not src.get("fileId"):
            continue
        mid, fid = src["modId"], src["fileId"]
        try:
            info = client.mod(domain, mid)
        except NexusError as exc:
            out.append(Finding(e.id, "dead", f"mod {mid} unreachable: {exc}"))
            continue

        status = info.get("status")
        if not info.get("available", True) or status not in (None, "published"):
            out.append(Finding(e.id, "dead", f"mod {mid} status={status!r} available="
                                             f"{info.get('available')}"))
            continue

        try:
            files = client.files(domain, mid)
        except NexusError as exc:
            out.append(Finding(e.id, "dead", f"file list unreachable: {exc}"))
            continue

        pinned = next((f for f in files if f.get("file_id") == fid), None)
        if pinned is None:
            # The pin is gone. This is the failure mode the whole exercise exists to catch
            # early: a user hitting it gets an unexplained install failure.
            out.append(Finding(e.id, "dead",
                               f"pinned fileId {fid} no longer exists on mod {mid}"))
            continue

        newer = _newer_than(files, fid, pinned.get("version"))
        if newer:
            out.append(Finding(e.id, "warn",
                               f"newer MAIN file available: {newer.get('file_id')} "
                               f"v{newer.get('version')} ({newer.get('file_name')}); "
                               f"pinned v{pinned.get('version')}"))
        else:
            out.append(Finding(e.id, "ok", f"fileId {fid} v{pinned.get('version')} live"))
    return out


def _head_ok(url: str) -> tuple[bool, str]:
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "modlist-agent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return (200 <= r.status < 400), str(r.status)
    except urllib.error.HTTPError as e:
        # Some hosts reject HEAD but serve GET; silverlock is one, so do not call it dead.
        if e.code in (403, 405):
            return True, f"{e.code} (HEAD not allowed; treated as live)"
        return False, str(e.code)
    except (urllib.error.URLError, OSError) as e:
        return False, str(e)


def check_offsite(manifest) -> list[Finding]:
    out: list[Finding] = []
    for e in manifest.mods + manifest.tools:
        src = e.source
        t = src.get("type")
        if t == "github":
            url = (f"https://github.com/{src['repo']}/releases/download/"
                   f"{src['tag']}/{src['asset']}")
        elif t == "http":
            url = src["url"]
        else:
            continue
        ok, note = _head_ok(url)
        out.append(Finding(e.id, "ok" if ok else "dead",
                           f"{url} -> {note}"))
    return out
