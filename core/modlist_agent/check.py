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

import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .nexus import Client, NexusError


@dataclass
class Finding:
    entry_id: str
    level: str          # ok | warn | dead | unreachable
    message: str


def _norm(v: str | None) -> str:
    s = (v or "").strip().lstrip("vV").lower()
    parts = s.split(".")
    while len(parts) > 1 and parts[-1] in ("0", ""):
        parts.pop()
    return ".".join(parts) or "0"


def _newer_than(files: list[dict], file_id: int, pinned_version: str | None,
                category: str = "MAIN") -> dict | None:
    """The newest file in `category`, if it is a genuine upgrade over the pinned one.

    Two ways this goes wrong if left naive, both observed on this recipe:

    1. Multi-variant mods (No DLC / DLC / Automatron, or a FOMOD alongside standalones)
       publish siblings under the SAME version. Those are variants, not upgrades.
    2. **"Newest MAIN" is sometimes the wrong file entirely.** Mod 21497's MAIN is the
       flat Fallout 4 build; its VR build ships as OPTIONAL. Recommending the MAIN there
       would tell a maintainer to install a non-VR mod into a VR recipe.

    So the category is declarable per entry, via `drift.trackCategory`.
    """
    pool = [f for f in files if f.get("category_name") == category]
    if not pool:
        return None
    newest = max(pool, key=lambda f: f.get("uploaded_timestamp") or 0)
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

        drift = e.raw.get("drift") or {}
        if drift.get("ignoreNewer"):
            # Suppression must carry a reason, so it is a decision rather than a shrug.
            out.append(Finding(e.id, "ok", f"fileId {fid} live; upgrades ignored — "
                                           f"{drift['ignoreNewer']}"))
            continue

        newer = _newer_than(files, fid, pinned.get("version"),
                            drift.get("trackCategory", "MAIN"))
        if newer:
            out.append(Finding(e.id, "warn",
                               f"newer MAIN file available: {newer.get('file_id')} "
                               f"v{newer.get('version')} ({newer.get('file_name')}); "
                               f"pinned v{pinned.get('version')}"))
        else:
            out.append(Finding(e.id, "ok", f"fileId {fid} v{pinned.get('version')} live"))
    return out


def _head_once(url: str) -> tuple[str, str]:
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "modlist-agent/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return ("ok" if 200 <= r.status < 400 else "dead"), str(r.status)
    except urllib.error.HTTPError as e:
        # Some hosts reject HEAD but serve GET; silverlock is one, so do not call it dead.
        if e.code in (403, 405):
            return "ok", f"{e.code} (HEAD not allowed; treated as live)"
        return "dead", str(e.code)
    except (urllib.error.URLError, OSError) as e:
        # THE HOST DID NOT ANSWER. That is not the same claim as "the file is gone", and
        # collapsing the two is how a check turns someone else's outage into our failure.
        return "unreachable", str(e)


def _head(url: str, attempts: int = 3) -> tuple[str, str]:
    """Reachability, three-state, with retries for the unreachable case only.

    MEASURED 2026-09-07: the scheduled drift run went red because
    http://f4se.silverlock.org/beta/f4sevr_0_6_21.7z timed out from a GitHub runner
    (WinError 10060) while answering 301 in 0.16s from the developer's machine. The pin
    was not dead, silverlock was not down for the world, and CI reported "1 dead" — a
    third party's egress being a red board is noise, and noise is how a real dead pin
    later gets waved through.

    A definite HTTP answer is returned immediately; only a connection failure is retried,
    since that is the one that is plausibly transient.
    """
    last = ("unreachable", "no attempt made")
    for i in range(max(1, attempts)):
        state, note = _head_once(url)
        if state != "unreachable":
            return state, note
        last = (state, note)
        if i + 1 < attempts:
            time.sleep(2 * (i + 1))
    return last[0], f"{last[1]} (after {attempts} attempts)"


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
        state, note = _head(url)
        out.append(Finding(e.id, state, f"{url} -> {note}"))
    return out
