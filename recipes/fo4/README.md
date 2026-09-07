# Fallout 4 (flat) — minimal essential base

The sibling of [`../fo4vr`](../fo4vr), for the non-VR game. Same rule, same schema, same
machinery — but **not** the same list, and the differences are the interesting part.

Pinned 2026-09-07 against runtime **1.11.240**. See the top of
[`manifest.yaml`](manifest.yaml) for exactly how far this has and has not been taken.

---

## What runtime this targets, and why that decides everything

`Fallout4.exe` on this machine is **1.11.240.0**, dated 2026-08-19. That is not
1.10.163 (the long-lived pre-next-gen runtime), and not 1.10.984 (the April 2024
"next-gen" update). It is the **Anniversary Edition** line, and the mod ecosystem treats
OG / NG / AE as three distinct compatibility targets.

**This recipe stays on the current runtime rather than downgrading.** Three independent
signals, all read on the day of pinning:

- F4SE ships **0.7.9 for 1.11.240** — silverlock's own table maps `0.6.23 -> 1.10.163`,
  `0.7.2 -> 1.10.984`, `0.7.9 -> 1.11.240`.
- Address Library, MCM and UFO4P all publish files **versioned `1.11.240`**, uploaded
  within days of the game update. The ecosystem tracks this runtime actively.
- PRP's requirements say the quiet part out loud: *"AE (Current) - Supported as of 81 or
  newer"*, and NG-via-Steam-downgrade is struck through as *"No longer supported, update
  to AE if still on it."*

The cost of that choice is recorded honestly below.

## How this differs from the VR recipe

These are not stylistic differences. Each one would have been a broken install if the VR
entry had simply been copied across.

| | `../fo4vr` | this recipe |
|---|---|---|
| Script extender source | silverlock, plain HTTP | **Nexus mod 42147** |
| Extender files in game dir | 3 (incl. `f4sevr_steam_loader.dll`) | **2** — the steam loader is gone |
| `extender_args` | `-forcesteamloader` | **empty** |
| Address library file | `version-1-2-72-0.csv` | **`version-1-11-240-0.bin`** |
| Crash/stability plugin | Buffout 4 NG and VR | **Addictol** |
| xSE PluginPreloader | installed | **excluded** |
| `dlcRequired` | `false` | **`true`** |
| Profile ini seeding | copied from the game root | **template + Documents fallback** |

**The extender is on Nexus.** silverlock publishes 0.6.23 as a direct `.7z`, but for
1.10.984 and 1.11.240 it links to Nexus instead. So unlike the VR recipe — where the whole
vertical slice could be proven before the download story existed — **a flat FO4 instance
cannot be built without a Nexus API key.** There is no key-free bootstrap here.

**No steam loader, and no loader argument.** F4SE 0.7.9's archive contains
`f4se_1_11_240.dll`, `f4se_loader.exe` and `Data/`, and `f4se_whatsnew.txt` says why:
*"f4se_steam_loader.dll no longer needed."* The VR platform passes `-forcesteamloader`
because on a Steamless-unpacked exe xSE injects before usvfs arms and loads **zero**
plugins while booting to a healthy-looking main menu.

That hazard cannot recur here, and the flag is now dead. 0.7.0 removed the entire
steam-loader injection path, and what survives is a compatibility stub: `Options.cpp`
parses `-forcesteamloader` and drops it, with usage text reading *"does nothing, ignored
for backwards compatibility."* Passing it would be harmless **and meaningless**, which is
the worst kind of configuration to inherit — it reads as load-bearing.

Nor is this install the refused case. F4SE maps a `.bind` section to `kProcType_Steam`,
which is **supported**; the *"Packed versions of Fallout are not supported"* refusal is
`kProcType_Packed`, i.e. UPX, detected by a `UPX0` section. This machine's `Fallout4.exe`
has `.bind` and no `UPX0`, and `f4se_loader.exe -crconly` against it logs `steam exe` and
exits 0.

**Do not repack or re-sign the extender.** Since 0.7.3 both binaries are Authenticode
signed, and the loader checks the DLL's certificate serial against its own before
injecting — so loader and DLL must come from the same archive, and any step that rewrites
the bytes turns a working install into `dll untrusted`.

**`.bin`, not `.csv`.** CommonLibF4 builds the address-library path itself:
`Data/F4SE/Plugins/version-{version}.{csv if VR else bin}`. Get that wrong and the failure
is a modal dialog and an apparent hang, not an error — the single nastiest failure this
project has met.

**Buffout is not available.** Mod 64880 (*Buffout 4 NG and VR*), which the VR recipe pins,
states plainly that it *"does not support Anniversary Edition"* and names Addictol as the
alternative. The dedicated port — *Buffout 4 AE / MiniBuff*, mod 99911 — opens with
*"Buffout 4 AE is no longer in development."* Addictol it is; see the trade-off below.

## What is in

| Mod | Tier | Why |
|---|---|---|
| Address Library | foundation | Every F4SE plugin resolves engine addresses through it |
| Unofficial Fallout 4 Patch | fix | The community bug-fix baseline |
| Addictol | fix | Engine crash/leak patches vanilla never made |
| Addictol Crash Logger | fix | Without it a crash is a closed window |
| High FPS Physics Fix | fix | Vanilla ties physics and UI to frame rate above 60 fps |
| Mod Configuration Menu | fix | Settings UI for F4SE mods, instead of hand-edited ini files |
| Previsibines Repair Pack | performance | Vanilla and UFO4P both break precombines; Boston pays for it |

Seven mods and two tools — and **PRP is 2.26 GB of those**, thirty times everything else
combined. It was admitted deliberately, with that cost understood: the defect it fixes is
engine data rather than taste, and it is actively maintained against this exact runtime.

MCM is in on a weaker argument, and worth naming as such: **nothing else in this list has
an MCM page.** It is a framework ahead of its dependents. The case for it is that Addictol
hides eight absorbed fixes in a TOML nobody has audited, and a settings UI is the cheapest
way to make that state visible.

**UFO4P is the entry the VR recipe cannot have.** There it is excluded because the base
must install on a DLC-free FO4VR. Here `dlcRequired: true` is declared: UFO4P 2.2.2a
requires *"Fallout 4 patch 1.11.221 or greater"* and *"ALL 15 Official DLCs"* — the six
DLC `.esm` plus the nine `ccXXX .esl` that AE ships. This machine has exactly those
fifteen. **A bare Fallout 4 cannot run this recipe as written**, and that is a deliberate
scope choice rather than an oversight.

**Addictol is a bundle, which cuts against this recipe's taste.** It absorbs Buffout,
X-Cell, Mentats, Baka MaxPapyrusOps, Escape Freeze, Interior NavCut Fix, Long Save Bug Fix
and Disk Cache Enabler. The case for it is that eight entries collapse into one, they
cannot disagree about who patches what, and it is the only one of them its own author says
is AE-ready. The case against is that one entry now hides eight decisions in a TOML file
**nobody here has read against the game**. That audit is not done.

## What is out, and why

| Mod | Why excluded |
|---|---|
| xSE PluginPreloader F4 (33946) | Its own page: *"You don't need this unless a mod specifically says you require this"*, and since NG, *"F4SE plugins can opt in to use the preload method built in the new F4SE releases."* Nothing here asks for it. Excluding it also removes a second mutation of the user's game directory. |
| Buffout 4 NG and VR (64880) | Author states no AE support |
| Buffout 4 AE / MiniBuff (99911) | Discontinued by its author |
| Buffout 4 (47359) | Original; last updated 2023, pre-next-gen |
| Baka ScrapHeap, Baka MaxPapyrusOps, Escape Freeze, Mentats, X-Cell, Long Save Bug Fix, Interior NavCut Fix | All absorbed by Addictol, whose author says not to run them alongside it |

Two entries are recorded as **candidates** — pinned and argued, not installed:

- **HUDFramework** — a framework with no consumer here, and the only pin in the recipe
  never republished for AE: v1.0f predates the next-gen update entirely.
- **No Read-only Plugins Txt Overwrite** — really a test to run rather than a mod to add.
  Its author documents that AE (v1.11.137+) *"automatically removes the existing and
  creates a new Plugins.txt with the resolved mod list regardless whether Plugins.txt was
  manually set to Read-only"*, where OG and NG respected the flag. This recipe's whole
  premise is that the generated `plugins.txt` **is** the load order, so if that is true
  here, `order.plugins` is advisory and something has to change. The measurement is cheap:
  record the file, launch, exit, diff.

## What is not established

Stated plainly, because a working `install` invites more confidence than it has earned:

- **Nothing has been launched.** The instance is generated and the mods are installed and
  hash-verified. The game has never been started through F4SE with this instance, so
  "these plugins load together" is *unproven*.
- **Verification may not be possible the way it is for VR.** `../fo4vr` is verified by
  `devbench` answering on a local port. devbench builds against CommonLibF4, whose
  `F4SE/Version.h` stops at `RUNTIME_1_10_984` — it has no constant for any 1.11.x. The
  address-library mechanism itself is fine (`IDDB` only hash-gates one known-bad 1.10.980
  bin, and the AE database exists). The problem is upstream of that: F4SE's own 0.7.5
  changelog says the **1.11+ series needs a new Address Library and that plugins must be
  recompiled against it**, so a DLL carrying pre-1.11 IDs is not merely untested here —
  it is documented as needing a rebuild. Until devbench is built against an AE-capable
  CommonLibF4, flat FO4 has no instrument and `f4se.log` is the only evidence available.
- **No two of these mods are known to conflict at the file level**, so `order.install` is
  reasoned rather than observed — the same caveat the VR recipe carries. One pair now
  genuinely overlaps in intent, though: PRP rebuilds previsibines for cells UFO4P also
  edits, and PRP's previs is built *against* that patch, so PRP is placed above it. That
  is the first ordering decision in either recipe where the machinery could actually
  matter, and it is still reasoning rather than a measurement.
- **Whether the engine respects the generated `plugins.txt` at all** on AE — see the
  second candidate above. If it rewrites it, `order.plugins` is advisory.
- **Addictol's TOML has not been audited**, so which of its eight absorbed fixes are
  actually on is unknown.
- **Idempotency** — [`../../docs/OPEN_QUESTIONS.md`](../../docs/OPEN_QUESTIONS.md) #7 —
  remains untested here as everywhere.

## Sources

- Machine, 2026-09-07: game at `C:\Program Files (x86)\Steam\steamapps\common\Fallout 4`
  (1.11.240.0), instance at `C:\Modding\mo2_fo4`, MO2 2.5.2. Naming the machine matters —
  see the DLC correction in [`../fo4vr/README.md`](../fo4vr/README.md).
- [F4SE](https://f4se.silverlock.org/) version table, and F4SE 0.7.9's own
  `f4se_readme.txt` / `f4se_whatsnew.txt`
- MO2 2.5.2 `game_fallout4.dll`, for `gameName` and the INI basenames
- `%LOCALAPPDATA%\Fallout4\Plugins.txt`, `DLCList.txt` and `UserDownloadedContent.txt`,
  as written by the game itself, for the plugins header and implicit DLC loading
- Nexus mod pages 42147, 47327, 4598, 84214, 44798, 46403, 21497, 20309, 64880, 99911,
  33946 — read via the API on the day of pinning
