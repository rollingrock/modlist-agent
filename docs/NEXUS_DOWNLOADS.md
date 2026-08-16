# Nexus downloads — the decision

Answers open question **#1**, the one ranked most likely to sink the project. Written
2026-08-16 from the Nexus API acceptable-use policy, the official API client's own
documentation, and a real MO2 instance's download records.

**Verdict: this is not a blocker.** It is a two-path design, and the constraint is smaller
than the seed doc assumed for two independent reasons — one about *how much* of the recipe
touches Nexus at all, and one about a sanctioned automation channel that already exists.

---

## 1. What the rules actually say

**The API is free to use and third-party managers are welcomed.** The Acceptable Use Policy
encourages public-facing applications, asks that they be registered before going public,
and strongly encourages open-sourcing them. This project is a normal, expected client — not
a grey-area one.

**What is prohibited is scraping:** *"fetching data en-masse with the intent to rehost this
information on your own service."* This project rehosts nothing (the `.gitignore` already
forbids committing archives) and fetches per-file metadata for a few dozen pinned files.
Comfortably inside the line.

**Rate limits:** 300 requests/hour, 600 for Premium, recovering ~1/second and burstable.
A manifest of ~20 mods needs on the order of 40 requests to resolve and verify. Two orders
of magnitude of headroom; not a design constraint.

**Requests must identify the application** via headers. Do this properly — an honest
user-agent is both the rule and what keeps the project welcome.

## 2. The actual restriction

One endpoint is gated, and only one:

```
GET /v1/games/{game}/mods/{modId}/files/{fileId}/download_link.json
```

From the official client's own signature:

```typescript
getDownloadURLs(modId, fileId, key?, expires?, gameId?)
// "If the user isn't premium on Nexus Mods, this requires a key
//  that can only be generated on the website."
```

- **Premium account:** call it with an API key, get CDN URLs, download. Fully automatable.
- **Free account:** you must additionally supply `key` + `expires`, which are **only**
  minted by the website's *"Mod Manager Download"* button.

Everything else — mod info, the file list, versions, changelogs, MD5 lookup — is open to
any account. **So the manifest can be fully resolved and verified on a free account.** Only
the bytes need the extra step.

## 3. The channel the seed doc missed: `nxm://`

The seed doc framed the free-account path as "the user does the boring part manually," and
treated browser automation as the only alternative. There is a third thing, and it is the
mechanism Nexus itself built for this:

**"Mod Manager Download" emits an `nxm://` URL that the OS hands to a registered handler.**
The dissected MO2 instance ships `nxmhandler.exe` and `nxmhandler.ini` for exactly this.
The URL carries the `key` and `expires` the API needs:

```
nxm://fallout4/mods/64879/files/271234?key=<...>&expires=<...>&user_id=<...>
```

So the free-account flow is not "download 20 archives by hand into the right folder." It is:

1. The agent registers a handler (or reuses MO2's) and prints the exact file page URLs.
2. The user clicks *Mod Manager Download* once per file. **Clicks only** — no filenames, no
   destinations, no version picking.
3. Each click hands the agent a signed `nxm://` link; the agent resolves, downloads,
   hashes, verifies against the manifest, and installs.

**Nobody automates a click that the user did not make.** The website stays the authorising
step, exactly as designed. This is the same mechanism every mod manager uses, and it is what
makes the free path *pleasant* rather than merely *legal*.

## 4. The path not taken

Browser automation that clicks Nexus's download buttons on the user's behalf (the
`NexusAutoDL` pattern) is deliberately **out of scope**. It exists and it works. It also
routes around the exact gate Nexus put there on purpose, and gets the project's API
registration pulled the day someone notices.

The `nxm://` handler achieves the same end state — the user clicks, the agent does
everything else — while being the sanctioned mechanism rather than a circumvention of it.
There is no reason to take the risk for no gain. **This one is closed; do not revisit it.**

## 5. How much of the recipe even touches Nexus

Open question #1 ended with: *"does the mod set even need Nexus?"* Checked against the
essential list in [`../recipes/fo4vr/`](../recipes/fo4vr/):

| Component | Source | Nexus? |
|---|---|---|
| Mod Organizer 2 (2.5.2) | GitHub releases | **No** |
| F4SEVR 0.6.21 | `f4se.silverlock.org` | **No** |
| vrperfkit, fo4vr_improvements | GitHub (fholger) | **No** |
| VR Address Library, FO4VR Tools, Buffout 4 NG+VR, xSE PluginPreloader, FRIK, Better Scopes VR, … | Nexus | Yes |

**The entire bootstrap is Nexus-free.** MO2 stands up, F4SEVR installs, the game launches
through MO2 — all before a single Nexus request. That has a concrete consequence for the
first milestone: *the vertical slice can be proven end to end without solving the download
story at all.* Launch through MO2, get devbench answering on `:8931`, and the riskiest
unknown in the project is retired using only GitHub and silverlock.

The Nexus-hosted mods are the ones that make the list *good*, not the ones that make the
slice *work*. That is a much better position than the seed doc assumed.

## 6. The design

**Two paths, same manifest, same verification. Premium is a speed-up, never a requirement.**

```
resolve   (free)     metadata, file list, MD5 → manifest check
  │
  ├── Premium + API key ──▶ download_link.json ──▶ fetch ──┐
  │                                                        ├──▶ hash ──▶ install
  └── Free ──▶ print URLs ──▶ user clicks ──▶ nxm:// ──────┘
```

Non-negotiables:

- **Never store the user's Nexus password.** API key only, from the user's account page.
- **Never create an account or accept an EULA** on the user's behalf (open question #6).
- **Hash every file after download**, on both paths. Premium is faster, not more trusted.
- **The agent must not click download buttons.**

## 7. Note for this machine

The dissected Starfield instance's `.meta` files hold download URLs pointing at
`chicago-premium.nexus-cdn.com`, `amsterdam-premium…` and friends, signed with a `user_id`.
Premium CDN hosts are not served to free accounts, so **the machine's owner very probably
has Nexus Premium** — meaning the fast path is available here from day one.

Do not let that shape the design. Building Premium-only would paywall the project for
everyone else, and the free path is what proves the design is honest. Build the free path
first *because* the fast path is available to test against — having both on one machine is
lucky, not a reason to skip one.

## What remains unverified

- [ ] Confirm the account is actually Premium (ask; do not probe)
- [ ] Whether `nxmhandler.exe` can be pointed at our own listener without disturbing the
      user's existing MO2 handler registration — **do not clobber a working association**
- [ ] Application registration: what it requires and whether it is needed pre-public
- [ ] Whether the API's MD5 lookup can verify a file *before* download (would let the
      manifest's hash be checked against Nexus's own record, not just our bytes)
- [ ] Exact rate-limit response headers, for honest backoff rather than guessing

## Sources

- [API Acceptable Use Policy](https://help.nexusmods.com/article/114-api-acceptable-use-policy)
- [Nexus Mods API documentation](https://api-docs.nexusmods.com/)
- [`node-nexus-api` client docs](https://github.com/Nexus-Mods/node-nexus-api/blob/master/docs/classes/_nexus_.nexus.md)
- [Nexus Mods Terms of Service](https://help.nexusmods.com/article/18-terms-of-service)
- [Nexus Mods App — download/login FAQ](https://nexus-mods.github.io/NexusMods.App/users/faq/NexusModsDownloads/)
