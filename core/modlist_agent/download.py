"""Fetch the pinned files, and prove they are the pinned files.

Two paths, one manifest, identical verification. Premium is a speed-up, never a
requirement, and never more trusted: everything is hashed on arrival regardless of how
it got here.
"""
from __future__ import annotations

import pathlib
import shutil
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .instance import sha256
from .nexus import Client, NotPremium, NxmLink


@dataclass
class Fetched:
    entry_id: str
    path: pathlib.Path
    sha256: str
    matched: bool | None   # True verified, False MISMATCH, None no pin to check against
    note: str = ""


def _encode(url: str) -> str:
    """Nexus CDN URLs embed the raw filename, spaces and all, so they are not valid URLs
    as returned. Encode the path (and only the path) before handing them to urllib."""
    u = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (u.scheme, u.netloc, urllib.parse.quote(u.path, safe="/%"), u.query, u.fragment))


def _download(url: str, dest: pathlib.Path) -> None:
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(_encode(url), headers={"User-Agent": "modlist-agent/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r, tmp.open("wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(dest)


def write_meta(dest: pathlib.Path, entry, domain: str) -> None:
    """MO2 writes a sibling .meta for every download; match it so a generated instance
    is indistinguishable from a hand-built one and MO2's update checks keep working."""
    src = entry.source
    dest.with_suffix(dest.suffix + ".meta").write_text(
        "[General]\n"
        f"gameName={domain}\n"
        f"modID={src.get('modId')}\n"
        f"fileID={src.get('fileId')}\n"
        f"name={entry.name}\n"
        f"version={src.get('version')}\n"
        "repository=Nexus\n"
        "installed=false\n",
        encoding="utf-8")


def _offsite_url(src: dict) -> str:
    """Same shape check.check_offsite already builds, factored out so fetch_all can
    reuse it instead of re-deriving it (and so a future third shape only changes here)."""
    if src["type"] == "github":
        return (f"https://github.com/{src['repo']}/releases/download/"
                f"{src['tag']}/{src['asset']}")
    return src["url"]   # type == "http"


def targets(manifest):
    """Entries that need fetching: pinned to a Nexus file or an off-site (github/http)
    release, and actually installed.

    root=instance is excluded: MO2 is root=instance and is fetched by ensure_mo2 during
    `build`, never by `download` — pulling it here too would be a second, redundant fetch
    path for the same file.
    """
    out = []
    for e in manifest.mods + manifest.tools:
        if e.tier == "candidate":
            continue
        if e.root == "instance":
            continue
        t = e.source.get("type")
        if t == "nexus":
            if not e.source.get("fileId"):
                continue
        elif t not in ("github", "http"):
            continue
        out.append(e)
    return out


def links_for(manifest, entries) -> list[tuple[str, str]]:
    domain = manifest.game["nexusDomain"]
    return [(e.id, Client.file_page(domain, e.source["modId"], e.source["fileId"]))
            for e in entries]


def _fetch_offsite(e, dest_dir: pathlib.Path) -> Fetched:
    """github/http entries: the URL is self-contained, so this needs no Nexus client or
    API key at all — unlike the Nexus branch of fetch_all, which always does.

    No .meta sibling is written here. write_meta's shape (modID/fileID/repository=Nexus)
    is Nexus-specific — a github/http file was never "installed via Nexus" for MO2's
    update checks to be indistinguishable about, so a Nexus-shaped .meta next to it would
    just be wrong, not merely incomplete.
    """
    want = e.file.get("sha256")
    name = e.file.get("name")

    if not name:
        # Never guess a filename — a wrong one silently re-downloads forever.
        return Fetched(e.id, dest_dir / e.id, "", None,
                       "ERROR no file.name pinned — refusing to guess a filename")
    dest = dest_dir / name

    if dest.exists():
        got = sha256(dest)
        if want and got != want:
            return Fetched(e.id, dest, got, False, "cached copy does not match pin")
        return Fetched(e.id, dest, got, (got == want) if want else None, "cached")

    try:
        _download(_offsite_url(e.source), dest)
    except (urllib.error.URLError, OSError) as exc:
        return Fetched(e.id, dest, "", None, f"ERROR {exc}")

    got = sha256(dest)
    return Fetched(e.id, dest, got, (got == want) if want else None,
                   "" if want else "no pin recorded yet")


def fetch_all(manifest, dest_dir: pathlib.Path, *, client: Client,
              nxm_links: list[NxmLink] | None = None,
              only: set[str] | None = None) -> list[Fetched]:
    domain = manifest.game["nexusDomain"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    by_file = {(l.mod_id, l.file_id): l for l in (nxm_links or [])}
    out: list[Fetched] = []

    for e in targets(manifest):
        if only and e.id not in only:
            continue
        if e.source.get("type") in ("github", "http"):
            out.append(_fetch_offsite(e, dest_dir))
            continue
        mid, fid = e.source["modId"], e.source["fileId"]
        want = e.file.get("sha256")
        name = e.file.get("name")

        if not name:
            # Ask Nexus rather than guessing a filename; a wrong name silently
            # re-downloads forever.
            try:
                name = client.file(domain, mid, fid).get("file_name")
            except Exception as exc:
                out.append(Fetched(e.id, dest_dir / f"{mid}-{fid}", "", None, f"ERROR {exc}"))
                continue
        dest = dest_dir / name

        if dest.exists():
            got = sha256(dest)
            if want and got != want:
                out.append(Fetched(e.id, dest, got, False, "cached copy does not match pin"))
                continue
            out.append(Fetched(e.id, dest, got, (got == want) if want else None, "cached"))
            continue

        try:
            urls = client.download_urls(domain, mid, fid, by_file.get((mid, fid)))
        except NotPremium as exc:
            out.append(Fetched(e.id, dest, "", None, f"NEEDS CLICK — {exc}"))
            continue
        except Exception as exc:
            out.append(Fetched(e.id, dest, "", None, f"ERROR {exc}"))
            continue
        if not urls:
            out.append(Fetched(e.id, dest, "", None, "no download URL returned"))
            continue

        last = None
        for url in urls:
            try:
                _download(url, dest)
                last = None
                break
            except (urllib.error.URLError, OSError) as exc:
                last = exc
        if last is not None:
            out.append(Fetched(e.id, dest, "", None, f"ERROR all mirrors failed: {last}"))
            continue

        got = sha256(dest)
        write_meta(dest, e, domain)
        out.append(Fetched(e.id, dest, got, (got == want) if want else None,
                           "" if want else "no pin recorded yet"))
    return out


def record_hashes(manifest_path: pathlib.Path, fetched: list[Fetched]) -> int:
    """Write freshly-computed hashes into `sha256: null` slots.

    Only fills EMPTY pins. A mismatching pin is never overwritten — that is the world
    moving, and silently re-pinning would destroy the only evidence of it.
    """
    text = manifest_path.read_text(encoding="utf-8")
    n = 0
    for f in fetched:
        if not f.sha256 or f.matched is False:
            continue
        i = text.find(f"- id: {f.entry_id}\n")
        if i < 0:
            continue
        end = text.find("\n  - id:", i + 1)
        end = len(text) if end < 0 else end
        seg = text[i:end]
        if "sha256: null" not in seg:
            continue
        seg2 = seg.replace("sha256: null   # pending download", f"sha256: {f.sha256}", 1)
        if seg2 == seg:
            seg2 = seg.replace("sha256: null", f"sha256: {f.sha256}", 1)
        text = text[:i] + seg2 + text[end:]
        n += 1
    manifest_path.write_text(text, encoding="utf-8")
    return n
