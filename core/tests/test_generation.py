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

from modlist_agent import cli, instance, manifest as mf, platforms  # noqa: E402

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
        postInstall:
          - delete: interface/MultiActivateMenu.swf
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


# --- build argument validation -----------------------------------------------------
# Still no game, no MO2, no network: cmd_build rejects a bad argument before it looks at
# the machine, so every one of these runs on the hosted runner like the rest of the file.

@pytest.fixture
def man_file(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(MANIFEST, encoding="utf-8")
    return p


def test_bad_local_id_is_rejected_before_the_instance_is_written(man_file, tmp_path, capsys):
    """2026-08-29: this check ran AFTER ensure_mo2 had extracted ~150 MB of MO2 into the
    instance, so a mistyped id cost a download and left a half-built directory behind."""
    inst = tmp_path / "inst"
    rc = cli.main(["build", str(man_file), "--instance", str(inst),
                   "--local", f"alfa={tmp_path}"])
    assert rc == 1
    assert "no such mod in the manifest" in capsys.readouterr().out
    assert not inst.exists()


def test_missing_local_source_is_rejected_before_the_instance_is_written(man_file, tmp_path,
                                                                        capsys):
    """The source directory used to be checked last, after build() had already written
    modlist.txt naming a mod that was never installed."""
    inst = tmp_path / "inst"
    rc = cli.main(["build", str(man_file), "--instance", str(inst),
                   "--local", f"alpha={tmp_path / 'nope'}"])
    assert rc == 1
    assert "does not exist" in capsys.readouterr().out
    assert not inst.exists()


def test_missing_harness_is_rejected_before_the_instance_is_written(man_file, tmp_path, capsys):
    """--harness was not validated at all: a wrong path raised a raw copytree
    FileNotFoundError, with the harness already listed first in modlist.txt."""
    inst = tmp_path / "inst"
    rc = cli.main(["build", str(man_file), "--instance", str(inst),
                   "--harness", str(tmp_path / "nope")])
    assert rc == 1
    assert "--harness" in capsys.readouterr().out
    assert not inst.exists()


def test_harness_must_be_a_directory(man_file, tmp_path, capsys):
    f = tmp_path / "devbench.zip"; f.write_text("x")
    rc = cli.main(["build", str(man_file), "--instance", str(tmp_path / "inst"),
                   "--harness", str(f)])
    assert rc == 1
    assert "is not a directory" in capsys.readouterr().out


def test_unknown_post_install_operation_is_an_error(tmp_path):
    # An operation nobody implemented would parse, do nothing, and read as a fix in
    # place — which is exactly how `delete` itself shipped for a fortnight.
    bad = MANIFEST.replace("- delete: interface/", "- move: interface/")
    p = tmp_path / "bad.yaml"; p.write_text(bad, encoding="utf-8")
    with pytest.raises(mf.ManifestError, match="unknown postInstall operation"):
        mf.load(p)


def test_post_install_on_a_game_root_entry_is_an_error(tmp_path):
    # gamma is root=game. A delete there lands in the user's game directory: outside the
    # instance, outside the .bak, outside anything the `uninstall` note can restore.
    bad = MANIFEST.replace("uninstall: delete it",
                           "uninstall: delete it\n    postInstall:\n      - delete: x.dll")
    p = tmp_path / "bad.yaml"; p.write_text(bad, encoding="utf-8")
    with pytest.raises(mf.ManifestError, match="not supported for root=game"):
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


# --- postInstall -------------------------------------------------------------------

def _extracted_mod(tmp_path, with_target=True):
    """A mod directory the way an archive really ships one: Windows-cased Interface/."""
    src = tmp_path / "src"
    (src / "Interface").mkdir(parents=True)
    (src / "Interface" / "Keep.swf").write_text("keep")
    if with_target:
        (src / "Interface" / "MultiActivateMenu.swf").write_text("delete me")
    return src


def _built(tmp_path, man):
    game = tmp_path / "game"; game.mkdir()
    inst = instance.Instance(tmp_path / "inst", platforms.FO4VR, game)
    inst.build(man)
    return inst


def test_post_install_delete_runs_on_every_install(tmp_path, man):
    """The key was declared in the manifest and implemented nowhere.

    Installing is rmtree + copytree from the source EVERY time, so deleting the file by
    hand survives exactly until the next install. Installing twice is the test. The
    manifest spells the path `interface/...` and the source ships `Interface/...`; that
    mismatch is the real one, out of full-dialog-vr.
    """
    inst = _built(tmp_path, man)
    src = _extracted_mod(tmp_path)
    dest = inst.mods / "Alpha Mod"
    for _ in range(2):
        msg = inst.install_local(man.mods[0], src)
        assert not (dest / "Interface" / "MultiActivateMenu.swf").exists()
        assert (dest / "Interface" / "Keep.swf").exists()   # only what was declared goes
        # A silent delete is the class of thing this repo dislikes: say what was removed,
        # in the line the operator actually reads.
        assert "postInstall deleted interface/MultiActivateMenu.swf" in msg


def test_post_install_delete_fails_when_the_target_is_absent(tmp_path, man):
    """No-op is not on the menu. The source is pinned by hash, so an absent target means
    the declaration stopped describing it — and the alternative is an `[ ok ] installed`
    line over a fix that never happened."""
    inst = _built(tmp_path, man)
    with pytest.raises(SystemExit, match="MultiActivateMenu"):
        inst.install_local(man.mods[0], _extracted_mod(tmp_path, with_target=False))


def test_post_install_paths_are_case_folded_here_not_by_the_filesystem(tmp_path):
    # NTFS would fold `interface` onto `Interface` for us, which is why verify.preflight
    # gets away with only swapping separators. Doing it ourselves keeps the answer the
    # same wherever this runs.
    (tmp_path / "Interface").mkdir()
    (tmp_path / "Interface" / "MultiActivateMenu.swf").write_text("x")
    parts = instance.mod_relative_parts("interface/MultiActivateMenu.swf")
    got = instance.resolve_insensitive(tmp_path, parts)
    # Not "it found something" — NTFS resolves `interface/` on its own. The components
    # come back with their ON-DISK spelling, which only happens if the fold was ours.
    assert got is not None
    assert got.relative_to(tmp_path).parts == ("Interface", "MultiActivateMenu.swf")
    assert instance.resolve_insensitive(tmp_path, ["interface", "absent.swf"]) is None


def test_post_install_paths_cannot_leave_the_mod_directory():
    # Not a bug that has happened: `delete` takes a path out of a text file and unlinks
    # what it names, and one level up is the rest of the instance.
    for bad in ("../../Fallout4VR.exe", "/etc/passwd", r"C:\Windows\notepad.exe", ""):
        with pytest.raises(ValueError):
            instance.mod_relative_parts(bad)


# --- platform seam -----------------------------------------------------------------

def test_extender_dll_name_is_runtime_specific():
    assert platforms.FO4VR.extender_dll("1.2.72") == "f4sevr_1_2_72.dll"


def test_unverified_platforms_are_declared_as_such():
    # SkyrimVR is a plausible-looking table nobody has tested. Keep that honest.
    assert "fo4vr" in platforms.VERIFIED
    assert "skyrimvr" not in platforms.VERIFIED


# --- install.files matching ----------------------------------------------------------
# Regression: `Data/Scripts/` was declared by BOTH recipes' script-extender entries and
# installed nothing, because str(PurePath) uses backslashes on Windows while the manifest
# uses forward slashes. `install` still reported success, which is why it went unnoticed.

def test_wants_file_matches_a_directory_entry_across_separators():
    from modlist_agent.instance import wants_file
    rel = pathlib.PurePath("Data") / "Scripts" / "Actor.pex"
    assert wants_file(rel, ["Data/Scripts/"])
    assert wants_file(rel, ["Data/Scripts"])
    assert wants_file(rel, [r"data\scripts"])


def test_wants_file_matches_a_plain_file_entry():
    from modlist_agent.instance import wants_file
    assert wants_file(pathlib.PurePath("f4se_loader.exe"), ["f4se_loader.exe"])
    assert not wants_file(pathlib.PurePath("f4se_loader.exe"), ["f4se_1_11_240.dll"])


def test_wants_file_is_component_wise_not_a_raw_prefix():
    from modlist_agent.instance import wants_file
    rel = pathlib.PurePath("Data") / "ScriptsBackup" / "x.pex"
    assert not wants_file(rel, ["Data/Scripts"])


def test_wants_file_without_a_declaration_takes_everything():
    from modlist_agent.instance import wants_file
    assert wants_file(pathlib.PurePath("anything.dll"), None)
    assert wants_file(pathlib.PurePath("anything.dll"), [])


# --- profile ini seeding -------------------------------------------------------------
# Regression: only rule 1 (<game>/<name>) existed, which covers FO4VR — whose game root
# ships Fallout4.ini and Fallout4Prefs.ini — and covers flat Fallout 4 not at all, since
# its root ships only Fallout4_Default.ini. A generated flat profile had NO game inis and
# MO2 silently seeded them on first launch, so the gap looked like a working instance.

def _seed_inis(tmp_path, monkeypatch, platform, game_files, doc_files):
    from modlist_agent import discover, instance as inst_mod
    game = tmp_path / "game"; game.mkdir(parents=True)
    for n, body in game_files.items():
        (game / n).parent.mkdir(parents=True, exist_ok=True)
        (game / n).write_text(body, encoding="utf-8")
    docs = tmp_path / "docs"; docs.mkdir(parents=True)
    for n, body in doc_files.items():
        (docs / n).write_text(body, encoding="utf-8")
    monkeypatch.setattr(discover, "documents_dir", lambda p: docs)
    monkeypatch.setattr(inst_mod.discover, "documents_dir", lambda p: docs)

    i = inst_mod.Instance(tmp_path / "inst", platform, game)
    i.profile_dir.mkdir(parents=True)
    return i


def test_flat_fo4_seeds_its_inis_from_template_and_documents(tmp_path, monkeypatch, man):
    from modlist_agent import platforms
    p = platforms.get("fo4")
    i = _seed_inis(tmp_path, monkeypatch, p,
                   {"Fallout4_Default.ini": "from-template"},   # NO Fallout4.ini here
                   {"Fallout4Prefs.ini": "from-documents"})
    i._write_profile(man)

    assert (i.profile_dir / "Fallout4.ini").read_text() == "from-template"
    assert (i.profile_dir / "Fallout4Prefs.ini").read_text() == "from-documents"
    # the tuning ini is written, never copied — it is the adaptive half
    assert "modlist-agent" in (i.profile_dir / "Fallout4Custom.ini").read_text()


def test_a_game_shipped_ini_still_wins_over_the_template(tmp_path, monkeypatch, man):
    """FO4VR's path must not regress: <game>/<name> is rule 1 and outranks the rest."""
    from modlist_agent import platforms
    p = platforms.get("fo4")
    i = _seed_inis(tmp_path, monkeypatch, p,
                   {"Fallout4.ini": "shipped", "Fallout4_Default.ini": "from-template"},
                   {"Fallout4.ini": "from-documents"})
    i._write_profile(man)
    assert (i.profile_dir / "Fallout4.ini").read_text() == "shipped"


# --- plugin load order vs install order ----------------------------------------------
# Regression: plugins.txt was derived from order.install, which is the OPPOSITE convention.
# order.install is winner-FIRST file priority; plugins.txt is load order, where a LATER
# plugin wins records. The flat FO4 recipe is the first to have a pair where both matter:
# PRP must beat UFO4P on files (so it is listed first) and must load AFTER it (so it is
# written last). `order.plugins` declared that and nothing read it.

PLUGIN_ORDER_MANIFEST = textwrap.dedent("""
    schema: 1
    game:
      id: fo4vr
      nexusDomain: fallout4
      runtime: "1.2.72"
    tools: []
    mods:
      - id: winner
        name: Winner
        why: must win file conflicts, must load last
        tier: fix
        source: { type: nexus, modId: 1, fileId: 2, version: "1" }
        install: { root: data }
        plugins: [zzz.esp]
      - id: loser
        name: Loser
        why: loses files, loads first
        tier: fix
        source: { type: nexus, modId: 3, fileId: 4, version: "1" }
        install: { root: data }
        plugins: [aaa.esp]
    order:
      install: [winner, loser]
      plugins: [Fallout4.esm, aaa.esp, zzz.esp]
""")


def _plugins_txt(tmp_path, monkeypatch, doc):
    from modlist_agent import discover, instance as inst_mod, platforms
    mp = tmp_path / "m.yaml"; mp.write_text(doc, encoding="utf-8")
    game = tmp_path / "game"; game.mkdir()
    (game / "Fallout4.ini").write_text("x", encoding="utf-8")
    (game / "Fallout4Prefs.ini").write_text("x", encoding="utf-8")
    monkeypatch.setattr(inst_mod.discover, "documents_dir", lambda p: game)
    i = inst_mod.Instance(tmp_path / "i", platforms.get("fo4vr"), game)
    i.profile_dir.mkdir(parents=True)
    i._write_profile(mf.load(mp))
    return [l for l in (i.profile_dir / "plugins.txt").read_text().splitlines()
            if l.startswith("*")]


def test_plugins_txt_follows_order_plugins_not_order_install(tmp_path, monkeypatch):
    got = _plugins_txt(tmp_path, monkeypatch, PLUGIN_ORDER_MANIFEST)
    # order.install is [winner(zzz), loser(aaa)]; order.plugins says aaa then zzz.
    assert got == ["*Fallout4.esm", "*Fallout4_VR.esm", "*aaa.esp", "*zzz.esp"]


def test_undeclared_plugins_keep_install_order_at_the_end(tmp_path, monkeypatch):
    """A forgotten order.plugins entry must degrade, never drop the plugin."""
    # NB: PLUGIN_ORDER_MANIFEST is already dedented, so match the dedented indentation.
    doc = PLUGIN_ORDER_MANIFEST.replace(
        "  plugins: [Fallout4.esm, aaa.esp, zzz.esp]",
        "  plugins: [Fallout4.esm]")
    assert "aaa.esp, zzz.esp" not in doc
    got = _plugins_txt(tmp_path, monkeypatch, doc)
    assert got == ["*Fallout4.esm", "*Fallout4_VR.esm", "*zzz.esp", "*aaa.esp"]


def test_the_tuning_ini_is_never_imported_from_documents(tmp_path, monkeypatch, man):
    """It carries bInvalidateOlderFiles; both games have a stray one in Documents.

    Adding the Documents fallback without guarding this copied 41 bytes of window
    position over the stub on every fresh profile, silently dropping the settings that
    make loose mod files load.
    """
    from modlist_agent import platforms, instance as inst_mod
    for pid in ("fo4", "fo4vr"):
        p = platforms.get(pid)
        i = _seed_inis(tmp_path / pid, monkeypatch, p,
                       {"Fallout4_Default.ini": "template"},
                       {p.tuning_ini: "[Display]\niLocation X=0\n"})
        i._write_profile(man)
        body = (i.profile_dir / p.tuning_ini).read_text()
        assert "bInvalidateOlderFiles" in body, pid
        assert "iLocation" not in body, pid
