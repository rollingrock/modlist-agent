# Open questions — decide these before writing code

Seeded 2026-08-16. These are the things that determine whether the project works at all.
None has been investigated yet; the confidence column is a starting guess, not a finding.

---

## 1. 🔴 Nexus downloads — the actual blocker

**The problem.** Nexus's API only serves download links to **Premium** accounts. Free
accounts must click through the website. This is precisely why Wabbajack has a manual
download phase and why it cannot be fully automated.

**Why it dominates everything else.** A recipe that cannot fetch its own files is a
document, not an installer. Solve this first — it constrains the whole design.

**Options, none free of cost:**

| Approach | Cost |
|---|---|
| Require Nexus Premium, use the API | Cleanest and fully automatable, but paywalls the project |
| Agent drives a browser to click downloads | Fragile, and needs a hard look at Nexus's ToS on automation |
| Manual download phase, agent handles the rest | Honest and ToS-safe; the user does the boring part |
| Prefer mods hosted outside Nexus where equivalents exist | Shrinks the essential list, may not cover it |

**Read the Nexus API terms and acceptable-use policy before choosing.** "It technically
works" is not the test. Do not design around scraping without checking.

**Open:** does the mod set even need Nexus? F4SEVR is off-site. How much of a *minimal* VR
base is Nexus-only?

---

## 2. 🔴 Verification — how do we know it worked?

The agent's own report is the weakest possible evidence. The neighbouring project has an
expensive lesson here: a diagnostic (`/scope?probe=1`) that *performed the fix it was
measuring*, so it read healthy every time it was looked at and was broken whenever it was
not; and a `PixelDark` check that tested the wrong exponent, so twelve thousand readbacks
across five sessions all confidently said "fine" about a buffer full of NaN.

**Principle: verify with a signal the agent does not produce.**

Candidates, strongest first:

- **An F4SE plugin answers over HTTP.** `devbench` on `:8931` replying to `ping` proves the
  game launched, F4SEVR loaded, and a plugin initialised. The agent cannot fake it.
- **`f4sevr.log` / `ModOrganizer.log` contents** — plugin count, load order, errors.
- **File hashes** of what was installed versus the manifest.
- **A screenshot** — weakest, but catches "black screen" that logs miss.

**Open:** what is the minimum pass/fail set? What does a *partial* success look like, and
does the agent stop or continue?

---

## 3. 🟠 Drift — pinned versus current

Pinned manifests go stale (dead links, removed mods, a requirement that silently changed).
Unpinned manifests are not reproducible, which was the whole point.

**Open:**
- Pin version *and* file hash, or version only?
- What happens when a pin is unavailable — hard fail, or agent-judged substitution? (Hard
  fail is safer; substitution is where a well-meaning model invents a broken build.)
- Is there a CI job that periodically checks every link still resolves?
- How do we record *why* a mod is in the list, so a future maintainer can judge a
  replacement? A one-line rationale per entry is cheap and pays for itself.

---

## 4. 🟠 What is "essential"? — the scope trap

The pitch is "a small essential base." Every such project grows until it is another 300-mod
list. The discipline is in the exclusion rule, written down before the first PR.

**Proposed rule (challenge it):** a mod earns a place only if it fixes something *broken or
missing* in the vanilla VR experience — not something a person might prefer. Bug fixes,
the script extender, VR interaction, performance, stability. **No** visual overhauls, **no**
gameplay rebalancing, **no** new content.

**Open:** does FRIK count? (VR body/weapon handling — arguably fixes something genuinely
missing.) Where exactly is the line, and who adjudicates?

---

## 5. 🟡 MO2 portable instance mechanics

Believed straightforward but unverified: `portable.txt` plus a generated `ModOrganizer.ini`,
mods as directories under `mods/`, load order in `loadorder.txt` / `plugins.txt`, profiles
under `profiles/`.

**Open:**
- Exact minimum `ModOrganizer.ini` for a portable FO4VR instance
- Which MO2 version, and does it need registering the game manually for VR?
- Can MO2 be driven headlessly enough for CI, or does it always need a GUI?
- FOMOD installers: scriptable, or does the agent need to make choices per install?

---

## 6. 🟡 Legal and ethical guardrails

- **No redistribution of mod files.** The repo holds manifests and instructions only.
- **Respect each mod's licence and the author's wishes** — some explicitly forbid automated
  redistribution or repackaging.
- **Nexus ToS on automation** — see §1; this is a real constraint, not a formality.
- The agent must not silently accept EULAs or create accounts for the user.

---

## 7. 🟡 Idempotency and recovery

Real users run this on a machine that is already half set up.

**Open:**
- Can the recipe be re-run safely over an existing instance?
- Does it detect and adopt an existing MO2 instance, or refuse and require a clean target?
- On failure partway, does it roll back, resume, or leave a diagnosable mess? (Leaving a
  *diagnosable* mess is a legitimate choice — say so explicitly rather than by accident.)

---

## 8. 🟢 Which model tier actually suffices

The premise is that a Sonnet-level model handles this. Plausible, and worth testing rather
than assuming, because the answer shapes the instructions: a weaker model needs more
explicit steps and fewer judgement calls.

**Open:** build the FO4VR slice, then run it end to end on a smaller model and count the
interventions. That number is the real product metric.
