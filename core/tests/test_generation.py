"""Tests that need no game, no MO2, no headset, no network.

This is the part of the project that can run on a hosted CI runner. It covers the things
that have actually gone wrong: the ordering rule, the ini encoding traps, and archive
root detection. Each test here corresponds to a real bug, not a hypothetical one.

    python -m pytest core/tests/test_generation.py -q
"""
from __future__ import annotations

import pathlib
import sys
import textwrap

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from modlist_agent import instance, manifest as mf, platforms  # noqa: E402

MANIFEST = textwrap.dedent("""
    schema: 1
    game:
      id: fo4vr
      nexusDomain: fallout4
      runtime: "1.2.72"
    tools: []
    mods:
      - id: alpha
        name: Alpha Mod
        why: fixes a thing
        tier: fix
        enabled: true
        source: { type: nexus, modId: 1, fileId: 2, version: "1" }
        install: { root: data }
      - id: beta
        name: Beta Mod
        why: fixes another thing
        tier: fix
        enabled: false
        source: { type: nexus, modId: 3, fileId: 4, version: "1" }
        install: { root: data }
      - id: gamma
        name: Gamma Tool
        why: loads early
        tier: foundation
        enabled: true
        source: { type: nexus, modId: 5, fileId: 6, version: "1" }
        install: { root: game }
        uninstall: delete it
    order:
      install: [alpha, beta]
""")


@pytest.fixture
def man(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(MANIFEST, encoding="utf-8")
    return mf.load(p)


# --- the ordering rule -------------------------------------------------------------

def test_modlist_is_written_winner_first_with_no_reversal(man):
    """The bug this project shipped in its own spec.

    order.install is winner-first and modlist.txt is winner-first, so the output order
    must MATCH the input order. A reversal here hands every conflict to the loser while
    producing an instance that installs cleanly and looks correct.
    """
    lines = man.modlist_lines()
    assert lines[1] == "+Alpha Mod"
    assert lines[2] == "-Beta Mod"          # disabled keeps its slot, with a minus
    assert [l for l in lines if "Gamma" in l] == []   # root=game is not virtualised


def test_harness_outranks_everything(man):
    lines = man.modlist_lines(harness="devbench")
    assert lines[1] == "+devbench"
    assert lines[2] == "+Alpha Mod"


# --- validation --------------------------------------------------------------------

def test_game_root_entry_in_order_install_is_an_error(tmp_path):
    bad = MANIFEST.replace("install: [alpha, beta]", "install: [alpha, beta, gamma]")
    p = tmp_path / "bad.yaml"; p.write_text(bad, encoding="utf-8")
    with pytest.raises(mf.ManifestError, match="must NOT be in order.install"):
        mf.load(p)


def _without(line_contains: str) -> str:
    """Drop the whole line containing a token. Indentation-agnostic, because MANIFEST is
    dedented at import and matching on leading spaces silently stops matching."""
    return "\n".join(l for l in MANIFEST.splitlines() if line_contains not in l)


def test_missing_why_is_an_error(tmp_path):
    p = tmp_path / "bad.yaml"; p.write_text(_without("why: fixes a thing"), encoding="utf-8")
    with pytest.raises(mf.ManifestError, match="missing `why`"):
        mf.load(p)


def test_duplicate_mod_name_is_an_error(tmp_path):
    bad = MANIFEST.replace("name: Beta Mod", "name: Alpha Mod")
    p = tmp_path / "bad.yaml"; p.write_text(bad, encoding="utf-8")
    with pytest.raises(mf.ManifestError, match="would collide in mods/"):
        mf.load(p)


def test_game_root_requires_uninstall_note(tmp_path):
    p = tmp_path / "bad.yaml"; p.write_text(_without("uninstall: delete it"), encoding="utf-8")
    with pytest.raises(mf.ManifestError, match="requires an `uninstall` note"):
        mf.load(p)


# --- the ini encoding traps --------------------------------------------------------

def test_bytearray_doubles_backslashes():
    got = instance.bytearray_path(r"C:\Program Files (x86)\Steam")
    assert got == r"@ByteArray(C:\\Program Files (x86)\\Steam)"


def test_custom_executable_paths_use_forward_slashes():
    # The same path is spelled two different ways in one file. This is the trap.
    assert instance.exe_path(r"C:\Games\x.exe") == "C:/Games/x.exe"


def test_executable_titles_have_no_spaces():
    # 'Fallout 4 VR (vanilla)' was whitespace-split by the caller and MO2 reported
    # "Executable 'Fallout' does not exist".
    assert " " not in instance.safe_title("Fallout 4 VR (vanilla)")


def test_generated_ini_has_both_spellings(tmp_path, man):
    game = tmp_path / "game"; (game / "Data").mkdir(parents=True)
    (game / "Fallout4VR.exe").write_text("")
    inst = instance.Instance(tmp_path / "inst", platforms.FO4VR, game)
    inst.build(man)
    ini = (tmp_path / "inst" / "ModOrganizer.ini").read_text(encoding="utf-8")
    assert "gameName=Fallout 4 VR" in ini            # spaces, not the short name
    assert "@ByteArray(" in ini
    assert "\\\\" in ini                              # doubled inside @ByteArray
    assert "1\\binary=" in ini and ":/" in ini        # forward slashes outside it
    assert "first_start=false" in ini                 # no tutorial modal
    assert (tmp_path / "inst" / "portable.txt").exists()


def test_profile_uses_local_inis(tmp_path, man):
    game = tmp_path / "game"; game.mkdir()
    (game / "Fallout4VR.exe").write_text("")
    inst = instance.Instance(tmp_path / "inst", platforms.FO4VR, game)
    inst.build(man)
    s = (tmp_path / "inst" / "profiles" / "Default" / "settings.ini").read_text()
    assert "LocalSettings=true" in s


# --- archive root detection --------------------------------------------------------

@pytest.mark.parametrize("layout,expect", [
    (["F4SE/Plugins/x.dll"], "."),                    # already Data-relative
    (["Data/F4SE/Plugins/x.dll"], "Data"),            # wrapped in Data/
    (["MyMod v1.2/Data/Scripts/a.pex"], "MyMod v1.2/Data"),   # version wrapper + Data
    (["thing.esp"], "."),                             # bare plugin at root
])
def test_detect_data_root(tmp_path, layout, expect):
    """Guessing wrong installs a mod that is present and invisible to the game."""
    for rel in layout:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x")
    got = instance.Instance.detect_data_root(tmp_path)
    assert got.relative_to(tmp_path).as_posix() == pathlib.PurePath(expect).as_posix()


# --- platform seam -----------------------------------------------------------------

def test_extender_dll_name_is_runtime_specific():
    assert platforms.FO4VR.extender_dll("1.2.72") == "f4sevr_1_2_72.dll"


def test_unverified_platforms_are_declared_as_such():
    # SkyrimVR is a plausible-looking table nobody has tested. Keep that honest.
    assert "fo4vr" in platforms.VERIFIED
    assert "skyrimvr" not in platforms.VERIFIED
