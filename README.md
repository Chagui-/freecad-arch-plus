# ArchPlus

A FreeCAD add-on that extends the built-in **BIM** workbench with enhanced
Arch tools. It adds an **ArchPlus** toolbar and menu inside the BIM workbench.

It currently provides enhanced parametric **Stairs**, **Doors**, and **Windows**
tools, plus a **Parts Library** for inserting catalog furnishings. Each
geometry engine for Stairs, Doors and Windows is a modifiable copy of a native
FreeCAD module — `ArchStairs` for stairs and `ArchWindow` for doors and
windows — so every native feature (IFC export, hosting/opening cuts, presets,
…) is preserved while new behaviour is added on top, without affecting the
built-in tools. The Parts Library is different in kind: it is a content
library and browser rather than a modified copy of a native Arch module,
inserting single lightweight objects built from bundled part definitions.

<img src="docs/images/toolbar.jpg" alt="The ArchPlus toolbar in the BIM workbench" height="50">

## Features (Stairs)


- **Configuration dialog** (Task panel) with **live preview** — the stair
  renders in the 3D view as you change values, and updates as you edit.
- **Double-click to edit** an existing stairs object, reusing the panel.
- **Comfort note** — live riser/tread readout and Blondel ratio (2R + T) check.
- **Configurable landing position** — `LandingStep` places the landing/turn on
  any step (0 = auto, centered) instead of always at the middle.
- **Half- and quarter-turn winders** — a turn is built from winder (wedge)
  steps that sweep 180° (half) or 90° (quarter) while climbing, filling a
  square footprint. Set the turn to a single step for a flat landing instead.

<img src="docs/images/stairs_quarter_turn.jpg" alt="Quarter-turn stairs" width="100">

### Configuration dialog

<img src="docs/images/stairs_dialog_1.jpg" alt="Stairs configuration dialog" width="250">
<img src="docs/images/stairs_dialog_2.jpg" alt="Stairs configuration dialog with comfort note" width="250">

## Features (Doors)

- **Configuration dialog** (Task panel) with **live preview** — the door
  renders as you edit, and the host wall's opening re-cuts immediately.
- **Double-click** (or right-click → **Edit**) to reopen the panel on an
  existing door.
- **Operations** — Single/Double swing, Single/Double sliding, and
  Opening-only (a bare hole, no leaf).
- **Panel styles** — Solid or full Glass.
- **Swing controls** — hinge side and opening direction for hinged doors.
- **Opening animation** — a 0–100 % slider: swing leaves rotate about the
  hinge, sliding leaves slide aside.
- **Panel position** — place the leaf Centered (default), flush Front, or flush
  Back within the frame depth.
- **Height above wall base** — lift the door off the floor for a threshold or
  mid-wall placement (0 = sitting on the floor).
- **Opening symbols** — plan (swing arc) and elevation symbols, each
  toggleable (elevation off by default).
- **Mouse placement** — click a wall face and the door drops to the wall base
  (floor) automatically and centres on the cursor, so you only aim *along* the
  wall. A sill/threshold offset is available during placement.
- **Reposition with the mouse** — from the panel button or right-click →
  **Reposition**: pick a new spot; the door re-orients to the wall face you
  point at, re-snaps to the floor, and re-cuts the host wall.

<img src="docs/images/doors_double_swing.jpg" alt="Double-swing door hosted in a wall" width="100">

### Configuration dialog

<img src="docs/images/doors_dialog_1.jpg" alt="Doors configuration dialog" width="250">
<img src="docs/images/doors_dialog_2.jpg" alt="Doors configuration dialog with opening options" width="250">


## Features (Windows)

- **Configuration dialog** (Task panel) with **live preview** — the window
  renders as you edit, and the host wall's opening re-cuts immediately.
- **Double-click** (or right-click → **Edit**) to reopen the panel on an
  existing window.
- **Shapes** — Rectangular or **Round** (a circular oculus). A round window is
  fixed glass; its diameter follows the width.
- **Operations** — Fixed (no opening), Single casement, Single sliding, and
  Double casement (rectangular only).
- **Swing controls** — hinge side and opening direction for casement windows.
- **Opening animation** — a 0–100 % slider: casement sashes rotate about the
  hinge, sliding sashes slide aside.
- **Sash position** — set the sash flush to the Front/interior (default) or
  Back/exterior face within the frame depth (only matters when the sash is
  shallower than the frame).
- **Full 4-sided frame** — unlike doors (which sit on the floor and use a
  3-sided frame), windows get a frame on all four sides including the bottom
  sill jamb, since they sit in a wall opening.
- **Single undivided glass pane** per sash.
- **Opening symbols** — plan (swing arc) and elevation symbols, each
  toggleable (elevation off by default).
- **Mouse placement** — click a wall face and the window drops to a sill height
  (default 900 mm) above the wall base automatically and centres on the cursor,
  so you only aim *along* the wall. The sill height is adjustable during
  placement.
- **Reposition with the mouse** — from the panel button or right-click →
  **Reposition**: pick a new spot; the window re-orients to the wall face you
  point at, re-sets to the sill height, and re-cuts the host wall.
- **Flip without reopening** — right-click a casement window → **Invert Opening
  Direction** or **Invert Hinge Position** to mirror the swing in place.

## Features (Parts Library)

ArchPlus ships a starter catalogue of 31 parametric parts across Kitchen,
Dining Room, Bedroom, Living Room, Bath Room and Office,
alongside the faceted vocabulary (`archplus/tools/partslib/library/facets.json`) and the
browser/placement machinery. Parts are floor-, wall- or free-hosted, so
wall cabinets, mirrors and curtains position against a wall the way a
door does.
Add further part folders under `archplus/tools/partslib/library/` (each with its own `part.json`
manifest, validated against that vocabulary) to extend it; an empty result
set (e.g. after a search with no matches) shows a plain "nothing here yet"
message instead of a blank void.

- **Dockable browser** — click **Parts Library** to open a dock ("ArchPlus
  Library") that stays open across placements, so you can insert several
  parts in a row without reopening anything.
- **Faceted grouping** — group the catalog by `Function`, `Element` or
  `Room` via a **Group by** combo; the chosen facet persists across FreeCAD
  restarts.
- **Multi-valued facets** — a part can belong to several rooms at once (a WC
  under both Bathroom and Bedroom, for example) and appears under each
  group it declares.
- **Search** — a live search box filters the grid by name, keyword and
  description as you type.
- **Live preview with derived measurements** — selecting a part shows a 3D
  preview and a `W × D × H` readout measured from the built shape, never
  authored by hand, so the stated size can never disagree with the geometry.
- **Variants** — parts can declare named variants (e.g. cabinet widths);
  switching **Variant** in the detail pane or the property editor rebuilds
  the shape and measurements in place.
- **Host-aware click-to-place** — click **Place**, then click a floor or
  wall face: the part drops to the correct height for its declared host
  (e.g. a wall-hung WC lands at the wall base plus its mounting height) and
  orients to the face.
- **Single-object insertion, no tree pollution** — placing a part adds
  exactly one object with no children, and deleting it leaves the tree
  completely clean.
- **Reload from library** — right-click a placed part and choose **Reload
  from library** to re-read its manifest and rebuild it; opening or
  recomputing a document never silently rebuilds a part from a
  since-edited definition on its own.

## Installation

Clone (or copy) this repository into your FreeCAD user `Mod` folder:

- **Linux:** `~/.local/share/FreeCAD/Mod/ArchPlus` (or, for FreeCAD 1.1,
  `~/.config/FreeCAD/...`)
- **Windows (FreeCAD 1.1):**
  `%APPDATA%\FreeCAD\v1-1\Mod\ArchPlus`

The exact path is `FreeCAD.getUserAppDataDir()` + `Mod` (run it in FreeCAD's
Python console). Restart FreeCAD, switch to the **BIM** workbench, and use the
**ArchPlus** toolbar.

## Usage

BIM workbench → **ArchPlus** toolbar:

- **Stairs** → configure → **OK**. Double-click a stairs object to edit it.
- **Doors** → click a wall face to place → configure in the panel. Double-click
  (or right-click → Edit) a door to reopen the panel; right-click →
  **Reposition** to move it with the mouse.
- **Windows** → click a wall face to place (drops to a 900 mm sill height by
  default) → configure in the panel. Double-click (or right-click → Edit) a
  window to reopen the panel; right-click → **Reposition** to move it with the
  mouse.
- **Parts Library** → browse/group/search the catalog in the dock, select a
  part and variant, then click **Place** and click a floor or wall face to
  insert it. Right-click a placed part → **Reload from library** to refresh
  it from its manifest.

## Adding parts to the library

A part is a folder under `archplus/tools/partslib/library/<family>/<part>/`
containing a `part.json` manifest — e.g. all 31 shipped parts currently live
under one family, `basic/`. Unlike the old category folders this replaced,
the family level is not cosmetic: a family can hold a `_shared.py` with
massing reused by several of its parts (see 2b), and a part's id is derived
from its full path, e.g. `basic/mirror`. Parts are found by their manifest,
and grouped in the browser by the **facets** they declare — that grouping is
independent of the family folder a part happens to live in.

> **One-time break (2026-08-17).** Part ids are now derived from the folder
> path, so `mirror` became `basic/mirror`. A document saved before this keeps
> its geometry — the object holds its own cached shape and ArchPlus warns
> `part 'mirror' is not in the library` rather than touching it — but its
> Parameters stop being editable. Delete and re-place the part to get
> parametric editing back.

There are two ways to give a part its geometry, and only one of them involves
writing code:

| | Geometry from | Write Python? | Parametric |
| --- | --- | :-: | :-: |
| **Model file** | a `.step`/`.brep` you drop in the folder | no | no — fixed geometry |
| **Builder** | a Python function that computes the shape | yes | yes — any size |

Everything in the shipped library is a builder, because a generated cabinet
can be any width. Reach for a model file when the geometry is fixed anyway —
a manufacturer's download, or something too organic to describe in code.

### 1. Write the manifest

`archplus/tools/partslib/library/basic/my-stool/part.json`:

```json
{
  "schema": 1,
  "name": "Bar stool",
  "description": "Round stool with a footrest ring.",
  "keywords": ["stool", "bar", "seating"],
  "facets": {
    "function": "Seating",
    "element": "Chair",
    "room": ["Kitchen", "Dining"]
  },
  "params": {
    "Height": { "type": "Length", "default": 750 },
    "SeatDiameter": { "type": "Length", "default": 340 }
  },
  "placement": { "host": "floor", "offset": 0 },
  "geometry": {}
}
```

- `schema`, `name`, `facets` and `geometry` are required; the rest are
  optional. `id` is *not* one of them — it is derived from the part's folder
  path (`basic/my-stool` here). A manifest may still declare an `id` to pin
  identity across a later folder rename; when present it must be a
  lowercase, `/`-joined slug.
- Every facet value must already exist in `archplus/tools/partslib/library/facets.json` — an unknown
  one is a hard error, not a silent pass. `room` is multi-valued (a list);
  `function` and `element` take a single string.
- `params` become editable properties on the placed object. Types:
  `Length`, `Angle`, `Integer`, `Bool`, `String`.
- `placement.host` is one of `floor`, `wall`, `ceiling`, `free`, and
  `offset` is millimetres from that surface — e.g. a wall cabinet uses
  `{"host": "wall", "offset": 1500}` to hang at 1500 mm.
- `variants` (optional) is a list of `{"label": ..., "params": {...}}`.
  A variant may also override `assets`, `ifcProperties` and `placement`, so
  a TV on a stand and the same TV on a bracket can be one catalogue entry
  with two hosts. Parts with one variant show no variant control, two show
  chips, three or more show a dropdown.

### 2a. Geometry from a model file (no code)

Drop the file in the part's own folder and leave the part with no
`builder.py`. No Python, no new module — the missing file is what tells
ArchPlus to fall back to the stock asset builder, which reads
`geometry.assets`:

```
archplus/tools/partslib/library/geberit-icon/
  part.json
  geberit-icon.step        # or .brep — as downloaded
  .cache/                  # generated on first load, gitignored
```

A purchased single model like this has no family of its own, so it sits
directly under `library/` rather than inside one — the standalone case.

```json
"geometry": {
  "assets": { "body": "geberit-icon.step" },
  "transform": { "rotate": [90, 0, 0], "anchor": "back-bottom-center" }
}
```

- `assets` maps a name to a file **inside the part's own folder**. An absolute
  path, or one containing `..`, is rejected — a manifest is data and must not
  be able to reach arbitrary files.
- `asset.single` expects the name `body`. That is its whole contract.
- A `.step` is parsed once and cached beside it as `.cache/<name>.brep`;
  later loads read the cache, which skips STEP translation entirely. The
  cache is gitignored and regenerates itself, so never commit it.

`transform` is what makes a vendor file usable. Downloads arrive at whatever
origin and orientation the vendor chose, and the browser measures `W × D × H`
from the built shape — so an un-normalised part reports nonsense and lands in
the wrong place:

- `unitScale` — multiply if the file is not in millimetres.
- `rotate` — `[x, y, z]` degrees, applied after scaling. Get the part to
  ArchPlus axes: X width, Y depth with the back at +Y, Z up.
- `anchor` — moves a named point of the bounding box to the origin, applied
  last. One of `origin`, `center`, `bottom-center`, `top-center`,
  `back-bottom-center`, `front-bottom-center`, `back-center`, `front-center`.
  A floor-standing part wants `bottom-center`; something that hangs flat on a
  wall wants `back-bottom-center`.

Normalisation happens once, at build time, which is why placement never has
to know anything about a file's internal quirks.

Two honest caveats. Reading a shape this way discards per-solid colours and
product names from a STEP assembly — set one material on the part instead.
And **nothing in the shipped library uses this path yet**: all 31 parts are
builders, so this route is exercised by the test suite but not by real
content. Expect to be the first to shake it out.

### 2b. Write a builder (parametric geometry)

A part's geometry code lives in its own folder, next to its manifest. Create
`builder.py` beside `part.json` and give it a `build` function — nothing in
the manifest names it, and nothing needs registering:

```python
# archplus/tools/partslib/library/basic/bar-stool/builder.py
from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """One docstring line, then the params it reads."""
    height = float(params.get("Height", 750))
    diameter = float(params.get("SeatDiameter", 340))
    ...
    return sh.fuse_all([seat] + legs)      # -> a Part.Shape
```

The contract is `def build(params, assets, ctx) -> Part.Shape`. Import
`Part`/`FreeCAD` *inside* the function, never at module scope, so the
headless test suite can import the module without FreeCAD present.

A part with **no** `builder.py` is an asset-only part: it is built by the
stock asset builder from the file named in `geometry.assets`. The absence of
the file is what guarantees no code from that folder runs.

`shapes.py` carries the shared massing primitives — `rounded_box`,
`square_leg`, `roll_top`, `panel_reveal_boxes`, `cut_boxes`, `toe_kick`,
`bar`, `tube_elbow`, `place`, `fuse_all`. Prefer them: every fillet in there
already falls back to a sharp edge rather than aborting the build when OCC
refuses.

Massing shared by several parts in the same family goes in the family's
`_shared.py`, reached as `from .. import _shared`. That relative import means
"my family" at any depth, so a part can later move into a sub-family folder
without editing its builder.

The two routes are not exclusive. `assets` is handed to every builder, so a
builder can generate the parametric part and load a fixed one for the rest —
a carcass computed from `params`, with a purchased handle fused on:

```python
def build(params, assets, ctx):
    carcass = sh.rounded_box(params["Width"], params["Depth"], params["Height"])
    handle = assets.shape("handle")        # from the manifest's assets map
    return sh.fuse_all([carcass, sh.place(handle, x=..., y=..., z=...)])
```

### 3. Conventions that matter

These apply to builders — a model file is whatever the vendor drew. They are
not style preferences; each one came from something looking wrong in a
render:

- **Axes.** X is width, Y is depth with the *back* at +Y, Z is up. Build
  from the origin so the part's minimum corner is (0, 0, 0); placement puts
  that corner on the picked point.
- **Measure what you advertise.** The browser shows `W × D × H` measured
  from the built shape, so a handle or cornice sticking out past the
  declared `Width` makes the catalogue lie. Build overhangs *inward*: make
  the top the advertised size and inset the carcass behind it.
- **Square, not round.** A 36 mm cylinder renders as a single line with no
  shading at thumbnail size. Legs and posts are square section.
- **Solid, not scattered.** Where the real object is one soft mass (a sofa),
  model one mass and *cut* the cushion seams into it. Separate floating
  cushions read worse.
- **Don't round a solid's plan corners and its top edge.** The two fillets
  collide at the corners and leave a picture-frame rim. Use `roll_top` for a
  roll that runs through.
- **Batch your cuts.** `cut_boxes()` subtracts a compound in one boolean.
  Twenty sequential cuts against a growing solid cost real seconds.
- **Avoid non-uniform scaling.** `oval()` runs a shape through
  `transformGeometry`, turning it into a BSpline surface that is far more
  expensive to tessellate — one such surface once cost 17 s per thumbnail.

### 4. Check it

```bash
uv run --with pytest --no-project pytest -q
```

`archplus/tools/partslib/tests/test_library_content.py` scans the real shipped library, so a
malformed manifest, an unknown facet value, an unresolvable builder symbol,
an unknown placement host or a facet icon missing from disk all fail here
rather than reaching a user as an empty panel.

Then open the Parts Library in FreeCAD and look at it. The test suite runs
without FreeCAD, so it cannot tell you whether a boolean succeeded, a fillet
silently fell back, or the thing simply looks wrong — only your eyes can.
The first open renders a thumbnail per part (with a progress dialog) and
caches it as `thumbnail.jpg` beside the manifest; commit that so a fresh
clone opens to a populated grid. Delete it to force a re-render after
changing geometry.

### IFC metadata

A placed part is an `ArchComponent`, so it carries `Description`, `IfcType`
and `IfcProperties` — and `IfcProperties` round-trips into IFC property sets
on export. This is the difference between a decorative block and something
that survives into the model a consultant receives.

`IfcType` is resolved in this order, first hit wins:

1. an explicit `"ifcType"` on the part,
2. the `ifcType` on the part's `element` facet value,
3. the `ifcType` on its `function` facet value,
4. `"Building Element Proxy"`.

So in practice you set it **once per element** in `archplus/tools/partslib/library/facets.json` and
never think about it again. Override on the part only when one element covers
two IFC types — a browse category like "Bathtubs & Showers" grouping an
`IfcSanitaryTerminal` with something else.

`ifcProperties` is a flat map whose values encode the property set, the IFC
type and the value, separated by double semicolons:

```json
"ifcProperties": {
  "Manufacturer":   "Pset_ManufacturerTypeInformation;;IfcLabel;;Geberit",
  "ModelReference": "Pset_ManufacturerTypeInformation;;IfcLabel;;204060"
}
```

`"Pset;;IfcType;;Value"`. A variant may override individual keys, which is
how three sizes of one product each carry their own order code while sharing
everything else. Get the encoding wrong and the property is dropped silently
on export rather than raising — so check a real export before trusting it.

Dimensions do **not** belong here. Width, depth and height are measured from
the built shape, so a hand-typed dimension would be a second source of truth
free to disagree with the geometry.

### Adding a new facet value

To use a room, function or element the vocabulary doesn't have yet, add it
to `archplus/tools/partslib/library/facets.json` *and* drop a matching 24×24 line-art SVG into
`archplus/tools/partslib/resources/icons/facets/` using `stroke="currentColor"` so it works in both
themes. A test asserts every referenced icon exists — a missing one renders
as a blank card with nothing in the console to explain why.

## TODO

Stairs:
- [ ] Support railings, balusters, etc.
- [ ] For half-turns, support spacing between the two stairways.

Windows:
- [ ] Muntins/grille (divided lite grids, e.g. 2×2, 3×3)
- [ ] Awning/hopper (top/bottom-hung) and tilt-and-turn operations
- [ ] Triple-pane and double-casement-plus-fixed configurations
- [ ] Real projecting sill geometry (currently the bottom jamb is flush)

## Requirements

- FreeCAD 1.1 (the BIM/Arch modules must be available).

## License

LGPL-2.1-or-later. This add-on includes modified copies of FreeCAD's
`ArchStairs.py` and `ArchWindow.py` (© Yorik van Havre), so as a derivative
work it is licensed under the same terms. `ArchWindow.py` is shared by both the
Doors and Windows tools (each keeps its own copy). See [LICENSE](LICENSE).
