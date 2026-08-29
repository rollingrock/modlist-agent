"""Generate a portable MO2 instance.

This is the manual work of 2026-08-16 turned into code. Every quirk encoded here was
learned by building an instance by hand and watching what MO2 did with it; see
docs/MO2_PORTABLE.md for the evidence behind each one.

Nothing here needs MO2's GUI. An instance is text files plus directories, and installing
a mod is placing a Data-relative directory under mods/.
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil
import subprocess
import urllib.request

SEVENZIP = pathlib.Path(r"C:\Program Files\7-Zip\7z.exe")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch(url: str, dest: pathlib.Path, expect_sha256: str | None = None) -> pathlib.Path:
    """Download unless already present and correct. Hash is checked ALWAYS, never skipped.

    A pin that is present but does not match is a hard failure: the world moved, and
    substituting is where a well-meaning agent invents a broken build.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and expect_sha256 and sha256(dest) == expect_sha256:
        return dest
    if not dest.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "modlist-agent/0.1"})
        with urllib.request.urlopen(req, timeout=120) as r, dest.open("wb") as f:
            shutil.copyfileobj(r, f)
    if expect_sha256:
        got = sha256(dest)
        if got != expect_sha256:
            raise SystemExit(
                f"hash mismatch for {dest.name}\n  expected {expect_sha256}\n  got      {got}\n"
                "Refusing to continue. Do not substitute — update the pin deliberately."
            )
    return dest


def extract(archive: pathlib.Path, dest: pathlib.Path, strip: int = 0) -> None:
    if not SEVENZIP.exists():
        raise SystemExit(f"7-Zip not found at {SEVENZIP}")
    dest.mkdir(parents=True, exist_ok=True)
    staging = dest if not strip else dest.parent / (dest.name + ".staging")
    if strip:
        shutil.rmtree(staging, ignore_errors=True)
        staging.mkdir(parents=True)
    subprocess.run([str(SEVENZIP), "x", str(archive), f"-o{staging}", "-y"],
                   check=True, capture_output=True)
    if strip:
        src = staging
        for _ in range(strip):
            kids = [p for p in src.iterdir()]
            if len(kids) != 1 or not kids[0].is_dir():
                break
            src = kids[0]
        for item in src.iterdir():
            target = dest / item.name
            if target.exists():
                shutil.rmtree(target) if target.is_dir() else target.unlink()
            shutil.move(str(item), str(target))
        shutil.rmtree(staging, ignore_errors=True)


# --- the ini encoding traps, in one place -------------------------------------------

def bytearray_path(p: pathlib.Path | str) -> str:
    """MO2 stores some values Qt-serialised, with backslashes DOUBLED inside.

    The same path is spelled differently elsewhere in the same file (see exe_path), which
    is exactly the sort of thing a naive writer gets wrong.
    """
    return "@ByteArray(" + str(p).replace("\\", "\\\\") + ")"


def exe_path(p: pathlib.Path | str) -> str:
    """[customExecutables] paths use FORWARD slashes and are not wrapped."""
    return str(p).replace("\\", "/")


def safe_title(title: str) -> str:
    """moshortcut:// arguments are whitespace-split by callers, so titles must not
    contain spaces. A title of 'Fallout 4 VR (vanilla)' produced
    "Executable 'Fallout' does not exist" — see docs/MO2_PORTABLE.md §4."""
    return "".join(c for c in title.replace(" ", "") if c.isalnum() or c in "-_")


class Instance:
    def __init__(self, path: pathlib.Path, platform, game_path: pathlib.Path,
                 profile: str = "Default"):
        self.path = pathlib.Path(path)
        self.platform = platform
        self.game_path = pathlib.Path(game_path)
        self.profile = profile

    # --- paths -----------------------------------------------------------------
    @property
    def mods(self) -> pathlib.Path: return self.path / "mods"
    @property
    def profile_dir(self) -> pathlib.Path: return self.path / "profiles" / self.profile
    @property
    def exe(self) -> pathlib.Path: return self.path / "ModOrganizer.exe"

    # --- MO2 itself ------------------------------------------------------------
    def ensure_mo2(self, tool, cache: pathlib.Path) -> None:
        if self.exe.exists():
            return
        src = tool.source
        url = (f"https://github.com/{src['repo']}/releases/download/"
               f"{src['tag']}/{src['asset']}")
        archive = fetch(url, cache / src["asset"], tool.file.get("sha256"))
        extract(archive, self.path)

    # --- generation ------------------------------------------------------------
    def build(self, manifest, harness: str | None = None) -> list[str]:
        """Write the whole instance. Returns a log of what it did."""
        did = []
        self._harness = harness
        for d in (self.mods, self.path / "downloads", self.path / "overwrite", self.profile_dir):
            d.mkdir(parents=True, exist_ok=True)

        # portable.txt does not *make* it portable — ModOrganizer.ini living next to the
        # exe does that. It suppresses the instance-manager dialog, which an unattended
        # agent must never meet.
        (self.path / "portable.txt").write_text("", encoding="ascii")

        self._write_ini()
        self._write_profile(manifest)
        did.append(f"instance at {self.path}")
        return did

    def _executables(self) -> list[tuple[str, pathlib.Path, str]]:
        p = self.platform
        probe = self.path / "vfsprobe.ps1"
        return [
            (safe_title(p.extender_loader.split("_")[0].upper()),
             self.game_path / p.extender_loader, p.extender_args),
            ("Vanilla", self.game_path / p.game_exe, ""),
            # Runs an arbitrary script inside usvfs without starting the game. Every
            # generated instance gets one so it can be tested — notably by
            # core/tests/test-conflict-order.ps1, which needs to observe the virtual
            # Data directory. The script itself is written by whoever runs the test.
            ("VfsProbe", pathlib.Path(
                r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"),
             f"-ExecutionPolicy Bypass -File {exe_path(probe)}"),
        ]

    def _write_ini(self) -> None:
        p = self.platform
        lines = [
            "[General]",
            f"gameName={p.mo2_game_name}",
            f"selected_profile={bytearray_path(self.profile)}",
            f"gamePath={bytearray_path(self.game_path)}",
            "version=2.5.2",
            # Suppresses the first-run tutorial: another modal an agent must not meet.
            "first_start=false",
            "backup_install=false",
            "",
            "[Settings]",
            # Profile-local inis keep the agent's hardware tuning inside the instance,
            # so it is versionable and reversible by deleting a directory, instead of
            # mutating the user's Documents.
            "profile_local_inis=true",
            "profile_local_saves=false",
            "profile_archive_invalidation=true",
            "",
            "[customExecutables]",
        ]
        execs = self._executables()
        lines.append(f"size={len(execs)}")
        for i, (title, binary, args) in enumerate(execs, start=1):
            lines += [
                f"{i}\\title={title}",
                f"{i}\\binary={exe_path(binary)}",
                f"{i}\\workingDirectory={exe_path(binary.parent)}",
                f"{i}\\arguments={args}",
                f"{i}\\hide=false",
                f"{i}\\ownicon=true",
                f"{i}\\steamAppID=",
                f"{i}\\toolbar=false",
            ]
        (self.path / "ModOrganizer.ini").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _write_profile(self, manifest) -> None:
        p = self.platform
        d = self.profile_dir

        (d / "modlist.txt").write_text(
            "\n".join(manifest.modlist_lines(getattr(self, "_harness", None))) + "\n",
            encoding="utf-8")

        plugins = list(p.plugins_header) + [f"*{n}" for n in p.base_plugins]
        for e in manifest.installable():
            for pl in e.raw.get("plugins") or []:
                if not pl.startswith("UNVERIFIED"):
                    plugins.append(f"*{pl}")
        (d / "plugins.txt").write_text("\n".join(plugins) + "\n", encoding="utf-8")

        loadorder = ["# This file was automatically generated by Mod Organizer."]
        loadorder += list(p.base_plugins)
        loadorder += [x.lstrip("*") for x in plugins if x.startswith("*")
                      and x.lstrip("*") not in p.base_plugins]
        (d / "loadorder.txt").write_text("\n".join(loadorder) + "\n", encoding="utf-8")

        (d / "lockedorder.txt").write_text(
            "# This file was automatically generated by Mod Organizer.\n", encoding="utf-8")
        (d / "settings.ini").write_text(
            "[General]\nLocalSaves=false\nLocalSettings=true\n"
            "AutomaticArchiveInvalidation=true\n", encoding="utf-8")
        (d / "initweaks.ini").write_text("[Archive]\nbInvalidateOlderFiles=1\n", encoding="utf-8")

        # Seed the profile inis from the game's shipped defaults, so MO2 has something to
        # work from without us touching the user's Documents.
        for name in p.ini_names:
            target = d / name
            if target.exists():
                continue
            shipped = self.game_path / name
            if shipped.exists():
                shutil.copy2(shipped, target)
            elif name == p.tuning_ini:
                target.write_text(
                    "; Written by modlist-agent. The ADAPTIVE half of the recipe lives\n"
                    "; in this file: nothing here is pinned.\n\n"
                    "[Archive]\nbInvalidateOlderFiles=1\nsResourceDataDirsFinal=\n",
                    encoding="utf-8")

    # --- mods ------------------------------------------------------------------
    # --- archives --------------------------------------------------------------
    #: directories/extensions that mark a directory as being the Data root
    DATA_MARKERS = {"f4se", "skse", "scripts", "meshes", "textures", "interface",
                    "materials", "sound", "music", "video", "strings"}
    PLUGIN_EXT = {".esp", ".esm", ".esl", ".ba2", ".bsa"}

    @classmethod
    def detect_data_root(cls, top: pathlib.Path) -> pathlib.Path:
        """Find the directory inside an extracted archive that maps to Data/.

        Authors package inconsistently: some ship `Data/F4SE/...`, some ship `F4SE/...`,
        some wrap everything in a version-named folder. Guessing wrong installs a mod
        that is present but invisible to the game — it looks fine and does nothing.
        """
        cur = top
        for _ in range(4):
            entries = list(cur.iterdir())
            if not entries:
                return cur
            names = {p.name.lower() for p in entries}
            if names & cls.DATA_MARKERS or any(
                    p.suffix.lower() in cls.PLUGIN_EXT for p in entries):
                return cur
            # A lone `Data` wrapper, or a lone version-named wrapper: descend.
            dirs = [p for p in entries if p.is_dir()]
            if len(entries) == 1 and dirs:
                cur = dirs[0]
                continue
            if len(dirs) == 1 and dirs[0].name.lower() == "data":
                cur = dirs[0]
                continue
            return cur
        return cur

    def install_archive(self, entry, archive: pathlib.Path, staging: pathlib.Path) -> str:
        """Extract an archive and place it as a mod (root=data) or into the game (root=game)."""
        work = staging / entry.id
        shutil.rmtree(work, ignore_errors=True)
        extract(archive, work, strip=entry.install.get("strip", 0))

        if entry.root == "game":
            return self._install_into_game(entry, work)

        root = self.detect_data_root(work)
        dest = self.mods / entry.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(root, dest)
        self._write_meta(entry, dest)
        rel = root.relative_to(work)
        return (f"installed {entry.name}"
                + (f" (data root: {rel})" if str(rel) != "." else ""))

    def _install_into_game(self, entry, work: pathlib.Path) -> str:
        """Copy declared files into the game directory, backing up anything it replaces.

        These are the only files that live outside the instance, so they are the only
        ones deleting the instance does not undo.
        """
        wanted = entry.install.get("files")
        root = work
        kids = [p for p in work.iterdir()]
        if len(kids) == 1 and kids[0].is_dir():
            root = kids[0]
        copied, backed = [], []
        for item in root.rglob("*"):
            if item.is_dir():
                continue
            rel = item.relative_to(root)
            if wanted and not any(str(rel).lower().startswith(w.lower().rstrip("/"))
                                  for w in wanted):
                continue
            target = self.game_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                bak = target.with_suffix(target.suffix + ".modlist-agent.bak")
                if not bak.exists():
                    shutil.copy2(target, bak)
                    backed.append(str(rel))
            shutil.copy2(item, target)
            copied.append(str(rel))
        msg = f"installed {entry.name} into the GAME directory ({len(copied)} file(s))"
        if backed:
            msg += f"; backed up {', '.join(backed)}"
        return msg

    def _write_meta(self, entry, dest: pathlib.Path) -> None:
        meta = [
            "[General]",
            f"gameName={self.platform.mo2_short_name}",
            f"modid={entry.source.get('modId', 0)}",
            f"version={entry.source.get('version', '0.0.0.0')}",
        ]
        if entry.source.get("type") == "nexus":
            meta.append("repository=Nexus")
        if entry.file.get("name"):
            meta.append(f"installationFile={entry.file['name']}")
        if entry.source.get("fileId"):
            meta += ["", "[installedFiles]", "size=1",
                     f"1\\modid={entry.source['modId']}",
                     f"1\\fileid={entry.source['fileId']}"]
        (dest / "meta.ini").write_text("\n".join(meta) + "\n", encoding="utf-8")

    def install_dir(self, name: str, src: pathlib.Path, note: str = "") -> str:
        """Place a plain directory as a mod. Used for the verification harness."""
        dest = self.mods / name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        (dest / "meta.ini").write_text(
            f"[General]\ngameName={self.platform.mo2_short_name}\nmodid=0\n"
            f"version=0.0.0.0\nnotes=\"{note}\"\n", encoding="utf-8")
        return f"installed {name}"

    def install_local(self, entry, src: pathlib.Path) -> str:
        """Install a mod from an already-extracted directory.

        Mechanically this is all installing a mod is: place a Data-relative directory
        under mods/<name>/. That is why no GUI is needed.
        """
        dest = self.mods / entry.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
        meta = [
            "[General]",
            f"gameName={self.platform.mo2_short_name}",
            f"modid={entry.source.get('modId', 0)}",
            f"version={entry.source.get('version', '0.0.0.0')}",
        ]
        if entry.source.get("type") == "nexus":
            meta.append("repository=Nexus")
        if entry.source.get("fileId"):
            meta += ["", "[installedFiles]", "size=1",
                     f"1\\modid={entry.source['modId']}",
                     f"1\\fileid={entry.source['fileId']}"]
        (dest / "meta.ini").write_text("\n".join(meta) + "\n", encoding="utf-8")
        return f"installed {entry.name}"
