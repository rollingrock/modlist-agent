# core — the game-neutral engine

Everything a recipe needs that is not the recipe. `core/` knows about MO2, script
extenders, usvfs and verification; it knows nothing about which mods are good.

```
core/
  mla.py                    entry point
  modlist_agent/
    manifest.py             load + validate a recipe; owns the ordering rule
    platforms.py            THE per-game seam — the only game-aware module
    discover.py             find Steam, the game, the runtime version
    instance.py             generate a portable MO2 instance
    verify.py               launch and prove it worked
    cli.py                  doctor / build / verify
  tools/steamvr-null.ps1    headless VR toggle
  tests/test-conflict-order.ps1
```

## Usage

```powershell
python core\mla.py doctor recipes\fo4vr\manifest.yaml
python core\mla.py build  recipes\fo4vr\manifest.yaml --instance C:\Modding\mo2_fo4vr_gen
python core\mla.py verify recipes\fo4vr\manifest.yaml --instance C:\Modding\mo2_fo4vr_gen
```

`doctor` is read-only and is meant to be the thing that fails. It answers "would this
recipe work here?" — runtime match, game location, unresolved pins, manifest consistency —
before anything is written or launched.

Exit codes are meaningful: **0 pass, 1 fail, 2 inconclusive.** `verify` never collapses
inconclusive into either of the other two; see below.

### Useful flags

- `--local id=PATH` — install a manifest mod from a directory instead of a download.
  Not a testing shortcut: mods built from source have no archive to pin, and this is how
  they get installed. FRIK lives next door; the native scope fix will too.
- `--harness DIR` — install a verification plugin at top priority. The harness is
  deliberately **not** a manifest entry: a recipe that ships its own verifier is marking
  its own homework.
- `--partial` — verify a deliberately incomplete build. Prints exactly what a pass does
  and does not prove.

## Design rules

**One seam, and keep it thin.** `platforms.py` is the only game-aware module. Adding a
game should mean filling in a table; if it ever needs more than that, the abstraction is
wrong and should be fixed rather than special-cased. `devbench` next door began
Skyrim-only and paid an expensive restructure when Fallout arrived — the seam is cheap now.

`SKYRIMVR` is present and **declared unverified**. `doctor` says so out loud rather than
letting a plausible-looking table imply it has been tested.

**The ordering rule lives in exactly one function.** `Manifest.modlist_lines` is the only
place that decides how `order.install` becomes `modlist.txt`, and
`tests/test-conflict-order.ps1` is the only thing entitled to an opinion about whether it
is right. That pairing exists because the rule was *wrong in the spec* and no amount of
reading caught it — both possibilities produce a plausible instance.

**Three outcomes, never two.** A missing dependency once produced a modal dialog: no
crash, no error code, an unbounded hang. So `verify` distinguishes *inconclusive* from
*fail*, checks declared dependency files **before** launching, and when it times out it
points at the discriminating signal instead of inventing a cause.

**Validation is about self-consistency, not correctness.** `doctor` can tell you a mod is
missing from `order.install`, or that a `root: game` entry has no uninstall note. It
cannot tell you a pin points at the right file. Do not let a green `doctor` read as more
than it is.

## What this does not do yet

- **Download and install Nexus mods.** `build` generates the instance and installs local
  sources; it does not fetch. Twelve pins are unresolved and the download path
  (`nxm://` and the premium API) is designed but unwritten. This is the biggest gap.
- **Archive installs.** `install_local` takes a directory. Extraction with `strip`/FOMOD
  handling exists in `instance.extract` but is unused by the mod path.
- **INI tuning.** The adaptive half writes a placeholder `Fallout4Custom.ini`. Nothing
  reads the GPU yet.
- **Idempotency.** `build` overwrites profile files and leaves `mods/` alone. It has never
  been run against a half-set-up machine, which is the case real users have.
