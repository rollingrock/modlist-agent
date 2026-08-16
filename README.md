# modlist-agent

**A deterministic mod recipe, plus an agent that adapts it to your machine and proves it worked.**

> Seeded 2026-08-16 as an idea, not an implementation. Nothing here has been built or run.
> The name is a placeholder — change it on day 1 if something better lands.
>
> **✅ First milestone passed, 2026-08-16.** A portable MO2 instance was generated from
> nothing, Fallout 4 VR launched through it, and `devbench` — a plugin living *only* inside
> MO2's virtual filesystem — answered on `127.0.0.1:8931` with
> `{exe: Fallout4VR.exe, extender: F4SE, vr: true, playerLoaded: true}`. Verification runs
> **headless** via SteamVR's null driver, so it needs no headset and can run in CI.
> Read [`docs/VERIFICATION.md`](docs/VERIFICATION.md).
>
> **Research pass, 2026-08-16.** Still no code, but the unknowns are much smaller.
> Start at [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md) — it now carries a status
> table and links to what each answer turned into:
> [`docs/NEXUS_DOWNLOADS.md`](docs/NEXUS_DOWNLOADS.md) (the download story, decided),
> [`docs/MO2_PORTABLE.md`](docs/MO2_PORTABLE.md) (portable MO2, verified against a real
> 2.5.2 instance), [`docs/MANIFEST_SCHEMA.md`](docs/MANIFEST_SCHEMA.md), and a first
> essential list at [`recipes/fo4vr/`](recipes/fo4vr/) — **researched, not verified.**

---

## The problem

If you want to mod Fallout 4 VR (or Skyrim VR) today, the practical advice is "go install a
Wabbajack list." That works, and it is a genuinely impressive piece of engineering, but it
has a shape that does not suit everyone:

- **It is all-or-nothing.** You take the author's taste in visuals, gameplay, difficulty and
  performance as a bundle. Removing pieces afterwards is often harder than not having them.
- **It is large.** Lists routinely run to hundreds of mods and tens of GB, for people whose
  actual goal was "make VR work properly and not crash."
- **You are at the mercy of the author.** Update cadence, hosting, what is included, whether
  it still installs at all.
- **Nobody has published a good minimal base.** There is no widely-used "just the essentials,
  correctly configured, nothing opinionated" starting point — which is what most people
  actually want before they add their own taste on top.
- **It cannot adapt.** A list is a fixed set of files. It does not know your GPU, your
  headset, your CPU budget, or where your Steam library lives. Every list ships one INI
  tuning and hopes.

## The idea

An **agent recipe**: a repo of pinned, hashed mod manifests plus instructions an AI agent
follows to stand up a **portable MO2 instance** on the machine in front of it — installing a
small essential base, tuning it to that system, and then verifying the result.

The output is a working portable MO2 instance the user owns and understands, not a black box.

## The core design principle

**Separate what must be reproducible from what must adapt.** These are different risks and
they get opposite treatment.

| Deterministic — in the manifest, pinned and hashed | Adaptive — the agent decides |
|---|---|
| Which mods, which versions, which exact files | Where Steam / the game / MO2 live |
| Load order and plugin flags | INI tuning for this GPU / CPU / headset |
| Install order and conflict winners | Resolving a conflict the manifest did not foresee |
| The FOMOD choices for each installer | Which *optional* extras suit this system |
| The expected end state used for verification | How to recover when a step fails |

The agent is never asked "what are good mods?" — that is the manifest's job, and a model
guessing there produces a build that dies three hours into a playthrough with no clue why.
The agent is asked "make this exact recipe work here, and tell me honestly if it didn't."

This is what a Wabbajack list structurally cannot do, so it is where the value is.

## Why an agent is genuinely the right tool

Not "because AI." Because the parts a static installer handles badly are all judgement:

- reading an error and knowing whether it is fatal or cosmetic
- noticing that a mod's requirement changed since the manifest was written
- picking INI values that fit 8 GB of VRAM versus 24
- explaining, in a sentence, what it just did and what the user should do next
- adapting when the user already has a partial setup rather than a clean machine

## Structure — start multi-game, cheaply

```
recipes/
  fo4vr/          <- first target
  skyrimvr/       <- second, and the reason the core exists
core/             <- MO2 portable setup, download/verify, load-order apply, checks
docs/
```

**Learned the hard way next door:** `devbench` began as a Skyrim tool, then had to be
restructured into "game-agnostic core + per-game platforms" once Fallout arrived. That
refactor was expensive and blocked other work. The seam costs almost nothing to put in on
day 1 and a lot to retrofit. Put it in now even while only `fo4vr` exists.

## The hard parts — read `docs/OPEN_QUESTIONS.md` before building

Ranked by how likely they are to sink it:

1. **Nexus downloads.** This is the blocker, not the modelling. Non-premium accounts cannot
   download via the API; Wabbajack works around this with a manual click-through step. Any
   design has to answer this honestly and within Nexus's terms.
2. **Verification.** "The agent said it worked" is not evidence. The recipe needs a
   machine-checkable end state.
3. **Drift.** Mods update and links rot. A pinned manifest goes stale; an unpinned one is
   not reproducible.

## First milestone

Not "a full list." One vertical slice that proves the shape:

> On a clean machine, stand up a portable MO2 instance for Fallout 4 VR with **F4SEVR plus a
> handful of essentials**, launch the game through MO2, and verify from *outside the agent's
> own narration* that the plugins actually loaded.

If that slice works end to end — including the download story — the rest is mostly more
manifest entries. If the download story does not work, better to learn it in week one.

A useful accident: `C:\repos\fallout4-scope-in-scope-investigation` needs exactly this. That
machine has Fallout 4 VR installed but no MO2 and no F4SEVR, and its plugins build but
cannot be loaded or tested. It is a real first customer with a real acceptance test —
`devbench` answering on `:8931` is a pass/fail signal that owes nothing to the agent's
self-report.
