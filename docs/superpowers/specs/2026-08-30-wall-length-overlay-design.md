# ArchPlus Wall: on-select length dimension overlay

Status: approved design, implemented (amended 2026-08-30 — dimensions
are per wall run and scoped by the selected faces, not per edge chain;
see §3 and §5)

## 1. Problem

ArchPlus walls are edited through sketches and task panels; the 3D view gives
no feedback about size. Picking a wall segment answers "how long is this
run?" only by reading properties or measuring by hand. The roadmap backlog
(`docs/ROADMAP.md`, Walls) already records the intent: live measurements in
the 3D view — on-select dimension lines and a length label beside the
selected segment, as a Coin overlay with no document objects, tracking
reflows.

This spec implements that backlog item: selecting a wall segment draws a
CAD-style dimension above the wall's top edge; deselecting removes it.

## 2. Approach

Per-object Coin overlay nodes driven by one global selection observer, both
following repo precedents:

- **Overlay = named `SoSeparator` in the segment's `RootNode`** — the exact
  mechanism of the existing face highlight
  (`addFaceHighlight`/`removeFaceHighlight` in `walls/object.py`). Parenting
  to the view provider means the overlay inherits the object's transform and
  lifetime for free, in the same coordinate frame the highlight already uses
  (segment shapes are built in world coordinates from sketch edges).
- **Selection = one global observer registered at import time** — the exact
  mechanism of `_PickPointRecorder` in `walls/gui.py`. On every selection
  event it recomputes the desired set of dimmed segments and diffs it
  against the currently drawn overlays.
- **3D picks land on the wall root**, not the segment (FreeCAD claims-children
  behavior). Root selections resolve each picked face to its owning segment
  with the existing `resolveRootFace(root, subname, pickPoint)` plus the
  recorded pick points — the same resolution the split command uses.
- **Reflows = `updateData`** — `_ViewProviderWall.updateData` already
  refreshes the highlight when a segment's `Shape` changes; it will rebuild
  the dim node the same way, so the label tracks sketch edits and panel-driven
  width/height changes live.

Alternatives rejected: a single global overlay node in the 3D-view scene
graph (must own view-tab/workbench lifetime and world-coordinate recompute;
no repo precedent), and widening each view provider's edit-scoped selection
watcher (one observer per wall, entangles the dim lifecycle with the
edit-highlight lifecycle).

## 3. What the user sees

Selecting a segment — clicking its face in the 3D view, or picking it in the
tree — draws above the wall's top edge:

- a dimension line parallel to the wall run's axis — one per **wall run**,
  a maximal straight sequence of claimed sketch edges (curved edges solo);
  a closed square wall therefore shows four runs, not its perimeter —
- short oblique ticks at both run ends,
- a screen-facing label at the midpoint with the run length in the user's
  unit scheme (e.g. `2450 mm`), via `SoText2` (constant on-screen size).

Deselect removes the overlay. Multi-selection dims every selected segment.
**Selection scoping:** picking specific faces dims only the runs those
faces belong to (each face's centroid projected onto the sketch plane and
matched to the nearest run within one wall width — the split command's
mapping); selecting the whole segment dims every run. Top/bottom faces
spanning corners match nothing and contribute no run.
The dim line and label render in a warm yellow distinct from the green edit
highlight, stay depth-tested so other geometry occludes them correctly, and
coexist with the highlight node (separate named separators).

The dimension floats in a plane `normal * (height + max(100, 5% height))`
above the segment's base — clear of the top face, no z-fighting.

**Measured length** = the run's axis polyline length (the sketch geometry
the user draws and edits). Seam-miter extensions at segment joints are join
artifacts, not wall length, and are excluded.

## 4. Module layout

New `archplus/tools/walls/dims.py`, structured like `model.py`: pure logic
importable headlessly, FreeCAD/pivy imported lazily inside functions.

- `segmentEdgeRuns(segment)` → per-run `(points, normal, height)` by
  clustering the segment's claimed edges exactly like `_buildSegment`
  (`Part.getSortedClusters`) and splitting each chain into wall runs
  (`model.chain_runs`), with the sketch's global transform already baked
  into the edge points.
- `_dimGeometry(polyline, normal, height)` → tick ends, line endpoints, and
  the label anchor for one run (pure; the pytest target).
- Coin builder: writes one `SoSeparator` named `"ArchPlusSegmentDim"`
  (naming convention: `ArchPlusSegmentHighlight`, `ArchPlusTargetPreview`)
  into the segment's `RootNode` — `SoDrawStyle` width 2, `SoBaseColor`,
  `SoCoordinate3`/`SoLineSet` for line and ticks, `SoFont`/`SoText2` for the
  label. Label text = `FreeCAD.Units.Quantity(len, Units.Length).UserString`,
  falling back to `"%.0f mm"` (stairs precedent).
- `_SelectionDims` selection observer + `install()`.

Wiring: `gui.py` calls `dims.install()` right after the `_PickPointRecorder`
registration (same import-time pattern). `dims` imports `gui` lazily inside
functions, so there is no circular import. The overlay add/remove helpers
live in `dims.py`; `_ViewProviderWall.updateData` calls into them on `Shape`
changes.

## 5. Selection semantics

On every `addSelection`/`removeSelection`/`clearSelection`/`setSelection`
event the observer recomputes the desired dimmed set from
`FreeCADGui.Selection.getSelectionEx()` and diffs:

| selection member | result |
|---|---|
| wall segment without named faces | dim every run |
| wall segment with `FaceN` submembers | dim the runs those faces map to (centroid matching) |
| wall root with `FaceN` submembers | dim each face's owning segment and run (pick-point resolution) |
| wall root in the tree (no faces) | dim nothing — spraying every segment with dimensions is noise |
| anything else | ignored |

Add missing overlay nodes, remove stale ones. Recompute-on-event keeps the
bookkeeping trivial: no per-object state beyond the current node map.

## 6. Error handling

- Every observer callback and Coin call wrapped in `try/except` like all
  existing observers and overlays — a failure never breaks selection or
  FreeCAD.
- Unresolvable root face (`resolveRootFace` returns `None`): skip silently.
  The split command warns because a command action failed; a passive overlay
  must not spam the Report view.
- Degenerate geometry (zero-length runs, doubled-back chains where
  `model.chain_runs` raises): no dim for that run; other runs still dim.
- Segment deleted while dimmed (undo, tree delete): removal wrapped in
  `try/except`; the node map prunes on the next diff.

## 7. Testing

- Headless pytest `archplus/tools/walls/tests/test_dims.py`, using the
  repo's fake-`FreeCADGui` monkeypatch pattern (`test_split.py`):
  - `_dimGeometry`: straight single-edge chain, L-shaped two-edge chain,
    tick/label placement and plane offset;
  - `axis_dims`: per-chain output, total length, doubled-back rejection;
  - selection mapping: direct segment pick, root face pick via faked
    `resolveRootFace`/`_lastPick`, tree root pick, non-wall objects;
  - label formatting fallback.
- GUI verification in `freecad_tests/verify_walls.py`, following the W22
  highlight-check pattern (traverse `RootNode` children by name):
  select a segment → dim node exists with the expected point count;
  change `Width` → node content updates; deselect → node gone.
- Docs: mark the roadmap backlog item shipped; note the overlay in
  `docs/TOOLS.md` (Walls).

## 8. Scope boundaries

In v1: segments only (the root has no shape); dimension above the top edge;
chain-axis length only (no per-edge dims, no area/height labels); no
preference toggle (the overlay follows selection by design — a toggle can be
added if it proves intrusive). Interactive endpoint handles (the second
roadmap backlog item) are a separate spec.
