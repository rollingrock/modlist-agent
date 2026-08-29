# Open questions — decide these before writing code

Seeded 2026-08-16. These are the things that determine whether the project works at all.
None has been investigated yet; the confidence column is a starting guess, not a finding.

> **Status update, 2026-08-16 (same day, first research pass).** Four of these moved.
> The two 🔴 blockers are both smaller than they looked. Summary:
>
> | # | Was | Now | Where |
> |---|---|---|---|
> | 1 | 🔴 Nexus downloads | 🟢 **Decided.** Two-path design; bootstrap is Nexus-free | [`NEXUS_DOWNLOADS.md`](NEXUS_DOWNLOADS.md) |
> | 2 | 🔴 Verification | 🟢 **PROVEN.** devbench answered on `:8931` from a running FO4VR | [`VERIFICATION.md`](VERIFICATION.md) |
> | 3 | 🟠 Drift | 🟢 **Decided.** Pin `(fileId, sha256)`; hard fail on violation | [`MANIFEST_SCHEMA.md`](MANIFEST_SCHEMA.md) |
> | 4 | 🟠 "Essential" | 🟢 **Rule applied.** 14 entries, FRIK adjudicated in | [`../recipes/fo4vr/README.md`](../recipes/fo4vr/README.md) |
> | 5 | 🟡 MO2 mechanics | 🟢 **Answered, then verified** by building and launching one | [`MO2_PORTABLE.md`](MO2_PORTABLE.md) |
> | 6 | 🟡 Legal | 🟢 Folded into #1's design; unchanged as constraints | [`NEXUS_DOWNLOADS.md`](NEXUS_DOWNLOADS.md) |
> | 7 | 🟡 Idempotency | 🔴 **Untouched, and now the biggest open risk** | — |
> | 8 | 🟢 Model tier | 🟢 Untouched; still the right metric, still needs the slice first | — |
>
> Per-question detail is inline below. The original text is preserved — a question's
> starting guess is worth keeping next to what it turned out to be.

---

## 1. 🟢 Nexus downloads — the actual blocker

> **DECIDED — see [`NEXUS_DOWNLOADS.md`](NEXUS_DOWNLOADS.md).** Two findings shrank this:
> (a) only *one* endpoint is gated (`download_link.json`); all metadata is free-account
> accessible, so the manifest fully resolves and verifies without Premium. (b) The
> sanctioned `nxm://` handler channel means the free path is "user clicks a button, agent
> does everything else," not "user downloads 20 archives by hand." Browser automation is
> **rejected and closed.** And the whole bootstrap — MO2, F4SEVR, vrperfkit — is off-Nexus,
> so the first slice can be proven before any of this is implemented.

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

## 2. 🟢 Verification — how do we know it worked?

> **PROVEN — see [`VERIFICATION.md`](VERIFICATION.md).** devbench answered on
> `127.0.0.1:8931` from a running Fallout 4 VR on 2026-08-16, returning
> `{exe: Fallout4VR.exe, extender: F4SE, vr: true, playerLoaded: true, frame: 4156}`. This
> was also **devbench's first live response ever**, so both unproven halves are now proven.
>
> The signal is stronger than expected: `devbench.dll` existed only in `mods/`, so one
> response proves *both* that the game ran and that MO2's virtualisation worked.
>
> **Verification is unattended.** SteamVR's null driver lets the game initialise with no
> headset, so this runs in CI — see `core/tools/steamvr-null.ps1`. That was not in the
> original plan and it materially changes what is possible.
>
> Still open, and now sharper: the **partial success** question. The one failure observed
> was a missing dependency presenting as a *modal dialog* — a silent hang with no crash and
> no error code. So the pass/fail set needs a third state: pre-launch dependency checks, a
> launch timeout, and "no response, no crash" reported as **inconclusive**, never as a
> diagnosed failure.

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

## 3. 🟢 Drift — pinned versus current

> **DECIDED — see [`MANIFEST_SCHEMA.md`](MANIFEST_SCHEMA.md).** Pin `(modId, fileId)` +
> `sha256`, not version — authors re-upload under the same version string. `(modId, fileId)`
> is MO2's own pin, read straight out of a real `meta.ini`, so generated instances stay
> native to MO2. **Hard fail on a violated pin**, never substitution. Absent vs violated is
> treated asymmetrically: a `null` pin may be resolved by the agent *and proposed for human
> commit*; a mismatching pin stops the run. `why` is mandatory per entry and CI-enforced —
> that was the cheap idea below and it survives. CI link-checking: yes, listed in the schema.

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

## 4. 🟢 What is "essential"? — the scope trap

> **RULE APPLIED — see [`../recipes/fo4vr/README.md`](../recipes/fo4vr/README.md).** The
> proposed rule below survived contact and is now enforced with a concrete test: *can the
> `why` be written without "nicer", "better", "more immersive", "I like"?* Applied to the
> most complete published FO4VR list (~60 mods), it leaves **14**. That subtraction is the
> product.
>
> **FRIK: adjudicated IN**, and the precedent is narrow — *missing* counts as *broken* when
> vanilla's version of a thing is an absence rather than a poor implementation. Floating
> hands with no body qualifies; so does a scope that blanks the world when you aim. A
> prettier texture does not. Who adjudicates: whoever writes the `why` line, in the open,
> in that README.
>
> Newly discovered constraint: **FO4VR ships with no DLC**, which excludes UFO4P, DLCVR and
> others on dependency grounds regardless of the rule. Losing UFO4P genuinely hurts. A
> second opt-in DLC tier is the answer, not folding it into the base.
>
> **Corrected 2026-08-29.** That is true of the *product*, not of every *disk*. On the
> machine that built the verified test instance all six official DLC are present in the
> game directory, and the engine loads them itself with no `plugins.txt` entry — so the
> masters a DLC-dependent mod needs can very well exist. The exclusions stand, but on the
> ground that the base must install on a bare FO4VR, not on the masters being absent,
> which is a property of the machine rather than of FO4VR.

The pitch is "a small essential base." Every such project grows until it is another 300-mod
list. The discipline is in the exclusion rule, written down before the first PR.

**Proposed rule (challenge it):** a mod earns a place only if it fixes something *broken or
missing* in the vanilla VR experience — not something a person might prefer. Bug fixes,
the script extender, VR interaction, performance, stability. **No** visual overhauls, **no**
gameplay rebalancing, **no** new content.

**Open:** does FRIK count? (VR body/weapon handling — arguably fixes something genuinely
missing.) Where exactly is the line, and who adjudicates?

---

## 5. 🟢 MO2 portable instance mechanics

> **ANSWERED — see [`MO2_PORTABLE.md`](MO2_PORTABLE.md).** Verified against a real MO2
> **2.5.2** instance (`C:\Modding\mo2_sf`), which is the current release, so the findings are
> current rather than historical. Highlights: FO4VR is natively supported (`game_fallout4vr.dll`
> ships in the box — **no manual game registration**); the whole instance is generatable as
> text files with no GUI; installing a mod is archive extraction into a Data-relative
> `mods/<name>/`; **`modlist.txt` is written bottom-up so the first line wins conflicts**,
> which is a silent-wrong-answer footgun that needs a test; and `ModOrganizer.ini` spells the
> same path two different ways in one file (`@ByteArray` with doubled backslashes vs forward
> slashes). Portable means self-contained, **not relocatable** — absolute paths bake in, which
> is why paths are generated per machine and never committed.
>
> Only the *launch* needs MO2's process, for usvfs. FOMOD reduces from "agent clicks through
> a GUI" to "manifest specifies choices as data."

Believed straightforward but unverified: `portable.txt` plus a generated `ModOrganizer.ini`,
mods as directories under `mods/`, load order in `loadorder.txt` / `plugins.txt`, profiles
under `profiles/`.

**Open:**
- Exact minimum `ModOrganizer.ini` for a portable FO4VR instance
- Which MO2 version, and does it need registering the game manually for VR?
- Can MO2 be driven headlessly enough for CI, or does it always need a GUI?
- FOMOD installers: scriptable, or does the agent need to make choices per install?

---

## 6. 🟢 Legal and ethical guardrails

> **CHECKED, UNCHANGED.** The Nexus API AUP explicitly *welcomes* third-party managers; what
> it forbids is scraping-to-rehost, which this project does not do (the `.gitignore` already
> forbids committing archives). Applications should be registered before going public and
> open-sourcing is encouraged. The constraints below stand as written and are now enforced
> by the design in [`NEXUS_DOWNLOADS.md §6`](NEXUS_DOWNLOADS.md): API key never password,
> no account creation, no EULA acceptance, and the agent never clicks a download button.

- **No redistribution of mod files.** The repo holds manifests and instructions only.
- **Respect each mod's licence and the author's wishes** — some explicitly forbid automated
  redistribution or repackaging.
- **Nexus ToS on automation** — see §1; this is a real constraint, not a formality.
- The agent must not silently accept EULAs or create accounts for the user.

---

## 7. 🔴 Idempotency and recovery

> **UNTOUCHED — and promoted, because everything around it moved.** With #1 and #5 answered,
> this is now the largest unexamined risk. Worse, **this machine cannot exercise it**: the
> FO4VR install is pristine (vanilla `Data/`, no F4SE, no MO2, no
> `Documents\My Games\Fallout4VR` profile). The clean-machine case is the easy one, so the
> first slice will pass without touching any of the questions below. Do not read that pass
> as evidence they are handled.

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

---

## Where the project actually stands

**The first milestone is done** — [`VERIFICATION.md`](VERIFICATION.md). Steps 1 and 2 of the
plan below were executed the same day and both passed; step 3 is where work resumes.

~~**1. Stand up the instance and launch through MO2.**~~ **Done.** `C:\Modding\mo2_fo4vr`,
MO2 2.5.2 from GitHub, instance generated as text files with no GUI interaction.

~~**2. Then add exactly one plugin: devbench.**~~ **Done, and it answered.** Also devbench's
first live run. It cost one real debugging cycle: the missing VR Address Library surfaced as
a modal dialog and a silent hang, which is now written up as a design constraint rather than
a war story.

**3. Resolve pins — this is next.** Every `fileId: null` and `sha256: null` in
[`../recipes/fo4vr/manifest.yaml`](../recipes/fo4vr/manifest.yaml) needs one API call. Now
safe to do, because there is a verified instance to install into and a working acceptance
test to check the result against. One pin is already real: MO2 2.5.2's `sha256`.

**4. Then the first genuine conflict.** Everything installed so far is non-overlapping, so
`modlist.txt` ordering — the bottom-up footgun, the single most dangerous untested thing in
the design — has never been exercised. It needs two mods that actually fight, and a test.

Still true, still untouched: **#7 idempotency**, and the clean machine means the passing run
says nothing about it. That remains the biggest unexamined risk.
