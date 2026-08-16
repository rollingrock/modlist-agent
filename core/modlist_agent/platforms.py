"""Per-game seams. Everything else in core/ is game-neutral.

The README's "start multi-game, cheaply" applies here: `devbench` next door began
Skyrim-only and paid an expensive restructure once Fallout arrived. The seam costs almost
nothing to define now.

A platform answers only the questions that genuinely differ between games. If something
can be derived from the manifest or is the same everywhere, it does NOT belong here —
a fat platform interface is how the game-neutral core rots back into a per-game one.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Platform:
    #: manifest `game.id`
    id: str
    #: exact string MO2 wants in ModOrganizer.ini [General] gameName — often has spaces
    mo2_game_name: str
    #: MO2's short name: the --game= argument, and the Documents\My Games\<x> folder
    mo2_short_name: str
    steam_app_id: int
    #: folder under steamapps/common
    steam_dir_name: str
    #: the executable whose version is the runtime we pin against
    game_exe: str
    #: script extender loader launched through MO2
    extender_loader: str
    #: extender's runtime DLL, formatted with the runtime version (dots -> underscores)
    extender_dll_fmt: str
    #: game ini basenames, in the profile when LocalSettings=true
    ini_names: tuple[str, ...]
    #: the ini the agent is allowed to tune — the adaptive half writes only here
    tuning_ini: str
    #: devbench's default port for this game+runtime, used by verification
    devbench_port: int
    #: header MO2/the game expect at the top of plugins.txt
    plugins_header: tuple[str, ...] = ()
    #: plugins always present, in load order, before anything a mod adds
    base_plugins: tuple[str, ...] = ()
    #: extra files the extender needs in the game dir, beyond the loader
    extender_extra: tuple[str, ...] = field(default_factory=tuple)

    def extender_dll(self, runtime: str) -> str:
        return self.extender_dll_fmt.format(runtime=runtime.replace(".", "_"))


FO4VR = Platform(
    id="fo4vr",
    # Verified 2026-08-16 from MO2's own log and the literal string in game_fallout4vr.dll.
    mo2_game_name="Fallout 4 VR",
    mo2_short_name="Fallout4VR",
    steam_app_id=611660,
    steam_dir_name="Fallout 4 VR",
    game_exe="Fallout4VR.exe",
    extender_loader="f4sevr_loader.exe",
    extender_dll_fmt="f4sevr_{runtime}.dll",
    extender_extra=("f4sevr_steam_loader.dll",),
    # NOT Fallout4VR*.ini — FO4VR uses the flat-Fallout names. Verified in the MO2 plugin.
    ini_names=("Fallout4.ini", "Fallout4Custom.ini", "Fallout4Prefs.ini"),
    tuning_ini="Fallout4Custom.ini",
    devbench_port=8931,
    plugins_header=(
        "# This file is used by Fallout 4 VR to keep track of your downloaded content.",
        "# Please do not modify this file.",
    ),
    base_plugins=("Fallout4.esm", "Fallout4_VR.esm"),
)

# Declared, NOT tested. Present to keep the seam honest: adding a game should mean filling
# this table, and if it ever needs more than a table the abstraction is wrong. Every field
# below is a plausible guess and none has been verified against a real instance.
SKYRIMVR = Platform(
    id="skyrimvr",
    mo2_game_name="Skyrim VR",
    mo2_short_name="SkyrimVR",
    steam_app_id=611670,
    steam_dir_name="SkyrimVR",
    game_exe="SkyrimVR.exe",
    extender_loader="sksevr_loader.exe",
    extender_dll_fmt="sksevr_{runtime}.dll",
    extender_extra=("sksevr_steam_loader.dll",),
    ini_names=("Skyrim.ini", "SkyrimCustom.ini", "SkyrimPrefs.ini"),
    tuning_ini="SkyrimCustom.ini",
    devbench_port=8921,
    plugins_header=("# This file is used by Skyrim VR to keep track of your downloaded content.",),
    base_plugins=("Skyrim.esm", "Update.esm"),
)

_REGISTRY = {p.id: p for p in (FO4VR, SKYRIMVR)}
VERIFIED = {"fo4vr"}


def get(game_id: str) -> Platform:
    try:
        return _REGISTRY[game_id]
    except KeyError:
        raise SystemExit(
            f"no platform for game id {game_id!r}; known: {', '.join(sorted(_REGISTRY))}"
        )
