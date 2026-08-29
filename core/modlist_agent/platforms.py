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
    #: arguments MO2 must pass the extender loader. MEASURED 2026-08-29, and the reason
    #: this field exists: xSE picks its injection path from the game exe's PE sections. A
    #: stock Steam exe has a `.bind` section, so xSE injects the small steam-loader shim
    #: and the runtime DLL is LoadLibrary'd later, on the game's MAIN thread, after
    #: ResumeThread. An exe with `.bind` stripped — any Steamless-unpacked install, which
    #: is common on modded VR setups — is detected as a "normal exe", and xSE instead
    #: injects the runtime on a REMOTE thread while the main thread is still suspended.
    #: usvfs arms on ResumeThread, so that ordering puts the extender's plugin-directory
    #: scan BEFORE the virtual filesystem exists: it enumerates the bare game directory,
    #: finds no Data/F4SE at all, and loads ZERO plugins. The game then boots to the main
    #: menu looking perfectly healthy, which is the worst possible failure shape.
    #: `-forcesteamloader` overrides the detection. It is safe unconditionally: the Steam
    #: relaunch/affinity block is gated on the DETECTED type and runs before the override
    #: (f4se_loader/main.cpp:186 vs :257), so on a stock exe the flag is a no-op.
    extender_args: str = ""

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
    # Without this, an unpacked Fallout4VR.exe loads no F4SEVR plugins at all. See
    # Platform.extender_args; proven on this machine 2026-08-29 against a working
    # hand-built instance that had carried the flag all along.
    extender_args="-forcesteamloader",
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
    extender_args="-forcesteamloader",   # SKSEVR takes the same flag. UNVERIFIED, like the rest of this table.
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
