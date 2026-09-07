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

    # Everything the operator typed is checked HERE, before ensure_mo2 pulls ~150 MB into
    # the instance and before build() writes modlist.txt. 2026-08-29: a mistyped --local id
    # was caught after ensure_mo2 had already run, leaving a half-built instance to delete
    # by hand; the --local source check ran later still, after build() had written a
    # modlist.txt naming a mod that was never installed; and --harness was not checked at
    # all — a wrong path surfaced as a raw copytree FileNotFoundError, again with the
    # harness already listed in modlist.txt.
    #
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
        src = pathlib.Path(v)
        if not src.exists():
            print(f"{BAD} --local {k}: {src} does not exist"); return 1
        if not src.is_dir():
            # install_local is copytree: a file here fails the same way --harness did.
            print(f"{BAD} --local {k}: {src} is not a directory"); return 1
        locals_[k] = src

    # The harness is the measuring instrument, deliberately NOT a manifest entry:
    # a recipe that ships its own verifier is marking its own homework.
    harness = pathlib.Path(args.harness) if args.harness else None
    harness_name = None
    if harness:
        if not harness.exists():
            print(f"{BAD} --harness {harness} does not exist"); return 1
        if not harness.is_dir():
            print(f"{BAD} --harness {harness} is not a directory"); return 1
        harness_name = harness.name

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

    for line in inst.build(m, harness=harness_name):
        print(f"{OK} {line}")
    if harness:
        print(f"{OK} " + inst.install_dir(harness_name, harness,
                                          note="verification harness, not part of the recipe"))
    for k, src in locals_.items():
        print(f"{OK} {inst.install_local(by_id[k], src)} (from {src})")
    print(f"{OK} modlist.txt written winner-first, no reversal "
          f"({len(m.order.get('install', []))} entries)")
    print(f"{OK} profile {inst.profile} with local inis")
    print("\nmods are NOT installed by this command — pins are unresolved.")
    print("Existing mods/ content is left untouched.")
    return 0


def cmd_check(args) -> int:
    """Drift check. Designed for CI: needs no game, no MO2, no headset."""
    from . import check as ck, nexus

    m = mf.load(args.manifest, strict=False)
    problems = mf.validate(m)
    dead = warn = unreachable = 0

    print("-- manifest --")
    for p in problems:
        print(f"{BAD} {p}")
    dead += len(problems)
    if not problems:
        print(f"{OK} internally consistent")

    print("\n-- off-site sources --")
    for f in ck.check_offsite(m):
        tag = {"ok": OK, "dead": BAD, "unreachable": WARN}[f.level]
        print(f"{tag} {f.entry_id}: {f.message}")
        dead += f.level == "dead"
        unreachable += f.level == "unreachable"

    if not args.no_nexus:
        print("\n-- nexus pins --")
        try:
            client = nexus.Client(args.key)
            for f in ck.check_nexus(m, client):
                tag = {"ok": OK, "warn": WARN, "dead": BAD}[f.level]
                print(f"{tag} {f.entry_id}: {f.message}")
                dead += f.level == "dead"
                warn += f.level == "warn"
            print(f"\nrate limit remaining {client.rate.get('x-rl-hourly-remaining', '?')}")
        except nexus.NexusError as e:
            print(f"{WARN} skipped: {e}")

    print(f"\n{dead} dead, {unreachable} unreachable, {warn} newer-available")
    if warn and args.strict:
        # Opt-in: a newer file is news, not breakage. Only fail on it when asked.
        return 1
    if dead:
        return 1
    # 2 is INCONCLUSIVE, the same meaning it carries in `verify`: no answer, cause
    # unknown. A host that did not respond has told us nothing about the pin, and
    # calling that a dead link is the confidently-wrong failure this project keeps
    # legislating against. See check._head for the run that forced the distinction.
    return 2 if unreachable else 0


def cmd_install(args) -> int:
    """Install downloaded archives into the instance. Hash-checked before anything moves."""
    from .instance import sha256

    m = mf.load(args.manifest, strict=False)
    plat = platforms.get(m.game["id"])
    g = discover.find_game(plat)
    if not g:
        print(f"{BAD} game not found"); return 1
    inst = instance.Instance(pathlib.Path(args.instance), plat, g.path)
    if not inst.exe.exists():
        print(f"{BAD} no instance at {inst.path} — run `build` first"); return 1

    downloads = inst.path / "downloads"
    staging = inst.path / "_staging"
    only = set(args.only.split(",")) if args.only else None
    n = skipped = 0

    for e in m.mods + m.tools:
        if e.tier == "candidate" or e.root == "instance":
            continue
        if only and e.id not in only:
            continue
        name = e.file.get("name")
        if not name:
            skipped += 1
            print(f"{WARN} {e.id}: no pinned filename — nothing to install"); continue
        archive = downloads / name
        if not archive.exists():
            skipped += 1
            print(f"{WARN} {e.id}: {name} not downloaded"); continue
        want = e.file.get("sha256")
        if want:
            got = sha256(archive)
            if got != want:
                # Never install something that failed its pin, even if it looks fine.
                print(f"{BAD} {e.id}: HASH MISMATCH, refusing to install\n"
                      f"       expected {want}\n       got      {got}")
                return 1
        try:
            print(f"{OK} {inst.install_archive(e, archive, staging)}")
            n += 1
        except Exception as exc:
            print(f"{BAD} {e.id}: {exc}"); return 1

    shutil_rmtree(staging)
    print(f"\n{n} installed, {skipped} skipped")
    return 0


def shutil_rmtree(p: pathlib.Path) -> None:
    import shutil
    shutil.rmtree(p, ignore_errors=True)


def cmd_download(args) -> int:
    from . import download as dl, nexus

    m = mf.load(args.manifest, strict=False)
    plat = platforms.get(m.game["id"])
    entries = dl.targets(m)

    if args.print_links:
        # The free path. We print; the human clicks. We never click for them.
        # Needs no destination — it downloads nothing.
        print("Click 'Mod Manager Download' on each page. Each click hands an nxm:// link\n"
              "to the registered handler; feed those back with --nxm or --nxm-file.\n")
        for eid, url in dl.links_for(m, entries):
            print(f"  {eid}\n    {url}")
        return 0

    # Only the fetch path needs a destination. Computing it up front crashed with a raw
    # TypeError (Path(None)) when neither flag was given; say what is missing instead.
    if args.instance:
        dest = pathlib.Path(args.instance) / "downloads"
    elif args.dest:
        dest = pathlib.Path(args.dest)
    else:
        print(f"{BAD} download needs a destination: pass --instance <dir> "
              "(fetches into <dir>/downloads) or --dest <dir>")
        return 1

    try:
        client = nexus.Client(args.key)
        who = client.validate()
    except nexus.NexusError as e:
        print(f"{BAD} {e}")
        return 1
    premium = bool(who.get("is_premium"))
    print(f"account {who.get('name')} — {'PREMIUM' if premium else 'free'}")
    if not premium:
        print("       free account: only files with an nxm:// link can be fetched.\n"
              "       Run with --print-links, click each, then pass them with --nxm-file.")

    nxm = []
    for u in args.nxm or []:
        nxm.append(nexus.NxmLink.parse(u))
    if args.nxm_file:
        for line in pathlib.Path(args.nxm_file).read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("nxm://"):
                nxm.append(nexus.NxmLink.parse(line.strip()))

    only = set(args.only.split(",")) if args.only else None
    results = dl.fetch_all(m, dest, client=client, nxm_links=nxm, only=only)

    ok = bad = pending = 0
    for r in results:
        if r.matched is False:
            bad += 1
            print(f"{BAD} {r.entry_id}: HASH MISMATCH ({r.note})\n       got {r.sha256}")
        elif r.note.startswith(("ERROR", "NEEDS CLICK")):
            pending += 1
            print(f"{WARN} {r.entry_id}: {r.note.splitlines()[0]}")
        elif r.matched is True:
            ok += 1
            print(f"{OK} {r.entry_id}: verified against pin{' (cached)' if r.note == 'cached' else ''}")
        else:
            ok += 1
            print(f"{OK} {r.entry_id}: {r.sha256[:16]}… ({r.note or 'downloaded'})")
    print(f"\n{ok} ok, {bad} mismatched, {pending} pending; "
          f"rate limit remaining {client.rate.get('x-rl-hourly-remaining', '?')}")

    if args.write_hashes:
        n = dl.record_hashes(m.path, results)
        print(f"{OK} recorded {n} new hash(es) into {m.path}")
        print("      Review the diff before committing — these are proposals, and a pin "
              "is a claim about what was tested.")
    # A mismatch is the loud case: the world moved and nothing should proceed on it.
    return 1 if bad else 0


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

    dw = sub.add_parser("download", help="fetch pinned files and verify them")
    dw.add_argument("manifest")
    dw.add_argument("--instance", help="download into <instance>/downloads")
    dw.add_argument("--dest", help="download here instead")
    dw.add_argument("--key", help="Nexus API key (default: NEXUS_API_KEY or ~/.nexus-api-key)")
    dw.add_argument("--print-links", action="store_true",
                    help="free path: print the file pages for the user to click")
    dw.add_argument("--nxm", action="append", help="an nxm:// link (repeatable)")
    dw.add_argument("--nxm-file", help="file containing nxm:// links, one per line")
    dw.add_argument("--only", help="comma-separated entry ids")
    dw.add_argument("--write-hashes", action="store_true",
                    help="record newly computed sha256 into empty pins")
    dw.set_defaults(fn=cmd_download)

    c = sub.add_parser("check", help="drift: are the pins still real? (CI-friendly)")
    c.add_argument("manifest")
    c.add_argument("--key", help="Nexus API key")
    c.add_argument("--no-nexus", action="store_true", help="skip Nexus (no key available)")
    c.add_argument("--strict", action="store_true", help="also fail when a newer file exists")
    c.set_defaults(fn=cmd_check)

    i = sub.add_parser("install", help="install downloaded archives into the instance")
    i.add_argument("manifest"); i.add_argument("--instance", required=True)
    i.add_argument("--only", help="comma-separated entry ids")
    i.set_defaults(fn=cmd_install)

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
