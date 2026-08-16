# Manifest schema v1

The manifest is the **deterministic** half of the design. Everything in it is pinned; nothing
in it is a judgement call the agent gets to make. If the agent finds itself wanting to change
a value here, that is a bug report against the manifest, not a decision to take.

Format is **YAML**, because a human maintains this list by hand and a diff of it should be
readable. One file per recipe: `recipes/<game>/manifest.yaml`.

---

## Top level

```yaml
schema: 1
game: {...}      # what this recipe targets
tools: [...]     # non-mod infrastructure (MO2, script extender)
mods: [...]      # the list
order: {...}     # conflict winners and plugin load order
```

## `game`

```yaml
game:
  id: fo4vr                    # recipe dir name, and the core's platform key
  name: Fallout 4 VR
  mo2GameName: Fallout 4 VR    # the exact string MO2 wants in ModOrganizer.ini
  nexusDomain: fallout4        # FO4VR mods live under the fallout4 domain
  steamAppId: 611660
  runtime: "1.2.72"            # game exe version this recipe is pinned against
  dlcRequired: false
```

`runtime` is a **hard gate**. Script-extender plugins are compiled against one runtime; a
mismatch is the single most common cause of "it launches and no mods load." The agent checks
the real `Fallout4VR.exe` version against this before doing anything else.

`nexusDomain` differing from `id` is not a typo — FO4VR has no Nexus domain of its own.

## `mods[]`

```yaml
- id: vr-address-library          # our stable slug; never changes, even if the mod is renamed
  name: VR Address Library for F4SEVR   # becomes mods/<name>/ in MO2 — display name
  why: >                          # REQUIRED. one line. see below
    Lets F4SEVR plugins resolve engine addresses by ID instead of hardcoded offsets.
  tier: foundation                # foundation | fix | performance | candidate
  required: true                  # false = agent may skip if it fails
  enabled: true                   # false = installed but left off (staged mods)

  source:
    type: nexus                   # nexus | github | http
    modId: 64879
    fileId: null                  # PIN — the exact uploaded file
    version: "1.7.0"

  file:
    name: null                    # expected archive filename
    sha256: null                  # PIN — hashed from our own bytes after download
    size: null

  install:
    root: data                    # where the archive's root maps to. see below
    strip: 0                      # leading path components to drop

  plugins: []                     # esm/esp/esl this mod contributes, if any

  verify:                         # files that must exist post-install, Data-relative
    - F4SE/Plugins/version-1-2-72-0.bin
```

### `why` is mandatory

Open question #3 asked whether to record why a mod is in the list. **Yes, and enforce it in
CI.** When a pin dies in eighteen months, the maintainer needs to know what the entry was
*for* to judge a replacement. One line, present tense, describing the defect it fixes — not
"good mod."

It doubles as the exclusion-rule audit: an entry whose `why` cannot be written without the
words "nicer," "better looking," or "I prefer" does not belong here (open question #4).

### `source.type`

| Type | Fields | Notes |
|---|---|---|
| `nexus` | `modId`, `fileId`, `version` | `(modId, fileId)` is MO2's own pin — see [`MO2_PORTABLE.md §6`](MO2_PORTABLE.md) |
| `github` | `repo`, `tag`, `asset` | No auth, no rate limit worth worrying about |
| `http` | `url` | For silverlock and similar. Pin the hash hard; there is no version API to fall back on |

### `install.root`

Most mod archives are already Data-relative and want `root: data`. The exceptions matter:

| Value | Meaning | Example |
|---|---|---|
| `data` | Archive root = `Data/`. Extract into `mods/<name>/`. | Most mods |
| `game` | Extract into the **game directory**, not the instance. | F4SEVR, vrperfkit — these load before usvfs exists |
| `fomod` | Archive has a FOMOD installer; needs `fomodChoices`. | See below |

`root: game` is the leaky one. Those files sit outside MO2's virtual filesystem, so they are
**not** removed when the instance is deleted, and they are the one place the recipe mutates
the user's game install. Every such entry needs an uninstall note.

### FOMOD

Where an archive ships an installer, choices are recorded as data rather than left to the
agent:

```yaml
install:
  root: fomod
  fomodChoices:
    "Choose your version": "VR"
    "Optional extras": []
```

This keeps a judgement call out of the agent's hands. Wrong FOMOD choices produce a build
that installs cleanly and misbehaves later — exactly the failure class the deterministic half
exists to prevent.

## `order`

```yaml
order:
  # MO2 modlist.txt, WINNER FIRST. the writer reverses this — see MO2_PORTABLE.md §4.
  install:
    - vr-address-library
    - buffout-4-ng-vr
    ...

  # plugins.txt / loadorder.txt. masters first.
  plugins:
    - Fallout4.esm
    - Fallout4_VR.esm
    ...
```

`order.install` lists **our slugs**, winner first, and the writer flips it into `modlist.txt`'s
bottom-up form. Writing it winner-first in the manifest is the readable direction; leaving the
reversal to one tested function is the safe one.

**Which mods must appear:** every mod with `install.root` of `data` or `fomod`, because those
are the ones MO2 virtualises and therefore the ones that can conflict. Mods with
`install.root: game` (F4SEVR, vrperfkit, the preloader) live outside usvfs, never appear in
`modlist.txt`, and are correctly absent here. `tier: candidate` entries are absent too — they
are not installed until adjudicated.

Any *virtualised* slug missing from `order.install` is a CI error. Silent append-to-end is how
a conflict winner changes without anyone noticing.

---

## Pins, and what to do when one is null

**`fileId` and `sha256` are the pin.** `version` alone is not: authors re-upload under the
same version string, and a hash is the only thing that distinguishes the file that was tested
from the file that is there now.

A `null` pin means **unverified, not optional.** The seed list ships with nulls because
resolving them requires live API calls that have not been made yet. The agent's rule:

- **`fileId: null`** → resolve from `version` via the API, report exactly what it resolved to,
  and **do not silently write it back**. A human confirms and commits the pin.
- **`sha256: null`** → download, hash, print. Same: proposed, not adopted.
- **Pin present but does not match** → **hard fail.** Do not substitute, do not pick the
  nearest version, do not "helpfully" continue. Open question #3 asked hard-fail versus
  agent-judged substitution; hard fail is the answer, because substitution is precisely where
  a well-meaning model invents a build that dies three hours in.

The asymmetry is deliberate: an *absent* pin is a known gap the agent may help close under
supervision. A *violated* pin is evidence the world moved, and the only safe response is to
stop and say so.

## CI

Cheap checks that pay for themselves (open question #3):

- every mod has a non-empty `why`
- every mod appears exactly once in `order.install`
- every `source` resolves — link still alive, `fileId` still present on the mod page
- no duplicate `id` or `name`
- `runtime` still matches the current live game version (a warning, not a failure — it means
  a game update landed and the recipe needs a look)
