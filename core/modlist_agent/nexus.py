"""Nexus Mods API client.

Deliberately small. It does metadata and download links, and nothing else — no scraping,
no browser automation, no clicking anything on the user's behalf. See
docs/NEXUS_DOWNLOADS.md for why that boundary is where it is.

Auth is a Personal API Key, which Nexus documents as being for "applications in the
testing stage of development or intended for personal use only" — exactly this. OAuth is
the migration path if this is ever registered as a public application.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

API = "https://api.nexusmods.com/v1"
KEY_FILE = pathlib.Path(os.path.expanduser("~")) / ".nexus-api-key"


class NexusError(Exception):
    pass


class NotPremium(NexusError):
    """download_link.json refused us because the account is not Premium.

    Not a bug and not a failure of the design — it is the documented gate, and the
    answer is the nxm:// path, not a workaround.
    """


@dataclass
class NxmLink:
    """A signed download authorisation, minted by the website when a user clicks.

    nxm://<domain>/mods/<modId>/files/<fileId>?key=...&expires=...
    """
    domain: str
    mod_id: int
    file_id: int
    key: str | None
    expires: str | None

    @classmethod
    def parse(cls, url: str) -> "NxmLink":
        u = urllib.parse.urlparse(url)
        if u.scheme != "nxm":
            raise NexusError(f"not an nxm:// url: {url!r}")
        m = re.match(r"/mods/(\d+)/files/(\d+)", u.path)
        if not m:
            raise NexusError(f"unrecognised nxm path: {u.path!r}")
        q = urllib.parse.parse_qs(u.query)
        return cls(u.netloc, int(m.group(1)), int(m.group(2)),
                   (q.get("key") or [None])[0], (q.get("expires") or [None])[0])


def load_key(explicit: str | None = None) -> str:
    if explicit:
        return explicit.strip()
    if os.environ.get("NEXUS_API_KEY"):
        return os.environ["NEXUS_API_KEY"].strip()
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    raise NexusError(
        f"no API key. Set NEXUS_API_KEY or write {KEY_FILE}.\n"
        "Generate one at https://www.nexusmods.com/users/myaccount?tab=api "
        "(bottom of the page, 'Personal API Key')."
    )


class Client:
    def __init__(self, key: str | None = None):
        self.key = load_key(key)
        self.rate: dict[str, str] = {}

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(f"{API}/{path}", headers={
            "apikey": self.key,
            "User-Agent": "modlist-agent/0.1",
            # The Acceptable Use Policy asks applications to identify themselves.
            "Application-Name": "modlist-agent",
            "Application-Version": "0.1",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                self.rate = {k.lower(): v for k, v in r.headers.items()
                             if k.lower().startswith("x-rl-")}
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403 and "download_link" in path:
                raise NotPremium(
                    "Nexus refused a download link. Free accounts must supply key/expires "
                    "from an nxm:// link — click 'Mod Manager Download' on the file page."
                ) from e
            if e.code == 429:
                raise NexusError("rate limited by Nexus; back off and retry later") from e
            raise NexusError(f"HTTP {e.code} for {path}") from e

    # --- metadata: works on any account ---------------------------------------
    def validate(self) -> dict:
        return self._get("users/validate.json")

    def mod(self, domain: str, mod_id: int) -> dict:
        return self._get(f"games/{domain}/mods/{mod_id}.json")

    def files(self, domain: str, mod_id: int) -> list[dict]:
        return self._get(f"games/{domain}/mods/{mod_id}/files.json").get("files", [])

    def file(self, domain: str, mod_id: int, file_id: int) -> dict:
        return self._get(f"games/{domain}/mods/{mod_id}/files/{file_id}.json")

    # --- the one gated endpoint ------------------------------------------------
    def download_urls(self, domain: str, mod_id: int, file_id: int,
                      nxm: NxmLink | None = None) -> list[str]:
        """CDN URLs for a file, best first.

        Premium: works with the API key alone. Free: requires key+expires from an
        nxm:// link that the user produced by clicking. We never mint those ourselves.
        """
        path = f"games/{domain}/mods/{mod_id}/files/{file_id}/download_link.json"
        if nxm and nxm.key:
            path += f"?key={urllib.parse.quote(nxm.key)}&expires={nxm.expires}"
        data = self._get(path)
        return [d["URI"] for d in data if d.get("URI")]

    @staticmethod
    def file_page(domain: str, mod_id: int, file_id: int) -> str:
        """Where a human clicks 'Mod Manager Download' for the free path."""
        return (f"https://www.nexusmods.com/{domain}/mods/{mod_id}"
                f"?tab=files&file_id={file_id}&nmm=1")
