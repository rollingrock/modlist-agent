# fo4vr — what is in the list, and what is not

Companion to [`manifest.yaml`](manifest.yaml). This file is the argument; the manifest is
the data. **Edit this when you edit the list** — an entry whose rationale nobody wrote down
is an entry nobody can later judge a replacement for.

> **Status: researched, not verified.** No pin has been resolved, nothing has been
> downloaded, nothing has been launched. Versions come from published community lists,
> chiefly [Florine's Fallout 4 VR](https://github.com/FWDekker/fo4vr-modlist) (v1.3.1),
> cross-checked against Nexus and the Steam VR forums. Treat every number as a starting
> point for verification.

---

## The rule

From open question #4, applied strictly:

> **A mod earns a place only if it fixes something broken or missing in vanilla FO4VR.**
> Not something a person might prefer.

The test used on every candidate: *can I write the `why` line without the words "nicer",
"better", "more immersive", or "I like"?* If not, it is out — however good it is.

This cuts hard. Florine's list is ~60 mods; the essential base is **14**. That gap is the
product. Nothing in the graphics, lighting, sound, difficulty or settlement sections
survived, and none of them should — they are that author's taste, and taste is what the user
adds on top of a base they understand.

## What is in

| Tier | Count | What it means |
|---|---|---|
| `tools` | 2 | MO2 and F4SEVR. Infrastructure, not mods, and **neither is on Nexus.** |
| `foundation` | 4 | Nothing else loads without these. Pure dependency. |
| `fix` | 7 | Vanilla VR is wrong or missing something. The actual list. |
| `performance` | 2 | Installed deterministically, **configured adaptively** by the agent. |
| `candidate` | 1 | Not adjudicated. Present as data, disabled, awaiting a decision. |

**13 mods are actually installed** (4 + 7 + 2); the remaining candidate is carried disabled so
the open question travels with the data instead of living only in this prose.

Down from 14 after the scope mods were cut — see decision 4. That is the list moving in the
right direction: an essential base should shrink when a defect gets fixed properly.

### The performance tier is the interesting one

`vrperfkit` is where the two halves of the design meet in one entry. *Which* file is
installed is pinned to a hash. *What goes in `vrperfkit.yml`* — upscaler, render scale,
foveation — is the agent's call from the real GPU, VRAM, headset resolution and measured
frametime. The manifest names the keys the agent may decide (`adaptive.decide`) so that
"adaptive" is a bounded permission rather than a free hand.

That is the thing a Wabbajack list structurally cannot do, expressed as a data structure.

## What is out, and why

**Everything DLC-gated.** Fallout 4 VR ships standalone with no DLC, and the local install
confirms it: `Data/` holds `Fallout4.esm` and `Fallout4_VR.esm` and nothing else. So these
are excluded despite being genuine fixes:

| Mod | Why excluded |
|---|---|
| **UFO4P** (Unofficial Patch) | Requires all DLC. Genuinely painful to lose — it is the single largest bugfix in the ecosystem — but a hard dependency we cannot satisfy. |
| **DLCVR** | Its entire purpose is making DLC work in VR. Moot with no DLC. |
| **Edmond's Automatron VR Workbench Rebuild** | Requires Automatron + Nuka-World. |
| **Bullet Time VATS VR** | Requires Far Harbor + Nuka-World. Would also have failed the rule as rebalancing. |

If you own FO4 flat with DLC (likely — `Fallout 4` is in the same Steam library), DLCVR plus
UFO4P becomes reachable and is worth a **second, opt-in tier**. Do not fold it into the base;
it doubles the failure surface and the base must work on a bare FO4VR.

**Everything aesthetic.** Fallout 4 HD Overhaul, Vivid Fallout, Visible Galaxy, Water
Enhanced, Detailed Feral Ghouls, Darker Nights, PhyLight, Fr4nsson's Light Tweaks, Interiors
Enhanced, every sound mod, Burst Impact Blast FX. All good; all taste; all out. Note that
several are marked "Required" in Florine's list — required *for that list's look*, which is
exactly the all-or-nothing bundling this project exists to unpick.

**Everything that changes the game.** Sim Settlements, backpacks, loot rebalancing,
radiation overhaul, survival options, headshot multipliers, Everyone's Best Friend. New
content or rebalancing. Out.

## Decisions — reviewed and settled 2026-08-16

All four open calls plus one were resolved by the developer in review. Recorded here with the
reasoning, because the reasoning is what a future maintainer needs.

### 1. FRIK — in, and not actually a borderline case

Open question #4 flagged FRIK as the hard call. It is not one: **FRIK is this project's
developer's own mod**, source next door at `C:\repos\Fallout-4-VR-Body`.

That changes three things beyond the obvious. Its `why` line is first-hand rather than
inferred from a mod page. A dead pin is a build, not a dead end. And the rule-bending
argument I made — that vanilla's floating hands are an *absence*, so "missing" counts as
"broken" — stands on its own merits rather than being the thing holding the entry up.

**The precedent still matters** for future entries: *missing* counts as *broken* only when
vanilla's version of a thing is an absence, not a poor implementation. That is a narrow door.
Vivid Fallout does not fit through it.

**No staging.** Published lists disable FRIK until after the vault prologue; this list does
not. The prologue is skippable with `coc` or an alternate-start mod, and the prologue issues
that motivated the convention are fixed anyway. Staging would inject a stateful,
mid-playthrough step into a recipe whose entire value is being reproducible — the cure is
worse than the disease.

It costs nothing at verification time either: devbench's `console` tool can run `coc`
directly, so the agent skips the prologue itself with no human touching the game. **The
`enabled: false` field stays in the schema** — it is still the right representation for a mod
that must ship installed-but-off — it just has no user in this recipe today.

### 2. Buffout — settled: alandtse's fork, and only that

**The one we use is [alandtse/Buffout4](https://github.com/alandtse/Buffout4) = Nexus 64880**
("Buffout 4 NG and VR"), which is the VR-capable maintained fork. The original Buffout 4
(47359) is Ryan-rsm-Mckenzie's and is **not** installed alongside it.

So the suspicion was right: published lists that install both are cargo-culting. The
empirical crash-log test is no longer needed to decide *what to install* — though it is still
worth running once as a check that crash logging actually works.

It being open source matters for drift (open question #3): if the Nexus pin ever dies, this
entry can be built from source rather than substituted.

`address-library-f4se` (47327, the flat-FO4 1.10.163 library) stays parked as a `candidate` —
separate question, still unresolved.

### 3. DLC — deliberately deferred

Skipped for now. Not because it is uninteresting but because it is *needlessly complicated
right now*: it doubles the failure surface for a base that must work on a bare FO4VR install
anyway.

**Revisit later, and treat it as an agent-robustness problem rather than a mod-list problem.**
The interesting question is not "can we install DLCVR" — it is whether the agent can detect
which DLC a machine actually has, adapt the manifest to it, and fail honestly when it cannot.
That is a good test of the adaptive half, which is exactly why it deserves its own pass
instead of being smuggled into the base.

### 4. Scope mods — all removed

**No scope mods. Not See-Through-Scopes, not Better Scopes VR.**

Not an exclusion-rule call. The picture-in-picture scope is being fixed **at the engine
level** in `C:\repos\fallout4-scope-in-scope-investigation`, which eliminates the defect every
scope mod exists to work around. Installing a workaround for a bug you have actually fixed is
strictly worse than installing nothing: it is dead weight that will eventually conflict with
the real fix.

This is the first entry decided by *what this development environment is building* rather than
by what Nexus offers, and it points somewhere the project had not anticipated: **when the
native fix ships as a plugin it becomes an entry in this list, with an upstream that is this
developer rather than Nexus.** The manifest already supports that — `source.type: github` and
the `upstream` field — but it is worth naming as a direction.

### 5. Full Dialog VR — kept

I flagged it as the entry I could least defend under the rule. Reviewed and kept as-is
(`required: false`, enabled).

### 6. Version Check Patcher — in, with a caveat

It disables a safety check. That is the point (vanilla rejects most working FO4 mods on
version mismatch), but a build that skips version validation is a build where a genuinely
incompatible plugin loads and crashes weirdly instead of refusing cleanly. Included because
the list is unusable without it; flagged because if the slice produces an inexplicable crash,
this is the first thing to suspect.

## Things the research turned up that change the plan

**The bootstrap is entirely Nexus-free.** MO2 comes from GitHub, F4SEVR from silverlock, and
a verified F4SEVR **0.6.21** for runtime **1.2.72** — exactly this machine's game version —
already sits in `C:\repos\f4sevr`. The vertical slice can therefore be proven end to end
*before* the download story is solved. See [`../../docs/NEXUS_DOWNLOADS.md`](../../docs/NEXUS_DOWNLOADS.md).

**F4SEVR is 0.6.21, not 0.6.20.** Every published list still says 0.6.20. The local copy's
readme says 0.6.21, with `0.6.21 — VR: fix kMessage_GameDataReady` in the changelog. A small
demonstration of why pins need dates and why "the community list says X" is a lead, not a
fact.

**The game is unmodded and clean.** `Fallout4VR.exe` is 1.2.72.0; `Data/` is vanilla; there
is no F4SE, no MO2, no `Documents\My Games\Fallout4VR` profile to conflict with. This is the
clean-machine case, which is the easy one — the idempotency questions (open question #7) stay
open because nothing here will exercise them.

## The verification signal, and its own honest caveat

The plan is `devbench` answering on `127.0.0.1:8931` — proving the game launched, F4SEVR
loaded, and a plugin initialised, from a signal the agent does not produce.

**`devbench`'s Fallout platform builds but has never run in-game.** Its own docs say so:
*"no endpoint has answered a live request yet. Treat the endpoint list below as the intended
contract, not as a tested one."*

So the acceptance test is itself unproven. That is not a reason to pick a different signal —
it is the same one-time cost either way, and a `ping` that returns `{ok, game, exe, vr}` is
strictly better evidence than a log grep. But it must be stated plainly: **the first slice is
bootstrapping two unproven things against each other.** If it fails, the first question is
*which one*, and the cheap discriminator is a log check
(`Documents\My Games\Fallout4VR\F4SE\f4sevr.log` showing the plugin loaded) that separates
"F4SEVR did not load devbench" from "devbench loaded but the server did not bind."

## Sources

- [Florine's Fallout 4 VR modlist](https://github.com/FWDekker/fo4vr-modlist) — the most complete published FO4VR list found; the base this was subtracted from
- [FRIK](https://www.nexusmods.com/fallout4/mods/53464), [Buffout 4 NG and VR](https://www.nexusmods.com/fallout4/mods/64880), [xSE PluginPreloader F4](https://www.nexusmods.com/fallout4/mods/33946)
- [Fallout VR Essentials Overhaul](https://www.nexusmods.com/fallout4/mods/96013), [Fallout 4 VR Fundamental Essentials](https://www.nexusmods.com/fallout4/mods/102510) — cross-checks
- Local: `C:\repos\f4sevr` (0.6.21), `C:\Program Files (x86)\Steam\steamapps\common\Fallout 4 VR` (1.2.72.0), `C:\Modding\mo2_sf` (MO2 2.5.2)
