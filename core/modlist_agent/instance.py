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

from . import discover

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


# --- manifest-spelled paths, resolved against a real extracted mod -------------------

def mod_relative_parts(rel: str) -> list[str]:
    """Split a manifest-spelled relative path into components, refusing any escape.

    `postInstall: delete` takes its path out of a text file and unlinks what it names, so
    the one thing that must not be expressible is leaving mods/<name>/.
    """
    s = str(rel).strip().replace("\\", "/")
    parts = [p for p in s.split("/") if p not in ("", ".")]
    if not parts or s.startswith("/") or ":" in s or ".." in parts:
        raise ValueError(
            f"{rel!r} must be a relative path that stays inside the mod directory")
    return parts


def resolve_insensitive(root: pathlib.Path, parts: list[str]) -> pathlib.Path | None:
    """Walk `parts` under `root`, matching each component case-insensitively.

    The manifest writes `interface/MultiActivateMenu.swf`; the archive ships
    `Interface/MultiActivateMenu.swf`. verify.preflight gets away with only swapping the
    separators because NTFS folds the case for it, but that makes the answer depend on the
    filesystem the code is sitting on. Fold it here instead, so the same manifest resolves
    the same way everywhere. Returns None when a component has no match.
    """
    cur = root
    for part in parts:
        if not cur.is_dir():
            return None
        # Listed, not asked. A `(cur / part).exists()` short-circuit lets NTFS answer
        # first, which is both the dependency this function exists to remove and
        # untestable on windows-latest — the only runner the hosted tier has.
        hits = [c for c in cur.iterdir() if c.name.lower() == part.lower()]
        if len(hits) != 1:             # 0 = absent; >1 only on a case-sensitive fs
            return None
        cur = hits[0]
    return cur


def wants_file(rel: pathlib.PurePath, wanted: list[str] | None) -> bool:
    """Is `rel` covered by an `install.files` entry? Empty/absent `wanted` means all.

    SEPARATORS ARE NORMALISED ON BOTH SIDES, and that is the entire point of this
    function existing. `str(rel)` yields backslashes on Windows; the manifest spells
    directories with forward slashes, the way every other path key in the schema does.
    The previous `str(rel).lower().startswith(w.lower().rstrip("/"))` therefore compared
    `data\\scripts\\actor.pex` against `data/scripts` and matched NOTHING — so every
    multi-component entry silently installed zero files while `install` reported success
    and a plausible-looking file count. Both recipes declare `Data/Scripts/` for the
    script extender, so neither has ever actually had the F4SE Papyrus scripts on disk.

    Matching is component-wise rather than a raw prefix, so `Data/Scripts` covers
    `Data/Scripts/Actor.pex` but not a sibling `Data/ScriptsBackup/x.pex`.
    """
    if not wanted:
        return True
    r = rel.as_posix().lower()
    for w in wanted:
        pref = str(w).replace("\\", "/").strip("/").lower()
        if pref and (r == pref or r.startswith(pref + "/")):
            return True
    return False


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

        # PLUGIN ORDER IS NOT INSTALL ORDER, and deriving one from the other inverts it.
        # `order.install` is modlist.txt: file-conflict priority, WINNER FIRST. plugins.txt
        # is load order, where a LATER plugin wins record conflicts. So a mod that must win
        # files goes first in one file and usually last in the other.
        #
        # Taking the order from installable() got that wrong the first time it mattered:
        # PRP sits above UFO4P in order.install because its loose files must win, and the
        # derived plugins.txt then loaded prp.esp BEFORE the unofficial patch — handing
        # every overlapping record to the patch, when PRP's previs is built against it and
        # must win. `order.plugins` already declared the right answer and nothing read it.
        #
        # It is used as a SORT KEY, not as the file's contents. Entries it lists that no
        # installed mod contributes — the DLC, which are engine-loaded and deliberately
        # absent from plugins.txt — stay documentation. Anything a mod contributes but the
        # list forgets keeps its manifest order at the end, so a missing entry degrades to
        # the old behaviour instead of silently dropping a plugin.
        declared = [str(x).lower() for x in (manifest.order.get("plugins") or [])]
        rank = {n: i for i, n in enumerate(declared)}
        contributed = [pl for e in manifest.installable()
                       for pl in (e.raw.get("plugins") or [])
                       if not pl.startswith("UNVERIFIED")]
        contributed.sort(key=lambda pl: rank.get(pl.lower(), len(rank)))   # stable

        plugins = list(p.plugins_header) + [f"*{n}" for n in p.base_plugins]
        plugins += [f"*{pl}" for pl in contributed]
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

        # Seed the profile inis, so the generated instance is complete before MO2 has ever
        # been run against it. Three sources, in order, and the second and third exist
        # because the first silently covers only FO4VR:
        #
        #   1. <game>/<name>            — FO4VR ships Fallout4.ini and Fallout4Prefs.ini
        #                                 in the game root, so this is a plain copy there.
        #   2. platform.ini_templates   — flat Fallout 4 ships only Fallout4_Default.ini.
        #   3. Documents/My Games/<x>/  — read-only, and the same place MO2 takes it from.
        #                                 Nothing here writes to Documents.
        #
        # MEASURED 2026-09-07: with only rule 1, a generated flat FO4 profile had NO
        # fallout4.ini and NO fallout4prefs.ini, and MO2 said so in its own log — "missing
        # fallout4.ini in C:/Modding/mo2_fo4/profiles/Default" — then seeded them itself on
        # first launch. The instance therefore looked fine, and only looked fine because a
        # GUI we are trying not to depend on quietly repaired it.
        templates = dict(p.ini_templates)
        docs = discover.documents_dir(p)
        for name in p.ini_names:
            target = d / name
            if target.exists():
                continue
            candidates = [self.game_path / name]
            if name != p.tuning_ini:
                # THE TUNING INI IS OURS AND IS NEVER IMPORTED. It is the adaptive half,
                # and it carries the archive-invalidation settings that make loose mod
                # files load at all. Both games have a Fallout4Custom.ini sitting in
                # Documents — 41 bytes of window position on this machine — so adding the
                # Documents fallback without this guard copied that over the stub and
                # dropped bInvalidateOlderFiles/sResourceDataDirsFinal on any FRESH
                # profile, for FO4VR as much as flat. Caught before it shipped only
                # because the existing instances already had the file and skipped the
                # branch. Rule 1 stays: if a game ever ships one, that still wins.
                if name in templates:
                    candidates.append(self.game_path / templates[name])
                candidates.append(docs / name)
            shipped = next((c for c in candidates if c.exists() and c.is_file()), None)
            if shipped:
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
            if entry.raw.get("postInstall"):
                # Refused, not implemented. A delete here would remove a file from the
                # user's game directory: outside the instance, outside the .bak
                # _install_into_game takes, and outside anything the `uninstall` note can
                # restore. manifest.validate() says the same, but `install` loads the
                # manifest non-strict, so the check has to exist on this side too.
                raise SystemExit(
                    f"{entry.id}: postInstall is not supported for root=game — it would "
                    "delete from the game directory, outside the instance")
            return self._install_into_game(entry, work)

        root = self.detect_data_root(work)
        dest = self.mods / entry.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(root, dest)
        removed = self._post_install(entry, dest)
        self._write_meta(entry, dest)
        rel = root.relative_to(work)
        return (f"installed {entry.name}"
                + (f" (data root: {rel})" if str(rel) != "." else "")
                + (f"; postInstall deleted {', '.join(removed)}" if removed else ""))

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
            if not wants_file(rel, wanted):
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

    def _post_install(self, entry, dest: pathlib.Path) -> list[str]:
        """Apply `postInstall` to a mod that has just been placed under mods/.

        Runs on EVERY install, because every install is rmtree + copytree from the source:
        whatever a previous run removed is back. Not hypothetical — full-dialog-vr has
        declared `postInstall: - delete: interface/MultiActivateMenu.swf` since
        2026-08-16 and nothing anywhere read the key, so on 2026-08-29 the operator
        deleted the file by hand and the next `mla install` copied it straight back in.

        `delete` is the only operation, because it is the only one anybody declared.
        manifest.validate() checks the same rules up front, but `mla install` loads the
        manifest non-strict, so the checks below are the ones that actually run.
        """
        removed: list[str] = []
        for step in entry.raw.get("postInstall") or []:
            if not isinstance(step, dict) or len(step) != 1:
                raise SystemExit(f"{entry.id}: each postInstall step is a single "
                                 f"`op: path` mapping, got {step!r}")
            (op, rel), = step.items()
            if op != "delete":
                raise SystemExit(
                    f"{entry.id}: postInstall operation {op!r} is declared and not "
                    "implemented. Refusing to install a mod whose recipe asks for "
                    "something this build cannot do.")
            try:
                parts = mod_relative_parts(rel)
            except ValueError as exc:
                raise SystemExit(f"{entry.id}: postInstall delete {exc}") from None
            target = resolve_insensitive(dest, parts)
            if target is None:
                # Not treated as already-done. The source is pinned by hash, so what it
                # contains is deterministic: an absent target means the declaration has
                # stopped describing it, and continuing would print `[ ok ] installed
                # <mod>` over a fix that was never applied.
                raise SystemExit(
                    f"{entry.id}: postInstall delete {rel!r} — not present in "
                    f"mods/{entry.name}/. Either the path is wrong or the source changed; "
                    f"refusing to report a fix that did not happen. mods/{entry.name}/ is "
                    "left in place for inspection.")
            shutil.rmtree(target) if target.is_dir() else target.unlink()
            removed.append(str(rel))
        return removed

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
        # Same rmtree + copytree, so the same restoration problem: a --local mod gets the
        # same postInstall treatment as one that came out of an archive.
        removed = self._post_install(entry, dest)
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
        return (f"installed {entry.name}"
                + (f"; postInstall deleted {', '.join(removed)}" if removed else ""))
