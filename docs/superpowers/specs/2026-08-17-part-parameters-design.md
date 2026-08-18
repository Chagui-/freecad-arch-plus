# Part parameters: replacing `variants` with per-part declared parameters

Status: approved design, not yet implemented
Supersedes: §5.3 ("Variants") of `2026-08-15-parts-library-design.md`

## 1. Problem

`variants` is one flat list doing two incompatible jobs.

A variant is meant to name a *configuration*. In practice 16 of the 20 parts
that declare variants use it purely for *size*, 2 use it for configuration,
and 2 mash both axes into one list. The mashing produces cherry-picked cells
out of a grid that is never written down:

    television      55" on stand │ 55" wall-mounted │ 65" wall-mounted
                                                       65" on stand is absent
    shower-screen   Bath screen │ Walk-in 900 mm │ Walk-in 1200 mm
                      the "bath" type got no size range at all

Two axes, one list. Every new size doubles the entries, so the author stops
enumerating and picks the combinations they happened to need.

The second problem is coupling. Only 2 of 20 parts vary a single parameter
across all their variants. The other 18 set a size *and* a coupled count:

    base-cabinet   600 mm → Width=600, DoorCount=1
                   800 mm → Width=800, DoorCount=2
    sofa           2-seat → Width, SeatCount
    gas-hob        4 burner → Width, BurnerCount

"An 800 mm cabinet has two doors" is design knowledge hardcoded into the
manifest. A naive width axis that set only `Width` would leave the door count
wrong for 18 parts.

## 2. Approach

Delete `variants`. Parts declare their own parameters; the browser panel
exposes them; coupled values are derived by the part's builder.

`SCHEMA_VERSION` stays 1 — nothing has been released publicly, so this is a
clean break rather than a migration.

## 3. The `params` block

`variants` is removed from `KNOWN_FIELDS`. A manifest that still declares it
is a hard validation error, not a warning: `index.scan()` excludes erroring
manifests and reports them, whereas a warning would let a stale part place
with silently wrong defaults.

`params` gains four optional keys. The block below is an illustrative
composite, not a real part — it borrows `base-cabinet`'s dimensions and
`television`'s `Mounting` choice to show every key in one place:

```jsonc
"params": {
  "Width":     { "type": "Length",  "default": 600,     "ui": "primary" },
  "Depth":     { "type": "Length",  "default": 600,     "ui": "primary" },
  "Height":    { "type": "Length",  "default": 900,     "ui": "primary" },
  "DoorCount": { "type": "Integer", "default": "auto",  "label": "Doors" },
  "KickHeight":{ "type": "Length",  "default": 100 },
  "Mounting":  { "type": "Choice",  "default": "stand", "ui": "primary",
                 "options": {
                   "stand": { "label": "On stand",
                              "placement": {"host":"floor","offset":0} },
                   "wall":  { "label": "Wall-mounted",
                              "placement": {"host":"wall","offset":1100} }
                 } }
}
```

| key | meaning |
|---|---|
| `ui` | `"primary"` puts the param in the browser panel's top row. Absent ⇒ inside the "More parameters" expander. |
| `label` | Display name only. The key remains the builder argument and the FreeCAD property name — the same `id`-vs-`name` split facets already use. |
| `default: "auto"` | The builder derives the value. Legal on `Integer` and `Length` only. |
| `options` | `Choice` only. Ordered map of stable value → `{label, placement?}`. A selected option's `placement` merges per key over the part's own. |

Supporting rules:

- **Order** is manifest key order (JSON object order, which Python preserves).
  Authoring order is UI order, so the content pass reorders keys.
- **Fallback**: a part marking no `ui: "primary"` gets its first three declared
  params as primary, so a panel is never empty.

**Param names are open.** There is no vocabulary and none is introduced: a new
part invents whatever params it needs, and the only requirement is that its
builder reads them. This is the deliberate opposite of facets, which *are* a
closed vocabulary in `facets.json` — facets are how parts are found, so they
must agree across the catalogue; params are how one part is shaped, which is
nobody else's business.

The one closed set is `type`, because each value maps to a FreeCAD property
class:

    Length → App::PropertyLength     Integer → App::PropertyInteger
    Angle  → App::PropertyAngle      Bool    → App::PropertyBool
    String → App::PropertyString     Choice  → App::PropertyEnumeration  (new)

`Choice` becomes expressible precisely because `options` now exists; today
`object.py` refuses `Enum` for want of a way to declare allowed values.

Explicitly **not** added: `min`/`max`/`step`, units other than mm, conditional
visibility between params. Nothing in the 31 shipped parts needs them.

## 4. Resolution and the builder contract

`manifest.py` loses `resolve_variant`, `variant_labels` and
`DEFAULT_VARIANT_LABEL`, and gains:

| function | returns |
|---|---|
| `param_specs(manifest)` | the `params` block, without the old variant merge |
| `primary_params(manifest)` | ordered names where `ui == "primary"`, else the first three declared |
| `merge_params(manifest, overrides)` | `{name: value}`; an `"auto"` default resolves to `None`; an override wins when present; an undeclared override is still dropped |
| `resolve_placement(manifest, params)` | base `placement`, then each `Choice` param's selected option's `placement` merged over it per key, in declared order |

`ifcProperties` merging disappears with variants — a part declares one block.
No shipped part varied it.

`geometry.build_shape(manifest, part_dir, overrides)` renames its first
parameter from `resolved` to `manifest` — there is no longer a resolved
variant, only the manifest — and drops the `variantLabel` component of its
cache key. `select_builder(resolved, part_dir)`, whose first argument is
already documented as retained-but-unread, is renamed to match. Auto params enter
the key as `None`, which is correct: a pinned 800 and an auto value that
computes to 800 are different objects to the user, and keying them apart costs
nothing.

**The builder contract changes.** Today builders write:

```python
door_count = max(int(params.get("DoorCount", 1)), 0)      # default never fires
```

The key is now always present, so `.get`'s default is dead and `int(None)`
raises. Coupled builders derive explicitly instead — this is the design
knowledge moving out of the manifest and into code:

```python
width = float(params["Width"])
door_count = params.get("DoorCount")
if door_count is None:
    door_count = 2 if width >= 700 else 1                 # the rule, stated once
door_count = max(int(door_count), 0)
```

Each part's builder is its own `library/basic/<part>/builder.py`, discovered
by file presence (`geometry.select_builder`), so there is no registry to
update — the change is local to the twelve parts that need it. README §2b
("Write a builder") and the `build_shape` docstring gain the rule: a declared
param may arrive as `None`, meaning derive it.

`index.py` entries drop `"variants"` and carry the whole `params` block, so the
grid renders without opening every manifest. `CACHE_VERSION` → 2: the entry
shape changed, and a stale cache would otherwise hand the panel a `variants`
key that no longer exists.

## 5. The document object

`PROP_VARIANT` and every enumeration-juggling path in `makePart()` and
`reloadFromLibrary()` are deleted (roughly 40 lines of "does FreeCAD fire
onChanged when reassigning an enum" defensiveness). A legacy object still
carrying a `Variant` property keeps it — removing a document property is
destructive — but it is hidden with `setEditorMode(..., 2)` so it cannot be
mistaken for live.

**`Choice` → `App::PropertyEnumeration`.** The enumeration list holds the
option *labels*, which is what the user should see in the property editor. The
stable value is recovered by label lookup, falling back to option index, so
renaming a label does not orphan a saved object.

**Auto/pinned state** lives in one hidden `App::PropertyStringList`,
`AutoParams`, naming the params still deriving:

- Seeded from the manifest on insert and on reload.
- `execute()` sends only *pinned* params as overrides; the rest reach the
  builder as `None`.
- After building, derived values are written back into their properties under
  the existing `self._reseeding` guard, so the editor shows `Doors: 2` rather
  than a meaningless `0`.
- `onChanged(prop)` for a param in `AutoParams`, outside reseeding, removes it
  from the list — editing a derived field is what pins it. Reload restores the
  full auto list.

Rejected alternative: a sentinel value (`-1` for Integer, `0` for Length). No
new property, but it puts `Doors: -1` in front of the user and collides with
`ShelfCount: 0`, which is meaningful.

Accepted consequence: once pinned, a param stays pinned until "Reload from
library". There is no per-field un-pin.

## 6. The browser panel

The chip and combo machinery (`_setVariantChips`, `_onVariantChanged`,
`variantGroup`, `variantCombo`, `MAX_VARIANT_CHIPS`, `_sanitizeVariantLabel`)
is deleted and replaced by a param form. `gui.py` is already 1456 lines, so the
Qt glue lands in a new `paramform.py` (~150 lines): build a widget per param
spec, read values back, apply auto styling. Every *decision* it needs — which
params are primary, in what order, which are auto — comes from the pure
`manifest.py` functions in §4, which are the testable half; the conftest fakes
PySide, so Qt itself is not unit-testable here.

Widgets by type:

    Length/Angle → QDoubleSpinBox (mm / ° suffix)   Integer → QSpinBox
    Bool         → QCheckBox                        String  → QLineEdit
    Choice       → QComboBox of option labels

Layout, replacing the chip row:

    Width  [ 800 ] mm    Depth [ 600 ] mm    Height [ 900 ] mm
    ▸ More parameters (3)                                 Reset

- Auto fields render dim/italic showing the derived value; the first edit pins
  them and they take normal styling.
- **Reset** returns every field to manifest defaults, and is also the only way
  back to auto — the same one-way rule as the inserted object (§5), so panel
  and property editor behave identically.
- The expander is collapsed by default and remembers its state for the session.

**Rebuild debounce.** Every edit re-runs `build_shape` for the preview and the
W/D/H readout. A `QTimer` fires 250 ms after the last keystroke so dragging a
spinbox does not queue a dozen OCC builds; the existing session shape cache
absorbs the repeats.

**Grid card.** The monospace variants line (`800 mm  1200 mm`) becomes the
primary param labels — `Width · Depth · Height` — dimmed, in the same slot. It
advertises what the part is adjustable *by*, which is what the variant line was
really communicating.

**Thumbnail cache.** `.cache/<sanitized-variant>.jpg` becomes
`.cache/<12-hex-of-param-hash>.jpg`. Grid fallbacks render from manifest
defaults with auto resolved.

**Place in 3D view** takes host and offset from
`resolve_placement(manifest, params)`, so choosing "Wall-mounted" changes
hosting at placement time.

## 7. Content migration

Direction rule: **the axis the variant labels named becomes the driver; the
coupled value becomes `"auto"`.** "3 drawers" meant drawers were the chooser,
so `Height` follows. "800 mm" meant width was the chooser, so `DoorCount`
follows.

Primary rule: **a count is primary when it is the driver, not when it is
derived.** `SeatCount`/`DrawerCount`/`BurnerCount` stay in the top row; the
values that follow from them do not.

| part | primary | `"auto"` (derived from) | new `Choice` |
|---|---|---|---|
| base-cabinet | Width, Depth, Height | DoorCount ← Width | |
| wall-cabinet | Width, Height, Depth | DoorCount ← Width | |
| wardrobe | Width, Height, Depth | DoorCount ← Width | |
| gas-hob | BurnerCount, Width, Depth | Width ← BurnerCount | |
| vanity | Width, Depth | BasinWidth ← Width | |
| sofa | SeatCount, Width, Depth | Width ← SeatCount | |
| dining-table | Width, Depth | SeatCount ← Width, Depth | |
| chest-of-drawers | DrawerCount, Width, Depth, Height | Height ← DrawerCount | |
| bookcase | Width, Height, Depth | ShelfCount ← Height | |
| media-unit | Width, Height, Depth | ShelfCount ← Width | |
| curtain | Width, Height | FoldCount ← Width | |
| television | ScreenSize, Mounting | Width, Height ← ScreenSize | Mounting {stand \| wall} |
| shower-screen | Width, Height | | |
| mirror, coffee-table, nightstand, side-table, desk, bathtub, shower-base | their W/D/H | | |

Three parts (gas-hob, sofa, chest-of-drawers) keep a driver count *and* the
dimension it derives in the primary row. That is the greyed-derived-field case
working as intended: pick "3-seat", see Width greyed at 1900, pin it to 1850 if
you want.

Notes on the structurally interesting rows:

- **television** gains `ScreenSize`, an `Integer` in inches because `Length` is
  mm-only. `Width` and `Height` derive from it at 16:9 plus a bezel allowance
  (55 → 1230 × 710, matching today's numbers). A TV is chosen by diagonal,
  never by millimetre width. The missing "65 on stand" cell cannot exist,
  because there is no grid.
- **shower-screen**: "Bath screen" was a size (800 × 1400), not a type. It
  becomes those two numbers, and every bath-screen width becomes reachable. No
  `Choice` is needed — all three old variants shared floor hosting.
- **dining-table** flips direction: Width and Depth are primary, so `SeatCount`
  is the derived one. A 1800 × 900 table reports 6 seats, rather than a
  "6-seat" preset dictating 1800 × 900.

The other 11 parts declare no variants and need only `ui: "primary"` marks plus
key reordering.

**Builders touched (12)**, each at `library/basic/<part>/builder.py`:
`base-cabinet`, `wall-cabinet`, `gas-hob`, `wardrobe`, `sofa`,
`dining-table`, `bookcase`, `media-unit`, `chest-of-drawers`, `curtain`,
`television`, `vanity`. Each gains one `if params.get(X) is None:`
derivation, stated once, replacing the dead `.get(name, default)` fallback.

## 8. Testing

The pure modules stay FreeCAD-free and carry the load.

`test_partslib_manifest.py`
- `primary_params`, including the first-three fallback
- `merge_params` turning an `"auto"` default into `None`, an override beating
  it, and an undeclared override still being dropped
- `resolve_placement` merging a `Choice` option's block per key over the part's
- a manifest declaring `variants` failing validation

`test_partslib_index.py`
- entries carry `params` and no `variants`
- a `CACHE_VERSION` 1 cache on disk is rejected rather than half-read

`test_partslib_geometry.py`
- the cache key no longer contains a variant label
- a pinned value and an auto param computing the same number key differently

`test_library_content.py` — guards the real catalogue, and is where the
regressions are pinned:
- every part builds at its declared defaults with **no overrides**, so every
  `"auto"` param proves its builder derives it (a builder that forgot hits
  `int(None)` and fails loudly here)
- every part builds at each `Choice` option
- every part declares at least one param, and every `ui: "primary"` name exists
  in `params`
- no shipped manifest declares `variants`
- **the two diagnostic symptoms, as named tests**: `television` at ScreenSize
  65 + Mounting `stand` builds; `shower-screen` builds at 800 × 1400 and at
  1200 × 1400 (a bath-width screen at walk-in height — previously unreachable)

Not unit-testable, as today: `object.py` (imports FreeCAD at module scope) and
the Qt form. The mitigation is keeping every decision they make in the pure
modules, so what remains is property plumbing.

## 9. Docs

- `2026-08-15-parts-library-design.md` §5.3 and its `variants` schema row get an
  amendment note pointing here, rather than being silently rewritten.
- `docs/PARTS-LIBRARY-VERIFICATION.md` replaces its variant-switching steps with
  param-editing ones.
- `README.md` §2a (the manifest reference) documents `ui`, `label`,
  `default: "auto"` and `options`, and drops `variants`; §2b documents that a
  param may arrive as `None`.
