# ArchPlus Wall: non-owning sketch walls with segment groups

Status: approved design, not yet implemented

## 1. Problem

ArchPlus has no wall tool: doors, windows and stairs still host on FreeCAD's
Arch Wall. That is not just a gap; Arch Wall's model is exactly wrong for how
walls should behave here:

1. **The wall owns its sketch.** `ArchComponent` registers the wall in its
   base sketch's `Components`, so one sketch belongs to one wall. Sharing a
   floor-plan sketch between walls of different widths — or between a wall and
   a future slab tool — is a fight with the component system.
2. **One wall, one fused solid.** All sketch edges are extruded and fused into
   a single shape. There are no per-segment objects, so per-segment control
   happens through `OverrideWidth`/`OverrideAlign`/`OverrideOffset` — plain
   lists indexed by edge number, which break the moment the sketch's edge
   numbering shifts (they are only toponaming-tolerant with the SketchArch
   add-on, which carries its own dead weight: `ArchSketchData`,
   `ArchSketchEdges`, `ArchSketchPropertySet`).
3. **Hosting is fragile.** A door or window subtracts its volume through
   subvolume math against the whole wall. ArchPlus's own copy carries the
   admission (`archplus/tools/windows/object.py:782`): the robust approach is
   to extrude per segment and punch the hole in the exact segment before
   fusing.
4. **Much of Arch Wall is deprecated or dormant** — `Refine` is commented out,
   blocks only support a single wire, the property-set machinery exists for an
   add-on we do not ship.

This spec replaces Arch Wall for ArchPlus work with a wall that *references* a
sketch without owning it, and that builds one wall segment per claimed sketch
edge, grouped as real objects in the tree.

## 2. Approach

One class, two roles, arbitrary nesting.

- **`Wall`** (the root) and **`WallSegment`** (every child) are the same
  `Part::FeaturePython` + `App::GroupExtensionPython` object (verified in
  FreeCAD 1.1: it can hold a shape *and* tree children). The root has no
  shape; it holds the sketch link and the defaults.
- **Children are segment groups**: each claims a set of sketch edges (by
  toponaming-tolerant subname) and extrudes them into one fused solid.
  A child's *effective* config = its own overrides + its ancestors', resolved
  by walking up the tree.
- **Nesting = organization + inheritance.** A nested exception child (e.g.
  "short wall" inside "interior") inherits the group's overrides without
  re-declaring them. Edge claims remain global — a descendant's claims are
  simply excluded from its ancestors' extrusions.
- **The sketch is referenced, never owned.** No Arch Component registration;
  the sketch stays free for other walls and future tools. Construction
  geometry cannot be claimed: Sketcher excludes it from `Shape` and its
  subnames (verified).
- **Hosting resolves at the wall level.** Doors and windows host on the wall
  root; each segment's `execute()` subtracts the openings that intersect its
  own extrusion — the exact-segment approach from the TODO above, without the
  "opening spans two segments" gap (see §7).

## 3. Objects and the tree

```
Wall "Ground floor"            width=300, height=2800, align=Center, offset=0
├── Segments "interior"        width=200            (claims: rest)
│   └── Segments "short wall"  height=2200          (claims: Edge7)
└── Segments "exterior"        width=300            (claims: Edge0..4, 17, 22)
```

| object | property | type | meaning |
|---|---|---|---|
| Wall (root) | `Sketch` | `App::PropertyLink` | the base sketch, set at creation |
| | `Width` | `App::PropertyLength` | default width, 300 mm |
| | `Height` | `App::PropertyLength` | default height, 2800 mm |
| | `Align` | `App::PropertyEnumeration` | `Center`/`Left`/`Right`, default `Center` |
| | `Offset` | `App::PropertyDistance` | baseline offset, default 0 (wall-level only in v1) |
| | `Subtractions` | `App::PropertyLinkList` | hosted doors/windows; each segment cuts the ones intersecting it (§7) |
| WallSegment | `Base` | `App::PropertyLink` | the sketch — Arch-compatible name, non-owning; auto-copied from the parent at creation |
| | `Edges` | `App::PropertyLinkSubList` | claimed sketch subnames (e.g. `Edge1`, `Edge3`) |
| | `Rest` | `App::PropertyBool` | this child claims *all unclaimed edges* |
| | `Width` | `App::PropertyLength` | `0 = inherit` |
| | `Height` | `App::PropertyLength` | `0 = inherit` |
| | `Align` | `App::PropertyEnumeration` | `Inherit`/`Left`/`Right`/`Center` |

Type strings: `"Wall"` (root), `"WallSegment"` (children).

Naming rules:

- Every segment carries its own `Base` link, seeded from its parent at
  creation. Re-parenting by drag-and-drop never invalidates a link; the
  inherited config is re-derived automatically.
- Segments are plain groups, not `App::Part`: children keep global
  coordinates, so a child's placement is never compounded with its parent's.
- Root `Placement` is identity and unused in v1 (moving a whole wall family as
  one unit is deferred).

## 4. Claims and rebuild

- A claim is a sketch subname (`PropertyLinkSubList`), so claims survive edge
  renumbering under FreeCAD's toponaming.
- **"Rest"**: a child with `Edges` empty and `Rest = True` claims every edge
  claimed by no one else. At most **one** rest child, and it must be a direct
  child of the root. A wall may have none — then new sketch edges build
  nothing (warning in the Report view).
- **Effective edges of a group** = its claims minus the union of its
  descendants' claims. Leaves extrude exactly what they claim. An edge claimed
  by two leaves builds in neither, with a warning.
- Sketch changes propagate through the dependency graph automatically:
  - new edge → rest child (or unbuilt + warning),
  - deleted edge → its claim silently drops,
  - edited edge → segment recomputes.
- Arcs and curves are supported (offset the edge in the sketch plane and
  extrude along the sketch normal); a wall is vertical by definition in v1 —
  Arch's `Normal`/`Face` properties are dropped.

## 5. Config and inheritance

Resolution: `effective(segment, prop)` walks from the segment up through its
tree parents; the root resolves `Inherit`/`0` to the built-in defaults
(Center, 300, 2800, 0).

Conventions (verified: FreeCAD 1.1 rejects `None` for `PropertyLength`):

- `Width`/`Height`: `0 = inherit` — Arch's own precedent ("Keep 0 for
  automatic"); safe because a zero-width wall is meaningless.
- `Align`: explicit `Inherit` entry as the first enumeration value.

Dropped or deferred Arch Wall properties:

| Arch Wall prop | verdict |
|---|---|
| `Normal`, `Face` | dropped — extrusion is always along the sketch normal |
| `OverrideWidth/Align/Offset` | dropped — replaced by the claim model |
| `ArchSketchData/Edges/PropertySet` | dropped — SketchArch add-on machinery |
| `Refine` | dropped — already deprecated in Arch |
| `MakeBlocks`, `BlockLength/Height`, `OffsetFirst/Second`, `Joint`, `CountEntire/Broken` | deferred v2 |
| `Length`, `Area` | deferred (schedules) |
| `Hosts`, `Additions` | dropped in v1 (additions = pilasters etc., later) |
| IFC properties, `Material`, `MoveWithHost`, `HiRes` | deferred/dropped |

## 6. Geometry build

`WallSegment.execute()`:

1. Resolve effective config (width, height, align, offset).
2. Resolve effective edges (claims minus descendants).
3. For each edge: offset a copy of the edge in the sketch plane by
   width/align/offset (Arch semantics: Left/Right/Center around the
   baseline), close into a wire, extrude along the sketch normal by height.
4. Fuse the per-edge solids into one shape.
5. Subtract the wall's hosted openings that intersect this segment (bbox
   pre-check + OCC `common` test against the wall root's `Subtractions`).
6. Assign the result; empty claims → empty shape.

## 7. Hosting (v1)

Openings resolve at the wall level, so an opening spanning two segments is
cut from both (a window across a split run or a corner junction). A fused
segment solid is a plain OCC solid — Boolean subtraction is unaffected by
fusing; the fragile part of Arch's hosting was the width-probing subvolume
math, which this design replaces entirely.

- **Hosting targets the Wall root.** `Hosts = [wall]`; the root's
  `Subtractions` holds the doors/windows. Deleting a segment never orphans an
  opening.
- **Per-segment cutting at recompute.** Each segment subtracts only the
  openings whose volumes intersect its own extrusion: cheap bounding-box
  pre-check, then an OCC `common` test. No user action needed for an opening
  spanning segments.
- **Placement unchanged**: pick a segment face in the 3D view; the tool walks
  up to the wall root for the host.
- **Door/window code**: the host-type check in `archplus/tools/windows/object.py`
  (and the shared door path) is extended to accept the wall; the width-probing
  path is bypassed — the opening's actual shape is what gets subtracted. The
  root exposes the Arch-ish interface (`Width`/`Height`/`Align`/`Base`), so
  the existing re-cut-on-edit machinery (windows `gui.py`) keeps working.
- **Warning**: an opening that intersects no segment (floating in a gap)
  reports "opening not applied" once.

**Known limitation — sibling joint artifacts.** Two collinear edges placed in
*different* groups butt with coplanar end faces and can flicker (z-fighting)
in the 3D view — cosmetic only, the same artifact as any two touching solids
in FreeCAD. Within one group it cannot happen (fusing merges the faces), and
T-junctions between groups are unaffected. Accepted for v1; documented in
`docs/TOOLS.md`.

## 8. Workflow and UI

- **Create**: select a sketch → Wall tool (ArchPlus menu/toolbar) → `Wall` +
  one rest child "Segments". Deleting the rest child is how you switch to
  explicit-claims-only.
- **Split**: pick built solids in the 3D view (box/ctrl-select whole groups,
  or click individual faces) → "Split into new segment" (toolbar + context
  menu) → a new sibling child takes the selected claims; the source child
  loses them. Face → claimed edge mapping by matching the clicked face's
  centroid against the claimed edges in the sketch plane (the same technique
  `freecad_tests/verify_openings.py` already uses). The sketch stays hidden
  throughout.
- **Nest**: drag the new child under another group in the tree — inheritance
  follows.
- **Delete** a child: its edges become unclaimed (rest child or unbuilt +
  warning).

### Task panels

Docked, FreeCAD-style panels with debounced live preview, following the
windows/stairs pattern (`_refImage` PNGs, `QGroupBox` sections, description
lines under fields). Two panels:

**Edit Wall** (root, double-click):

- *Dimensions* — plan reference image (W across the wall, baseline,
  Left/Center/Right trio with the Offset gap) + fields W · Width, H · Height,
  Align, Offset, each with a description line. These are the defaults —
  children follow them unless they override.
- *Sketch & claims* — Sketch link picker, Rest segment picker (top-level
  segments + "None"), claim stats ("4 edges claimed · 0 unclaimed").
- *Metadata* — Tag / Mark.

**Edit Segment** (child, double-click):

- *Override* — the same plan reference image; W/H/Align rows with a
  per-field override checkbox: **checked = overrides, editable**; unchecked =
  greyed field showing the inherited (effective) value. Checking pre-fills the
  field with the inherited value. The property editor keeps the `0` /
  `Inherit` conventions underneath — the panel is the friendly face of the
  same data.
- *Claims* — read-only summary ("2 edges claimed · 1 auto") plus a note that
  edges are split/reassigned in the 3D view and that Rest and Sketch are set
  in the wall panel.

**Rest and Sketch settings appear only in the root panel** (and the property
editor); the segment panel never shows them. The height needs no diagram —
its description line suffices; the diagrams cover W, Align and Offset only.

## 9. Error handling

- Deleted sketch: segments keep their `Base` link dangling; `execute()` sees
  no usable edges and yields an empty shape without raising.
- Double claim: warning in Report view, edge builds nowhere.
- New edges with no rest child: Report view warning listing the count.
- A `Rest` child with explicit `Edges`: `Edges` ignored, warning once.
- Invalid subnames (should not happen under TNP): skipped with a warning.

## 10. Files and testing

```
archplus/tools/walls/
    __init__.py     tool registration (menu, toolbar)
    model.py        pure: claim resolution, effective-config resolution,
                    effective-edge computation, edge-vs-face matching
    object.py       FreeCAD proxy: properties, execute(), onChanged()
    gui.py          commands (create wall, split segment), task panels,
                    ViewProvider
    resources/icons/  plan + align/offset reference images (PNG)
    tests/test_model.py     headless pytest for the pure logic
archplus/freecad_tests/verify_walls.py    FreeCAD-session verification
```

Headless tests (`test_model.py`) — claim math, inheritance resolution,
rest-child rules, conflict detection, matching logic.

`verify_walls.py` (existing harness: sketch → wall → split → re-edit sketch →
host window → save/reload):

1. Create sketch with 5 edges (one construction line) → wall: one rest child,
   4 edge claims, construction line never claimed.
2. Split two edges into "exterior"; rest child now extrudes 2 edges.
3. Nest a single-edge child under "exterior" with `Height=2200`: effective
   height 2200, effective width inherited from "exterior".
4. Edit the sketch (move a vertex, add an edge, delete an edge): claims
   follow, new edge lands in rest, deleted edge drops.
5. Host a window on a segment: the segment's volume shrinks by the opening;
   unhosting restores it.
6. Host a window across a split run (two collinear segments): both segments
   are cut, each exactly in its half; an opening intersecting nothing reports
   "opening not applied".
7. Save/reload: tree, claims and inheritance survive.

## 11. Scope boundaries

In v1: geometry, grouping/split, nested inheritance, per-segment hosting,
TNP-safe rebuild, task panels (root + segment), warnings.

Out (later): materials/colors, blocks, IFC, merge command,
root-level placement/moving, Arch wall migration, `Length`/`Area`.

## 12. Docs

- `docs/TOOLS.md` gains a Walls section (concepts: claims, rest, inheritance;
  commands: create, split).
- `docs/ROADMAP.md` moves "walls" to shipped.
