# ArchPlus Parts Library — Design

**Date:** 2026-08-15
**Status:** Approved for planning

## 1. Purpose

Add a fourth ArchPlus tool: a browsable library of reusable BIM parts — sanitary
fixtures, furniture, lighting, appliances. The user opens a dock panel, narrows
the catalog by facet or search, previews a part in 3D with its description and
measurements, and clicks in the 3D view to place it.

The three existing ArchPlus tools are parametric *generators*: they build
geometry from a spec the user types. The Parts Library is different in kind. It
is *content* plus a browser, so it needs a file format standard, an index, a
preview renderer and an insertion path — none of which the existing tools have.

### Goals

- A documented, validated standard for what a part is.
- Rich metadata per part: description, measurements, manufacturer data, IFC
  classification — surviving into IFC export.
- Browsing that stays fast as the catalog grows.
- Insertion that produces **one** object in the tree, editable afterwards, and
  that does not break when the file is opened without ArchPlus.

### Non-goals

Deliberately excluded, each additive against this schema:

- User-supplied library folders (see §6.3 for why the door stays open).
- Free-form tags — superseded by facets (§4).
- Multi-axis variant matrices (§5.3).
- Bulk import tooling for vendor IFC/STEP catalogs.
- Per-part builder code colocated in part folders (§6.4).

## 2. Decisions

| # | Decision | Rationale |
|---|---|---|
| D1 | Library bundled in-repo, curated only | Builders are Python; no arbitrary code from untrusted sources |
| D2 | Manifest (JSON) + optional shape asset per part | Metadata under our control; parametric where it matters |
| D3 | Faceted classification, not a category tree | One tree cannot answer "what is it" and "where does it go" at once |
| D4 | Insert = live link + cached shape | Editable with the library; still renders without it |
| D5 | Dockable panel, stays open | Enables the pick → place → pick loop a library exists for |
| D6 | Host-aware placement | Wall/ceiling-mounted fixtures otherwise need manual fix-up every insert |
| D7 | Builders resolve only from `partslib_builders` | Keeps all executable code in one auditable place |
| D8 | Measurements derived from geometry, never authored | A spec sheet that cannot drift from the model |

## 3. The part standard

A part is a folder. `part.json` is its contract; nothing else in the folder is
authoritative.

```
library/sanitary/wc-geberit-icon/
  part.json            manifest — the only authoritative file
  thumbnail.png        committed; regenerated only if absent
  wc-360.brep          shape asset, converted from vendor STEP
  wc-490.brep
  .cache/              gitignored — parsed/derived artifacts
```

### 3.1 Manifest

```json
{
  "schema": 1,
  "id": "wc-geberit-icon",
  "name": "Wall-hung WC — Geberit iCon",
  "description": "Rimless wall-hung pan for concealed cistern.",
  "keywords": ["toilet", "wc", "pan", "rimless"],

  "facets": {
    "function": "Sanitary",
    "element":  "WC",
    "room":     ["Bathroom", "Cloakroom"]
  },

  "ifcProperties": {
    "Manufacturer": "Pset_ManufacturerTypeInformation;;IfcLabel;;Geberit"
  },

  "geometry": {
    "builder": "asset.single",
    "assets":  { "body": "wc-360.brep" },
    "transform": { "rotate": [90, 0, 0], "anchor": "back-bottom-center" }
  },

  "placement": { "host": "wall", "offset": 400 },

  "variants": [
    { "label": "360 mm",
      "assets": { "body": "wc-360.brep" },
      "ifcProperties": { "ModelReference": "Pset_ManufacturerTypeInformation;;IfcLabel;;204060" } },
    { "label": "490 mm",
      "assets": { "body": "wc-490.brep" },
      "ifcProperties": { "ModelReference": "Pset_ManufacturerTypeInformation;;IfcLabel;;204070" } }
  ]
}
```

### 3.2 Fields

| Field | Required | Notes |
|---|:-:|---|
| `schema` | ✅ | Format version. Lets a v2 land without breaking saved documents. |
| `id` | ✅ | **Immutable.** Written into user documents — see §3.3. |
| `name` | ✅ | Display name in the grid and detail pane. |
| `facets` | ✅ | Validated against `facets.json`. See §4. |
| `geometry` | ✅ | See §6. |
| `description` | | Shown in the detail pane; fed to search. |
| `keywords` | | Search only — not a classification axis. |
| `ifcType` | | Overrides the facet-derived default (§4.2). |
| `ifcProperties` | | `"Pset;;Type;;Value"`. Merged variant-over-part. |
| `params` | | Builder inputs only. See §3.4. |
| `placement` | | Defaults to `{"host": "free"}`. See §7. |
| `variants` | | Absent ⇒ one implicit default variant. See §5.3. |

Unknown fields are a validation **warning**, not an error — forward
compatibility for manifests written against a later schema.

### 3.3 `id` is permanent

Because insertion stores `PartId` in the user's document (§5), an id appears in
files ArchPlus does not control. Renaming one silently degrades every project
referencing it to its cached shape.

`id` is therefore independent of folder path and of every facet value. The
library may be reorganised — folders moved, facets restructured — with no
effect on saved documents. Ids are unique across the library; the indexer fails
loudly on a duplicate.

### 3.4 `params` are builder inputs, nothing else

If a value does not change geometry, it is not a param. Two rules follow:

- **Driving dimensions** are declared params, passed to the builder, and appear
  as editable object properties.
- **Measurements** (width, depth, height) are *derived* from the built shape's
  bounding box at index time. They are never authored, so they cannot disagree
  with the geometry — the standard failure mode of hand-written spec sheets.

An asset-backed part typically declares no params at all: its geometry is
fixed, and its measurements are measured.

## 4. Faceted classification

### 4.1 Why not a tree

A single taxonomy forces one field to answer several unrelated questions. A bar
stool belongs under both `Kitchen` and `Seating`; a wall lamp under both
`Lighting` and `Bedroom`. There is no correct answer because the question is
malformed.

Facets are independent fields, each answering one question, with the browser
grouping by whichever the user selects. This is also how BIM classification
actually works — Uniclass 2015 uses separate tables for Entities, Spaces,
Elements and Products; OmniClass has fifteen.

Facets also subsume tags. Tags exist to work around single-tree membership; a
multi-valued facet expresses the same thing with a controlled vocabulary, so
`wall-hung` and `wallhung` cannot both come into existence.

### 4.2 Vocabulary

`library/facets.json` defines the allowed facets and their values.

```json
{
  "function": { "label": "Function", "multi": false, "values": {
      "Sanitary": {}, "Seating": {}, "Storage": {}, "Lighting": {} } },

  "element":  { "label": "Element",  "multi": false, "values": {
      "WC":    { "ifcType": "Sanitary Terminal" },
      "Basin": { "ifcType": "Sanitary Terminal" },
      "Chair": { "ifcType": "Furniture" } } },

  "room":     { "label": "Room",     "multi": true,  "values": {
      "Bathroom": {}, "Cloakroom": {}, "Kitchen": {}, "Bedroom": {} } }
}
```

- `function` and `element` are single-valued; `room` is multi-valued.
- Values may contain `/` for optional nesting (`Sanitary/WC`), rendered as a
  sub-tree. The schema itself is depth-agnostic.
- A manifest naming a value absent from the vocabulary fails validation.

**IfcType resolution order:** the part's explicit `ifcType` → the `element`
value's mapping → the `function` value's mapping → `"Building Element Proxy"`.

## 5. The inserted object

### 5.1 Type

A `Part::FeaturePython` subclassing `ArchComponent.Component`, matching
`windowsplus_object.py:1769`. Inheriting from `ArchComponent` supplies
`Description`, `Tag`, `Material`, `IfcType`, `IfcData` and `IfcProperties` for
free, and `IfcProperties` round-trips into IFC property sets on export
(`ArchComponent.py:2482`, `ArchIFC.py:75-98`).

Properties on the object:

| Property | Type | Notes |
|---|---|---|
| `PartId` | String, read-only | Resolves back to the library |
| `Variant` | Enumeration | Populated from the manifest |
| *(per declared param)* | Length / Angle / Integer / Bool / Enum | Editable, drives rebuild |
| `Description`, `IfcType`, `IfcProperties` | inherited | Populated on insert |

### 5.2 Live link + cached shape

The cache needs **no new property**: `obj.Shape` is already persisted in the
FCStd by FreeCAD. Therefore:

- `execute()` rebuilds from the library when the part resolves.
- When it does not resolve — ArchPlus absent, part removed, id renamed —
  `execute()` **returns without touching `obj.Shape`**. Saved geometry stays on
  screen; the ViewProvider shows a warning overlay and params go read-only.
- **Nothing rebuilds on document open.** Unchanged objects are not touched, so
  no recompute is triggered. Rebuilding is an explicit right-click **Reload
  from library**.

That last rule is deliberate. Automatic rebuild would mean a corrected library
part silently altering drawings that have already been issued.

### 5.3 Variants

A variant is a named alternative of the same catalog entry — not necessarily a
size. Sizes (`360 mm`), finishes (`Oak`), and handing (`Left`) are all variants.

Each variant carries a `label` and may override `assets`, `params`,
`ifcProperties` and `thumbnail`. Overrides merge over the part-level values.

The variant list is **flat**, not a matrix of axes. `size × finish × handing`
reads tidily in a schema and expands into 36 combinations to author and
thumbnail. Where a part genuinely needs a second independent axis, that axis is
a param, not a variant.

Switching `Variant` on an inserted object rebuilds it in place, preserving
placement.

## 6. Geometry

### 6.1 Builder contract

```python
def build(params, assets, ctx) -> Part.Shape
```

- `params` — resolved parameter values.
- `assets` — lazy loader; `assets.shape("body")` resolves a manifest asset name
  to a file, parses it, caches to `.brep`, returns a `Part.Shape`.
- `ctx` — units, normalisation helpers, anchoring.

One contract covers three usages:

```python
# Pure generation — no assets
def base_cabinet(params, assets, ctx):
    return _carcass(params["Width"], params["Height"], params["Depth"])

# Pure asset — ships with ArchPlus; third-party STEP needs zero code
def single(params, assets, ctx):
    return ctx.normalize(assets.shape("body"), params)

# Hybrid — generated carcass, purchased hardware
def cabinet_with_handle(params, assets, ctx):
    carcass = _carcass(params["Width"], params["Height"], params["Depth"])
    handle  = assets.shape("handle")
    handle.Placement = ctx.anchor(carcass, "front-center")
    return carcass.fuse(handle)
```

### 6.2 Loading assets without polluting the document

Every supported source becomes a bare `Part.Shape`, never a `DocumentObject`.
This is what prevents the tree pollution that motivated the whole design —
`File → Insert` copies every sketch, body and pad into the document root, and
FreeCAD's delete does not cascade, so removing the top object orphans the rest.

Techniques, all with precedent in `ArchReference.py`:

| Source | Technique |
|---|---|
| `.brep` | `Part.Shape().importBrepFromString()` (`ArchReference.py:257-259`) |
| `.step` | `Part.read()` → shape; converted to `.brep` at authoring time |
| `.FCStd` | Read as a zip, pull `.brp` blobs directly (`ArchReference.py:153-165`) |
| other | Snapshot `doc.Objects` → import → harvest shapes → `removeObject` (`ArchReference.py:222-233`) |

### 6.3 Third-party content

Adapting a vendor download is a **metadata** exercise, not a coding one: drop
the asset in a part folder, write a manifest using the stock `asset.single`
builder, fill in facets and IFC properties.

The real work is normalisation. Vendor STEP arrives at an arbitrary origin and
orientation, so `geometry.transform` carries `rotate`, `unit` and `anchor`. The
origin is normalised **once at build time**, which is why placement (§7) never
needs to know a shape's internal quirks.

Two known limitations, accepted:

- `importBrepFromString` loses per-solid colours and product names from STEP
  assemblies. Assign one material in the manifest instead.
- Asset-backed parts are not dimensionally parametric. A 360 mm pan is not a
  stretched 490 mm pan; those are separate variants with separate assets.
  Non-uniform scaling of purchased geometry is explicitly rejected — it
  distorts wall thicknesses and reports products that are not sold.

**Security.** Manifests name builders by symbol (`"builder": "sanitary.wc_pan"`),
never by file path or import path. Builders resolve only from the
`partslib_builders` package inside the repo. An asset-only part therefore
executes no library-supplied code at all — the subset that could safely be
opened to user-supplied libraries later, without revisiting any of this.

### 6.4 Builders are central, not per-part

Builders live in `partslib_builders/`, organised by family. A part folder does
**not** carry its own `builder.py` in v1.

The value of a Python builder is reuse: one `furniture.cabinet` parameterised by
width/height/depth serves thirty cabinets, where thirty colocated builders serve
one each and drift apart on the first bug fix. Central placement also keeps all
executable code in one auditable location, which is what makes D1/D7
enforceable rather than aspirational.

Revisit when: builders start appearing one-per-part with no shared logic. The
manifest already names builders by symbol, so adding colocation later is an
`importlib` change and no format change.

## 7. Placement

```json
"placement": { "host": "wall", "offset": 400 }
```

`host` ∈ `wall` | `floor` | `ceiling` | `free`. Default `free`.

All four are implemented through **one** rule rather than four code paths:
placement always orients from the picked face, and `host` decides only which way
the offset runs and whether to snap to the host's base.

| Host | Behaviour |
|---|---|
| `wall` | Orient to picked face; snap Z to host base; offset up. Exactly `_doorPlacement` (`doorsplus_gui.py:852`) |
| `ceiling` | Orient to picked soffit face; offset down from it |
| `floor` | Orient to picked face; offset up from it |
| `free` | Working plane orientation at the picked point |

This deliberately avoids raycasting to find the slab above, which is where
host-aware placement usually turns expensive.

`_doorPlacement` already does the hard part — orientation from a picked face via
`DraftGeomUtils.placement_from_face`, base-Z snapping, cursor centring.
Generalising it is cheaper than writing placement from scratch.

Insertion runs a `Snapper.getPoint()` session with a ghost tracker (the
`_placeTracker` pattern, `doorsplus_gui.py:887`). The panel stays open
afterwards, so placing six chairs is six clicks.

## 8. The dock panel

A `QDockWidget`, docked right by default, persisting across insertions and
workbench switches.

```
┌ ArchPlus Library ──────┐
│ ┌────────────────────┐ │
│ │ search…            │ │  name + keywords + description
│ ├────────────────────┤ │
│ │ Group by: (Room ▾) │ │  Function / Element / Room
│ ├──────────┬─────────┤ │
│ │ Bathroom │ ▣  ▣  ▣ │ │  grid of cached PNG thumbnails
│ │ Kitchen  │ ▣  ▣    │ │
│ │ Bedroom  │ ▣  ▣  ▣ │ │
│ ├──────────┴─────────┤ │
│ │   [ live 3D ]      │ │  QuarterWidget — selected part
│ ├────────────────────┤ │
│ │ Variant: (360mm ▾) │ │
│ │ W 360  D 540  H 400│ │  derived from bounding box
│ │ Rimless wall-hung… │ │  description
│ ├────────────────────┤ │
│ │      [ Place ]     │ │
│ └────────────────────┘ │
└────────────────────────┘
```

- **Group by** re-buckets the same index; multi-valued `room` legitimately
  places one part under several headings. Defaults to Function, remembered
  between sessions.
- **Search** filters across name, keywords and description, and applies within
  the current grouping.
- **Live preview** is a `pivy.quarter.QuarterWidget` — a plain `QWidget`, so it
  embeds directly (`OfflineRenderingUtils.py:487`). One viewport, for the
  selected part only.

## 9. Index, caches, thumbnails

**Index.** At startup, scan `library/**/part.json` — text only, no geometry.
Cache to `%APPDATA%/FreeCAD/ArchPlus/index.json`, invalidated per-manifest on
mtime. Browsing therefore never loads a shape, which is what keeps the panel
responsive as the catalog grows.

**Thumbnails.** Committed to the repo, so a fresh clone opens to a populated
grid. Where one is missing, render at index time in the background:
`OfflineRenderingUtils.render()` uses `SoOffscreenRenderer` with
`camera.viewAll()` auto-fit (`:395-405`), and `buildScene()` builds a Coin node
straight from a bare `Part.Shape` via `Shape.writeInventor(2, 0.01)` (`:409`).
No document and no open 3D view are required.

**Asset cache.** Parsed assets cache to `.brep` under a gitignored `.cache/`.

**Repo policy.** Commit thumbnails (small, deterministic). Commit `.brep`
assets, converted at authoring time; keep vendor STEP out of the repo. Measure
actual sizes at the first real part — OCC's BREP is ASCII and may not be smaller
than the source STEP; the certain win is load speed, not bytes. Revisit with
git-lfs only if the repo becomes heavy.

## 10. Module layout

```
partslib_manifest.py   schema, load, validate         ← no FreeCAD imports
partslib_index.py      scan, cache, facets, search    ← no FreeCAD imports
partslib_geometry.py   builder registry, asset load, brep cache
partslib_thumbs.py     offscreen PNG render
partslib_object.py     ArchPlus_Part + ViewProvider
partslib_gui.py        dock panel + ArchPlus_PartsLibrary command
partslib_builders/     asset.py, sanitary.py, furniture.py, …
library/               facets.json + part folders
```

Six modules rather than the established two-files-per-tool convention. The
justification is not tidiness: `partslib_manifest.py` and `partslib_index.py`
have **zero FreeCAD imports**, which is the only reason manifest validation,
facet resolution, variant merging and search ranking are testable headlessly
(§11). Individual filenames still follow the existing `*_object.py` /
`*_gui.py` pattern.

The only change to existing code is `InitGui.py`: add
`"ArchPlus_PartsLibrary"` to the `commands` list and import `partslib_gui` in
`add_ui()`.

## 11. Testing

`tests/` is currently empty — no tests are committed; the `__pycache__` there is
stale.

The valuable half of this subsystem is pure Python and runs under plain pytest
with no FreeCAD present:

- manifest parsing, validation, unknown-field warnings
- facet vocabulary resolution and rejection of unknown values
- IfcType resolution order (§4.2)
- variant merge semantics (§5.3)
- duplicate-id detection
- search ranking and grouping
- index cache invalidation on mtime

Geometry, thumbnails, placement and the panel require FreeCAD and are verified
manually against a checklist.

## 12. Risks

1. **`QuarterWidget` under the Qt6 `PySide` shim.** FreeCAD's own usage imports
   `PySide2` (`OfflineRenderingUtils.py:485`) while ArchPlus modules use the
   `PySide` shim. This is the riskiest widget in the plan — resolve with a
   ~20-line spike **before** committing to the live preview pane. Fallback: a
   larger static PNG in the detail pane.
2. **`SoOffscreenRenderer` needs a GL context** and fails on some drivers.
   Mitigated by committing thumbnails, which makes runtime rendering a
   convenience rather than a dependency.
3. **BREP sizes in git.** Measure at the first real part before converting a
   catalog (§9).
4. **Dock widget lifecycle** across workbench switches and document close.

## 13. Future extensions

Each is additive against this schema and designed for, not built:

- **User-supplied libraries**, restricted to asset-only parts (§6.3).
- **Per-part builders** via `importlib` (§6.4).
- **Additional facets** — `discipline` for MEP/Structural federation — as a
  `facets.json` edit.
- **Vendor catalog import** tooling for bulk IFC/STEP ingestion.
