"""Find what is already on this machine.

The adaptive half of the design starts here. Nothing in this module is pinned; it is all
"what does the world look like right now", and every answer is reported rather than
assumed.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

DEFAULT_STEAM = [
    r"C:\Program Files (x86)\Steam",
    r"C:\Steam",
]


@dataclass
class GameInstall:
    path: pathlib.Path
    exe: pathlib.Path
    runtime: str | None
    in_program_files: bool


def steam_roots() -> list[pathlib.Path]:
    """Every Steam library on the machine, from libraryfolders.vdf."""
    roots: list[pathlib.Path] = []
    for base in DEFAULT_STEAM:
        b = pathlib.Path(base)
        if not b.exists():
            continue
        roots.append(b)
        vdf = b / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            # The vdf format has changed shape across Steam versions; the one stable
            # thing is a quoted "path" value, so match that rather than parse properly.
            for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
                p = pathlib.Path(m.group(1).replace("\\\\", "\\"))
                if p.exists() and p not in roots:
                    roots.append(p)
    return roots


def file_version(exe: pathlib.Path) -> str | None:
    """Windows file version, e.g. '1.2.72'. None if it cannot be read.

    Shells out to PowerShell rather than parsing the PE version resource: this project is
    Windows-only by nature, and a wrong version silently pinned is worse than a slow one
    read correctly.
    """
    if sys.platform != "win32":
        return None
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             f"(Get-Item -LiteralPath '{exe}').VersionInfo.FileVersion"],
            capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    v = (out.stdout or "").strip()
    if not v:
        return None
    # FileVersion is usually 'a.b.c.d'; the runtime we pin against is the first three.
    parts = v.split(".")
    return ".".join(parts[:3]) if len(parts) >= 3 else v


def find_game(platform) -> GameInstall | None:
    for root in steam_roots():
        p = root / "steamapps" / "common" / platform.steam_dir_name
        exe = p / platform.game_exe
        if exe.exists():
            return GameInstall(
                path=p,
                exe=exe,
                runtime=file_version(exe),
                # MO2 warns about this on every start; surface it once rather than
                # letting the user meet it as a mystery permission error later.
                in_program_files="program files" in str(p).lower(),
            )
    return None


def documents_dir(platform) -> pathlib.Path:
    return pathlib.Path.home() / "Documents" / "My Games" / platform.mo2_short_name


def extender_log(platform) -> pathlib.Path:
    """Where the script extender writes. The discriminator when verification fails."""
    return documents_dir(platform) / platform.extender_loader.split("_")[0].upper()
