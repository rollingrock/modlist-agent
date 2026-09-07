# CI — what can be automated, and the one thing that cannot

Short answer to "can this be CI'd?": **most of it, yes — and the most valuable part
already is. But the end-to-end run cannot happen on a hosted runner, and no amount of
cleverness fixes that.**

---

## The hard blocker

`verify` needs Fallout 4 VR actually running. That requires:

| Requirement | Hosted runner reality |
|---|---|
| The game — a **paid ~25 GB Steam title** | Cannot be installed. SteamCMD needs credentials, Steam Guard 2FA blocks automation, and sharing an account violates Steam's terms. |
| **Disk** for game + instance + downloads | GitHub's Windows runners have roughly 14 GB free. The game alone does not fit. |
| **A GPU** | Hosted runners have no GPU. The null driver removes the *headset* requirement, not the *rendering* one — the engine still creates a D3D11 device and renders frames. |
| **SteamVR** | Also a Steam install, same problem. |

The null driver was a genuine unlock — it made verification *unattended*, which is most of
what people want from CI. It does not make it *hostable*, and it is worth being precise
about the difference rather than implying we solved more than we did.

**So: "prove it on a truly clean system" is achievable, but the clean system has to be a
machine that owns the game.** A fresh VM or a spare box with FO4VR installed, registered
as a self-hosted runner, is the real version of that idea — and it would be a genuinely
strong result, because it would exercise the one case this project has never tested: a
machine that is not this one.

## The two tiers

### Tier 1 — hosted, every push (`.github/workflows/ci.yml`)

Needs nothing but Python. Runs on forks and PRs.

- **`pytest core/tests/test_generation.py`** — 17 tests, no game, no network, ~0.2s.
  Each one corresponds to a bug that actually happened: the winner-first ordering rule,
  `@ByteArray` backslash doubling versus forward slashes in the same file, space-free
  executable titles, archive-root detection, and the manifest validation rules.
- **`mla check --no-nexus`** — manifest self-consistency plus liveness of every off-site
  source (GitHub releases, silverlock).

### Tier 1b — hosted, weekly, needs `NEXUS_API_KEY`

- **`mla check`** — for every pinned Nexus file: does the mod still exist, is it still
  published, **is the pinned `fileId` still there**, and has a newer MAIN file appeared?

  **Metadata only, deliberately.** Re-downloading 54 MB of mods nightly to prove nothing
  changed would be a rude use of someone else's bandwidth, and the API's acceptable-use
  policy is a reason to be careful rather than clever. Hashes are checked when a manifest
  changes, not on a timer.

  It skips gracefully when the secret is absent, so forks are not confusingly red.

### Tier 2 — self-hosted, manual (`workflow_dispatch`)

`doctor → build → download → install → conflict-test → verify`, with the SteamVR null
driver enabled and **always restored**, even on failure — it is global state that would
otherwise hijack a real headset.

Runner labels: `[self-hosted, windows, fo4vr]`. Env: `MLA_INSTANCE`, `MLA_HARNESS`.

## Reading a failure

Exit codes are meaningful throughout, and this matters more than usual here:

| Code | Meaning |
|---|---|
| 0 | pass |
| 1 | fail — a real, diagnosed problem |
| 2 | **inconclusive** — no result, cause unknown |

`verify` never collapses 2 into 1. A missing dependency once produced a modal dialog with
no crash and no error code, and a CI job that reported that as "failed: mods broken" would
have been confidently wrong. Inconclusive means *go look*, not *it is broken*.

`mla check` treats a **dead pin as failure** and a **newer version as news** (`--strict`
turns news into failure, off by default). A newer file upstream is not a defect — the pin
is doing exactly its job — but it is the signal a maintainer needs.

**It also returns 2, and that is not a failure.** An off-site source whose host did not
answer is *unreachable*, which says nothing about whether the pin is still good. The
distinction was forced on 2026-09-07: a scheduled run reported `1 dead` because
`f4se.silverlock.org` timed out from a GitHub runner while answering `301` in 0.16s from
the developer's machine. Turning a third party's egress into a red board is noise, and
noise is how a genuinely dead pin later gets waved through. Connection failures are
retried, a definite HTTP answer is not, and the hosted jobs print
`INCONCLUSIVE (a host did not answer)` and stay green.

Both hosted steps iterate **every** `recipes/*/manifest.yaml` rather than naming one.
They named `fo4vr` explicitly until `recipes/fo4` arrived with no coverage at all and
nothing said so.

## What CI still would not prove

Worth stating so a wall of green does not imply more than it should:

- **That the result is any good in a headset.** Verification proves plugins load. It says
  nothing about comfort, performance, or whether the game is fun. No automated check will
  ever cover that.
- **Idempotency** (open question #7). Every run so far, CI included, starts from a
  deleted instance. The half-set-up machine real users have is still untested, and a
  clean-machine pass is not evidence about it.
- **Conflict resolution among real mods.** The conflict test uses two synthetic mods. No
  two mods in the recipe are yet known to fight, so the ordering machinery is correct but
  unexercised by anything real.
- **The free-account download path**, which is written and has never run.
