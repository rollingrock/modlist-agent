# Verification — the slice, and how it was proven

Answers open question **#2**. Written 2026-08-16, immediately after the first end-to-end run.

**The first milestone passed.** A portable MO2 instance was built from nothing, Fallout 4 VR
launched through it, and a plugin that exists *only* inside MO2's virtual filesystem answered
an HTTP request from a running game.

---

## The result

```
POST http://127.0.0.1:8931/api/tool/inspect  {"kind":"state"}

{
  "exe":          "Fallout4VR.exe",
  "extender":     "F4SE",
  "game":         "fallout4",
  "vr":           true,
  "playerLoaded": true,
  "frame":        4156,
  "plugin":       "devbench",
  "version":      "1.14.0",
  "port":         8931,
  "pid":          19004
}
```

Raw capture: [`evidence/first-run-2026-08-16.json`](evidence/first-run-2026-08-16.json).

**This is also devbench's first live response, ever.** Its docs said *"builds, not yet run
in-game… treat the endpoint list as the intended contract, not a tested one."* It is tested
now: `ping`, `inspect state`, `inspect health`, `inspect scene` and `log list` all answered.
The two unproven things the seed plan had to bootstrap against each other both work.

## Why this is evidence and not narration

Each field rules something out, which is the whole point of picking a signal the agent does
not produce:

| Field | What it makes impossible to fake |
|---|---|
| the response existing at all | The game process is running and a socket is bound |
| `exe: Fallout4VR.exe`, `vr: true` | It is *VR*, not flat Fallout 4 |
| `extender: F4SE` | F4SEVR loaded and ran the plugin |
| `plugin: devbench`, `version` | Our DLL initialised — not just that a file exists |
| `frame: 4156`, rising between calls | The engine is *rendering*, not stuck at init |
| `playerLoaded: true` | It got past the main menu into a loaded world |
| `scene: {position, gameHour, daysPassed}` | Real game state read on the main thread |

An agent claiming "I installed it and it works" produces none of this. That asymmetry is the
design.

**Strongest single fact:** `devbench.dll` was never copied into the game folder. It exists
only at `mods/devbench/F4SE/Plugins/devbench.dll`, and F4SEVR loaded it from
`...\Fallout 4 VR\Data\F4SE\Plugins\devbench.dll`. So the response simultaneously proves the
game ran *and* that MO2's virtualisation worked. One signal, two claims.

The reverse direction holds too: devbench's `config.json` and `runtime.json` were written to
`overwrite/F4SE/Plugins/devbench/`, and the game's real `Data/` is still vanilla.

---

## Headless verification — the thing that makes this automatable

FO4VR needs a headset. The Quest 3 here connects over Virtual Desktop, so an unattended run
would need a human wearing it — which would have killed the idea of verifying in CI.

**SteamVR's null driver removes that requirement.** It presents a synthetic HMD, so the game
initialises, loads F4SEVR, loads plugins, and renders frames with no hardware attached.

```powershell
core\tools\steamvr-null.ps1 -Status     # what is it now
core\tools\steamvr-null.ps1 -Enable     # headless
core\tools\steamvr-null.ps1 -Disable    # give the Quest back
```

The game is **not playable** this way — it renders to nowhere. That does not matter here,
because the acceptance signal is a plugin answering over HTTP, not pixels. Verification is
therefore unattended, repeatable, and CI-able.

Notes from making it work:

- Settings go in **`Steam\config\steamvr.vrsettings`** (user config), not the SteamVR
  install's `resources\settings\default.vrsettings`. The install's copy is overwritten on
  every SteamVR update; the user's is not. `driver_null` can be overridden there too, so the
  whole toggle lives in one file.
- Needs `requireHmd=false`, `forcedDriver=null`, `activateMultipleDrivers=true`, and
  `driver_null.enable=true`.
- **`forcedDriver=null` is global and forces the null HMD even when a real headset is
  connected.** Always `-Disable` afterwards. The script refuses to run while SteamVR is up
  (the change would be both ignored and overwritten on exit) and backs up the original config
  once.
- **First run triggers SteamVR room setup**, which sends the game a Quit and then kills it
  (`Kill process …: Fallout4VR because it didn't quit in time`). Room setup writes a
  chaperone for the null universe and subsequent runs are clean. Expect one wasted launch on
  a fresh machine, and do not diagnose it as a mod problem.

## The failure that taught the most

The first attempt with devbench died with F4SEVR's log ending mid-sentence:

```
checking plugin ...\Data\F4SE\Plugins\devbench.dll
```

No crash in the event log. No further output. From the automation's side: a silent hang.

The actual cause was a **modal dialog** —
`REL/IDDB.cpp(82): failed to open: Data/F4SE/Plugins/version-1-2-72-0.csv` — devbench's
CommonLibF4 needs the **VR Address Library**, which was not installed. The process sat on a
message box nobody could see.

Three consequences for the design:

1. **A missing dependency can present as a hang, not an error.** The recipe must check
   declared dependency files exist *before* launching, impose a launch timeout, and report
   "no response, no crash" as **inconclusive** rather than inventing a cause.
2. **`vr-address-library` is not merely a manifest entry — it is load-bearing for anything
   built on CommonLibF4.** Its `why` was already right; its blast radius was understated.
3. This is exactly the failure class the project exists to catch. An agent trusting its own
   narration would have said "installed successfully."

## What passed, precisely

- [x] MO2 2.5.2 fetched from GitHub, hash recorded, extracted — no installer, no registry
- [x] Portable instance generated as text files, no GUI interaction at any point
- [x] MO2 accepted the hand-written ini and auto-detected FO4VR 1.2.72
- [x] F4SEVR 0.6.21 installed to the game dir; its `Data/Scripts` kept as a *mod*
- [x] Mods installed by directory placement (`mods/<name>/` Data-relative)
- [x] Game launched through MO2 via `moshortcut://`
- [x] usvfs virtualised `mods/` into `Data/` — proven by F4SEVR finding the plugin
- [x] usvfs redirected writes into `overwrite/` — game `Data/` untouched
- [x] **devbench answered on `127.0.0.1:8931`**

## What this run did *not* prove

Stated plainly, because a green result is the easiest place to smuggle in an unearned claim:

- **Nothing about the mod list.** Three mods were installed: devbench (a test plugin), the VR
  Address Library, and F4SEVR's scripts. No mod from
  [`../recipes/fo4vr/manifest.yaml`](../recipes/fo4vr/manifest.yaml) was downloaded, and no
  pin was resolved.
- **Nothing about downloads.** Every file came from GitHub or local disk. The VR Address
  Library CSV was taken from `C:\repos\BethesdaGhidraScripts\addresslibrary\f4` rather than
  Nexus 64879 — same payload, but the download path is still untested.
- **Nothing about conflicts.** Three non-overlapping mods cannot exercise `modlist.txt`
  ordering, which remains the most dangerous untested thing in the design.
- **Nothing about idempotency** (open question #7). The machine was clean, which is the easy
  case. This run does not touch it.
- **Nothing about playability.** A null-driver launch says the engine runs. It says nothing
  about whether the game is any good in a headset.
- **Nothing about the adaptive half.** No INI was tuned to this GPU; `Fallout4Custom.ini`
  holds only the minimum to serve loose files.

## Reproducing it

```powershell
core\tools\steamvr-null.ps1 -Enable
& "C:\Modding\mo2_fo4vr\ModOrganizer.exe" -p Default "moshortcut://:F4SEVR"
# wait ~10s
Invoke-RestMethod -Uri http://127.0.0.1:8931/api/tool/inspect -Method Post `
  -ContentType application/json -Body '{"kind":"state"}'
core\tools\steamvr-null.ps1 -Disable      # when done
```
