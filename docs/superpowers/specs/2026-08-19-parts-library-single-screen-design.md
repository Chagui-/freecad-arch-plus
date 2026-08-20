# Parts Library: one screen, faster clicks, part families

Date: 2026-08-19

## Problem

Three complaints about the Parts Library panel, in the order they were raised:

1. **The grid lists parameter names that carry no information.** Each card
   shows a monospaced line of its primary parameter *labels* — `Width | Depth
   | Height` — with no values. It restates the column headings of a form the
   user has not opened yet.
2. **Clicking a part is slow.** Selecting a card rebuilds the part's geometry
   and re-renders a preview image that, at default parameters, is identical to
   the `thumbnail.jpg` already committed beside the part.
3. **The catalogue screen may not be worth its click.** The panel opens on a
   page of room cards listing element rows; the grid is one level down.

The library holds 31 parts across 6 rooms and 36 element rows. **25 of those
36 rows lead to exactly one part.** The catalogue screen is therefore mostly a
toll booth: two clicks to reach a single card.

## Goals

- One screen, opening directly onto parts.
- A card that aids recognition, not specification.
- Clicking a part at its default parameters costs no geometry work.
- A place for a part to say which collection it belongs to, so an
  `ikea-malm/` pack can sit beside `basic/` and be told apart.

## Non-goals

- Changing how parts are built, placed, or written to a document.
- Changing the facet vocabulary in `library/facets.json`.
- A live 3D preview. `pivy.quarter` remains unusable on FreeCAD 1.1 (Qt6 moved
  `QOpenGLWidget`), and the static image path stays the real one.
- Filtering by family. Deferred until a second collection exists.

## Evidence

Phase timings, measured in a live FreeCAD 1.1.1 GUI session over all 31 parts
with the shape cache cleared before each (simulating a first click), via the
`freecad` MCP server's `execute_code`:

| phase | total | avg/click | worst |
| --- | --- | --- | --- |
| `geometry.build_shape` | 8.19 s | 0.264 s | 0.703 s (vanity) |
| `geometry.measure` | 4.34 s | 0.140 s | 0.913 s (king-bed) |
| `thumbs.render_shape` | 2.82 s | 0.091 s | 0.272 s (curtain) |
| load rendered pixmap | 0.03 s | 0.001 s | — |
| **load committed `thumbnail.jpg`** | 0.03 s | **0.001 s** | — |

Average click 0.496 s; worst 1.76 s (king-bed).

Three distinct causes, none of which is the offscreen render:

- **`measure()` is computed for every part but read by four.**
  `_refreshPreview` always calls `paramForm.setDerived(geometry.measure(shape))`,
  and `setDerived` only writes into fields whose default is `"auto"`. Only
  `chest-of-drawers`, `gas-hob`, `sofa` and `television` declare one.
  `measure()` calls `Shape.optimalBoundingBox()`, which `geometry.py`'s own
  docstring records as costing "about as much as building the shape (330 ms of
  the king bed's 685 ms)". King-bed spends 0.913 s on a number that is then
  discarded. **4.34 s of the 15.38 s sweep is work nothing reads.**
- **Every selection recreates an image already on disk.** At default
  parameters the render reproduces `thumbnail.jpg` — the same file
  `ensure_thumbnail()` produced from the same resolved defaults. Loading it
  costs 1 ms; recreating it costs 0.496 s.
- **The search box has no debounce.** `search.textChanged` →
  `_repopulateGrid` → `setCurrentRow(0)` → `currentItemChanged` → `_onSelect`
  → `_refreshPreview`. Every keystroke rebuilds all 31 cards *and* runs the
  full pipeline against whatever the first match now is. Typing "cabinet" is
  seven keystrokes, roughly 3–4 s of blocked UI. The parameter form already
  debounces at 250 ms (`_paramTimer`); the search field never got one.

Note for future readers: `thumbs.py`'s comments describe a 17-second
`writeInventor` tessellation. That problem is fixed — tessellation now peaks
at 0.14 s, thanks to the shape-scaled `_DEVIATION_RATIO`. The comment is
history, and reading it as current is what first sent this design at the wrong
phase.

## Design

### 1. One screen

`PartsLibraryPanel` loses its top-level `QStackedWidget` and its
"categories" screen. What remains is a single column:

```
[ All · 31 ] [ 🛁 Bathroom · 8 ] [ 🛏 Bedroom · 10 ] [ 🍽 Dining · 2 ]
[ 🍳 Kitchen · 6 ] [ 🛋 Living · 8 ] [ 💼 Office · 2 ]
[ Search…                                                          ]
┌─────────────────────────────────┬──────────────────────┐
│ card grid (or empty state)      │ detail sidebar       │
└─────────────────────────────────┴──────────────────────┘
```

- **Chips** are one flow-wrapped row of exclusive toggle buttons. `All` comes
  first and is selected on open. Each chip carries the room's existing facet
  SVG from `resources/icons/facets/` and its part count.
- Selecting a chip sets `self._filterRoom` and repopulates the grid. Search
  narrows within the selected chip.
- **`element` stops being a navigation level.** It stays in `part.json`,
  keeps feeding `index.search()` and the IFC type mapping in `manifest.py`,
  and is simply not clickable. With 25 of 36 element rows holding one part,
  the level does not currently earn a control.
- The breadcrumb is deleted: the selected chip is the breadcrumb.
- **Wrapping**: a `QHBoxLayout` cannot wrap, so the chip row uses a small
  `FlowLayout` — Qt's canonical ~40-line `QLayout` subclass, added to
  `archplus/common/widgets.py`. It reflows itself from `heightForWidth`, so
  nothing needs to watch resize events. Six rooms fit one line at any
  realistic panel width; the wrap is for growth.
- **The chip data** comes from a new `index.facet_groups(entries, facets,
  facet="room")`, returning `[{value, label, icon, count}]` — the primary half
  of today's `category_tree` without the `children` the chips cannot use.
  `category_tree` loses its only caller and is deleted along with the screen
  it served; its tests move to `facet_groups`.

Deleted with the screen: `_buildCategoriesScreen`, `_populateCategories`,
`_fillCategoriesEmptyState`, `_makeRoomCard`, `_reflowCategories`,
`_columnCountFor`, `eventFilter`, `_showCategories`, `_updateBreadcrumb`,
`_addBreadcrumbSegment`, `_addBreadcrumbSeparator`, `_roomLabel`,
`_elementLabel`, `index.category_tree`, and the `_categoriesStack` /
`_categoryCards` / `_categoryColumns` / `_CARD_TARGET_WIDTH` state.
`_showResults` is not deleted but reduced to `_onChipSelected(room)`, which
sets `self._filterRoom` and repopulates. Roughly 250 lines net.

The card grid keeps `QListWidget` in `IconMode`, which reflows on its own —
which is why the hand-rolled reflow machinery above can go rather than being
ported to the chip row wholesale.

### 2. Card content

A card is **thumbnail, name, and family**:

- The monospaced parameter-label line is removed outright. Nothing replaces
  it. A card's job here is recognition; the thumbnail does that, and the
  detail pane states dimensions properly, as editable fields.
- The **family** line renders under the name, dimmed and one point smaller,
  whenever the part's collection declares a `label`. A part whose collection
  declares none has no family line and a correspondingly shorter card.
- The detail sidebar shows the same family as a dim line under the part name.
- The family label joins `index.search()`'s haystack, so typing "malm" finds
  the collection's parts.

### 3. Collections

A new optional `collection.json` sits in a collection folder, one level above
the parts, mirroring how `library/facets.json` sits at the library root:

```
library/
  facets.json
  basic/
    collection.json          { "schema": 1, "description": "…" }
    armchair/  part.json  builder.py  thumbnail.jpg
    …
  ikea-malm/
    collection.json          { "schema": 1, "label": "IKEA Malm",
                               "description": "…" }
    malm-6-drawer-chest/  part.json  …
```

Fields:

| field | required | meaning |
| --- | --- | --- |
| `schema` | no | Version gate; `1`. Absent is accepted, matching `part.json`. |
| `label` | no | Display name. **Present → cards show the family line. Absent → they do not.** Free text, so "IKEA" keeps its capitalisation. |
| `description` | no | One line. Tooltip on the family line, and a dim line in the detail pane. |

- **`basic/` ships a `collection.json` with a `description` and no `label`.**
  Every collection is therefore defined and documented, and the 31 existing
  parts show no family line — an identical "Basic" on all 31 cards would
  repeat exactly the low-information mistake the parameter line is being
  removed for. An unlabelled collection means "these parts belong to no
  brand".
- **Resolution**: a part's collection is the nearest ancestor directory
  containing a `collection.json`, searching upward and stopping at the library
  root. Both `library/ikea-malm/…` and `library/ikea/malm/…` therefore work. A
  part with no such ancestor has no family.
- **No effect on part ids.** The id stays the folder path relative to the
  library (`basic/armchair`), so nothing existing changes.
- Deliberately excluded: `version`, `icon`, `url`, and `attribution` /
  `license`. Attribution is a real question once third-party geometry packs
  land, but there is nowhere in the UI to show it, and a field nothing reads
  is a field that goes stale.

### 4. Preview speed

Three independent changes.

**4a. Measure only when a derived field is waiting for it.**
`ParamForm` grows `hasDerivedFields()`, returning `bool(self._auto)` — true
only while some field still shows a derived value. `_refreshPreview` calls
`geometry.measure()` only when it is true. This shrinks a sweep from 15.38 s
to about 11.3 s and takes 0.913 s off king-bed, on the edited-parameter path
as much as on selection.

**4b. At default parameters, serve the committed thumbnail.**
`ParamForm` grows `isPristine()` — set true by `setSpecs`, set false by
`_onEdited`. `setDerived` deliberately does not emit `changed`, so derived
values arriving do not dirty the form; `reset()` calls `setSpecs` and so
restores pristine, which correctly returns the pane to the default thumbnail.

Comparing parameter *values* against the manifest defaults would be the wrong
test: `setDerived` writes measured numbers into the auto fields moments after
selection, and those fields would then read as edited.

`_refreshPreview` becomes:

| state | build | measure | render | preview shown |
| --- | --- | --- | --- | --- |
| pristine, no derived fields (27 of 31) | — | — | — | `thumbnail.jpg` |
| pristine, derived fields (4 of 31) | yes | yes | — | `thumbnail.jpg` |
| edited | yes | if derived | yes | `_PREVIEW_CACHE` as today |

A pristine part with derived fields still builds and measures, because its
Width/Height genuinely cannot be known without the shape. Worst case is
chest-of-drawers at 0.65 s, cached for the session thereafter. This is
accepted rather than eliminated: at four parts and under a second, a committed
measurements sidecar would add a second generated file per part that can go
stale against an edited builder, for a saving nobody would feel.

**Falling back.** No committed thumbnail — a user-added part — drops through
to today's build-and-render path, which writes the jpg. Slow exactly once,
fast forever after. The `_prerenderThumbnails` progress dialog is untouched.

**Build errors stay visible.** A part that cannot build cannot have had a
thumbnail rendered either, so it lands in the fallback path and reports
"Cannot build this part: …" exactly as now. The invariant holds itself. The
residual case — a committed thumbnail whose builder later broke — shows a
stale image until the user edits a parameter or places the part, and "Rescan
library" clears it.

**4c. Debounce the search box.**
`search.textChanged` starts a single-shot 250 ms timer rather than calling
`_repopulateGrid` directly, reusing the interval the parameter form already
uses. Combined with 4b, a keystroke costs a grid rebuild and a 1 ms file read
instead of a full geometry pipeline.

Expected result: a sweep of all 31 parts falls from **15.38 s to about
1.68 s**, effectively all of it the four parts with derived fields.

### 5. Module structure

`gui.py` is 1436 lines. Section 1 removes roughly 250. One module comes out
rather than letting it grow back:

- **`collection.py`** (new, ~60 lines) — loads and validates
  `collection.json`, and resolves a part directory to its nearest-ancestor
  collection. Free of FreeCAD, Part and PySide imports, exactly as `index.py`
  and `manifest.py` are, so it unit-tests headlessly.

`index.scan()` calls it once per part and stores `family` (the label, or
`None`) and `familyDescription` on each entry, so the cached index carries
them and the panel never walks the filesystem while browsing.

## Data model changes

- `index.py`: entries gain `family` and `familyDescription`. `CACHE_VERSION`
  goes 2 → 3, so a stale v2 cache is refused rather than handing the panel a
  missing key — the same reasoning that took it 1 → 2 when `variants` became
  `params`.
- `is_cache_valid()` must also invalidate on a changed, added or removed
  `collection.json`, not only `part.json` and `facets.json`. Otherwise editing
  a collection label appears to do nothing until something else changes.

## Error handling

| condition | behaviour |
| --- | --- |
| `collection.json` is malformed JSON | Scan error naming the file, as `facets.json` does today. The collection's parts still appear, without a family. A bad collection must never hide parts. |
| `collection.json` has no `label` | Not an error, not a warning. Parts show no family line. This is `basic/`'s normal state. |
| `label` is not a string | Scan error naming the file; parts appear without a family. |
| Two `collection.json` files on one path | Nearest ancestor wins. Not an error. |
| Facet SVG for a room is missing | Chip renders with no icon, as `_facetIconPath` already degrades. |
| A part matches no room facet | Falls in `index.UNCLASSIFIED`, which already has a chip. |

## Testing

Following the existing suite's split — logic headless, widgets against the
bundled PySide6 offscreen.

Headless (`conftest.py` fakes PySide):

- `tests/test_partslib_collection.py` (new) — nearest-ancestor resolution,
  including nested collections and a part with none; `label` optional;
  malformed JSON produces an error rather than raising; a non-string `label`
  is an error.
- `test_partslib_index.py` — entries carry `family` / `familyDescription`; a
  changed `collection.json` invalidates the cache; a v2 cache on disk is
  refused; the family label is searchable; `facet_groups` returns one group
  per declared room with correct labels, icons and distinct-part counts
  (inherited from the `category_tree` tests it replaces).

Widget tests (offscreen PySide6):

- `test_partslib_paramform.py` — `isPristine()` is true after `setSpecs`,
  false after a user edit, still true after `setDerived`, and true again after
  `reset()`; `hasDerivedFields()` tracks `_auto`.
- `test_partslib_thumbs.py` — the pristine path loads `thumbnail.jpg` and does
  not call `render_shape`; a part with no derived fields does not call
  `measure`; the edited path calls both.
- `test_widgets.py` (or a new panel test) — chips are built one per room plus
  `All`, with counts; selecting a chip filters the grid; a card has no
  parameter-label line; the family line is present for a labelled collection
  and absent for an unlabelled one; typing in search does not fire a preview
  before the debounce elapses.

## Migration

- No user-visible data migrates. Existing `part.json` files are untouched.
- The index cache self-invalidates through `CACHE_VERSION`.
- Adding `library/basic/collection.json` is the only content change.
- `docs/PARTS-LIBRARY-VERIFICATION.md` and the README's parts-library section
  need updating for the single screen and for `collection.json`.

## Out of scope

- Filtering by family, and a second chip row for `element`. Both become easy
  once a second collection exists; neither is justified at 31 parts in one
  collection.
- A committed measurements sidecar (see 4b).
- `attribution` / `license` on a collection (see 3).
