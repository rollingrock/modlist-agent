"""modlist-agent CLI.

    python core/mla.py doctor  recipes/fo4vr/manifest.yaml
    python core/mla.py build   recipes/fo4vr/manifest.yaml --instance C:\\Modding\\mo2_fo4vr
    python core/mla.py verify  recipes/fo4vr/manifest.yaml --instance C:\\Modding\\mo2_fo4vr

`doctor` is read-only and answers "would this work here?". Run it first; it is designed to
be the thing that fails, loudly and early, instead of a launch that hangs.
"""
from __future__ import annotations

import argparse
import pathlib
import sys

from . import discover, instance, manifest as mf, platforms, verify

OK, WARN, BAD = "[ ok ]", "[warn]", "[FAIL]"


def cmd_doctor(args) -> int:
    m = mf.load(args.manifest, strict=False)
    problems = mf.validate(m)
    plat = platforms.get(m.game["id"])
    bad = False

    print(f"recipe   {m.path}")
    print(f"game     {plat.mo2_game_name} ({plat.id})")
    if plat.id not in platforms.VERIFIED:
        print(f"{WARN} platform {plat.id!r} is DECLARED BUT UNVERIFIED — no instance has "
              "ever been built for it")

    print("\n-- manifest --")
    if problems:
        bad = True
        for p in problems:
            print(f"{BAD} {p}")
    else:
        print(f"{OK} internally consistent "
              f"({len(m.mods)} mods, {len(m.order.get('install', []))} ordered)")
    un = m.unresolved()
    if un:
        print(f"{WARN} {len(un)} unresolved pin(s): {', '.join(e.id for e in un)}")
        print("       unresolved is not optional — resolve before shipping this recipe")

    print("\n-- machine --")
    if sys.platform != "win32":
        print(f"{BAD} not Windows")
        return 1
    g = discover.find_game(plat)
    if not g:
        print(f"{BAD} {plat.steam_dir_name} not found in any Steam library")
        return 1
    print(f"{OK} game at {g.path}")
    want = m.game.get("runtime")
    if g.runtime == want:
        print(f"{OK} runtime {g.runtime} matches the manifest pin")
    else:
        bad = True
        print(f"{BAD} runtime {g.runtime} but manifest pins {want} — script-extender "
              "plugins are built per-runtime; this is the most common cause of "
              "'it launches and no mods load'")
    if g.in_program_files:
        print(f"{WARN} game is under Program Files; MO2 warns about this. Not fatal, but "
              "it is a known source of permission oddities")

    ext = g.path / plat.extender_loader
    print(f"{OK if ext.exists() else WARN} script extender "
          f"{'present' if ext.exists() else 'NOT installed'} ({plat.extender_loader})")

    if args.instance:
        inst = pathlib.Path(args.instance)
        print(f"{OK if (inst / 'ModOrganizer.exe').exists() else WARN} instance "
              f"{'exists' if (inst / 'ModOrganizer.exe').exists() else 'not built'} at {inst}")
    return 1 if bad else 0


def cmd_build(args) -> int:
    m = mf.load(args.manifest)
    plat = platforms.get(m.game["id"])
    g = discover.find_game(plat)
    if not g:
        print(f"{BAD} game not found"); return 1
    if g.runtime != m.game.get("runtime"):
        print(f"{BAD} runtime {g.runtime} != pinned {m.game.get('runtime')}"); return 1

    inst = instance.Instance(pathlib.Path(args.instance), plat, g.path)
    cache = pathlib.Path(args.cache) if args.cache else inst.path.parent / "_cache"

    mo2 = next((t for t in m.tools if t.id == "mo2"), None)
    if mo2 and not inst.exe.exists():
        print(f"fetching {mo2.name} {mo2.raw.get('version')} ...")
        inst.ensure_mo2(mo2, cache)

    # --local lets an entry come from a directory instead of a download. Not a testing
    # shortcut: mods built from source (FRIK lives next door; the native scope fix will
    # too) have no Nexus archive to pin, and this is how they get installed.
    by_id = {e.id: e for e in m.mods}
    locals_ = {}
    for spec in args.local or []:
        if "=" not in spec:
            print(f"{BAD} --local expects id=PATH, got {spec!r}"); return 1
        k, v = spec.split("=", 1)
        if k not in by_id:
            print(f"{BAD} --local {k}: no such mod in the manifest"); return 1
        locals_[k] = pathlib.Path(v)

    harness_name = None
    if args.harness:
        # The harness is the measuring instrument, deliberately NOT a manifest entry:
        # a recipe that ships its own verifier is marking its own homework.
        harness_name = pathlib.Path(args.harness).name
    for line in inst.build(m, harness=harness_name):
        print(f"{OK} {line}")
    if args.harness:
        print(f"{OK} " + inst.install_dir(harness_name, pathlib.Path(args.harness),
                                          note="verification harness, not part of the recipe"))
    for k, src in locals_.items():
        if not src.exists():
            print(f"{BAD} --local {k}: {src} does not exist"); return 1
        print(f"{OK} {inst.install_local(by_id[k], src)} (from {src})")
    print(f"{OK} modlist.txt written winner-first, no reversal "
          f"({len(m.order.get('install', []))} entries)")
    print(f"{OK} profile {inst.profile} with local inis")
    print("\nmods are NOT installed by this command — pins are unresolved.")
    print("Existing mods/ content is left untouched.")
    return 0


def cmd_verify(args) -> int:
    m = mf.load(args.manifest, strict=False)
    plat = platforms.get(m.game["id"])
    g = discover.find_game(plat)
    if not g:
        print(f"{BAD} game not found"); return 1
    inst = instance.Instance(pathlib.Path(args.instance), plat, g.path)
    if not inst.exe.exists():
        print(f"{BAD} no instance at {inst.path} — run `build` first"); return 1

    r = verify.run(m, inst, timeout=args.timeout, launch_title=args.title,
                   partial=args.partial)
    tag = {verify.Outcome.PASS: OK, verify.Outcome.FAIL: BAD,
           verify.Outcome.INCONCLUSIVE: WARN}[r.outcome]
    print(f"{tag} {r.outcome.value.upper()}: {r.detail}")
    if args.evidence and r.evidence:
        verify.save_evidence(r, pathlib.Path(args.evidence))
        print(f"{OK} evidence -> {args.evidence}")
    return r.exit_code


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mla", description="modlist-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="read-only: would this recipe work here?")
    d.add_argument("manifest"); d.add_argument("--instance")
    d.set_defaults(fn=cmd_doctor)

    b = sub.add_parser("build", help="generate the portable MO2 instance")
    b.add_argument("manifest"); b.add_argument("--instance", required=True)
    b.add_argument("--cache")
    b.add_argument("--harness", help="directory to install as the verification harness")
    b.add_argument("--local", action="append",
                   help="install a manifest mod from a directory: id=PATH (repeatable)")
    b.set_defaults(fn=cmd_build)

    v = sub.add_parser("verify", help="launch and prove it worked")
    v.add_argument("manifest"); v.add_argument("--instance", required=True)
    v.add_argument("--timeout", type=int, default=180)
    v.add_argument("--title", help="custom executable to launch")
    v.add_argument("--evidence", help="write the raw capture here")
    v.add_argument("--partial", action="store_true",
                   help="verify deliberately incomplete builds (proves the instance, not the recipe)")
    v.set_defaults(fn=cmd_verify)

    args = ap.parse_args(argv)
    return args.fn(args)
