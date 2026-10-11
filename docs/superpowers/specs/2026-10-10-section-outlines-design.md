# Section outlines — design

Date: 2026-10-10
Status: draft (awaiting user review)
Branch: `section-outlines`

## Purpose

Modelling a furnished plan is unusable: any edit freezes the UI for minutes.
Measured on the real document, moving one library part costs **~2.5 minutes in
a freshly opened copy** (11 s recompute + 141 s redraw) and **~7 minutes in
the live session** (125 s + 309 s); an idle redraw in that session is 86 s.

The cost is the drawings, not the edit. Four Draft `Shape2DView` plan cuts
each cover a whole floor (29 / 29 / 42 / 50 objects, 15–26 of them placed
library parts), feeding 5 TechDraw projected items, 16 dimensions and 2 pages
— and every change re-runs all of it, because they are all dependents of the
things the section planes list.

This design makes the furniture cheap to draw: each placed library part
contributes its **cached plan outline** instead of its solid, so the drawing
is built from a fraction of the edges, and every stage that scales with edges
— Draft's projection, TechDraw's re-projection of it, the page render, the
3D display of the section views — comes down with it.

## Background: what already exists

- **The pipeline is Draft's.** `Shape2DView.execute` expands the plane's
  objects (`groups.get_group_contents`), applies `ExclusionNames` *before*
  expansion and `VisibleOnly` *after*, cuts each shape against the section
  volume, and projects **one compound** with `TechDraw.projectEx`. The only
  per-object call is `self._get_shapes(o.Shape, onlysolids)` — nothing hands
  the object itself to a hook.
- **Exclusion cannot reach group-listed objects.** `ExclusionNames` only bites
  objects listed directly on the plane, which is why the furniture reached
  through the level groups could not be dropped (measured: the two planes that
  list parts directly fell 2.44 → 0.71 s and 3.63 → 0.71 s; the two that reach
  them through groups did not move).
- **Occlusion is resolved across the compound**, not per object: a box inside
  a box projects to 4 visible edges as a compound and 8 projected separately.
  An outline riding in the same compound keeps its occlusion against the walls.
- **A part's shape is local, its placement is mirrored into the `TopoShape`**
  (`Shape.Placement` equals `o.Placement`), so anything substituted for it
  must carry the same placement or be baked global.
- **All four section planes are plan cuts** (normal +Z, z = 1400 and 4200) and
  the views run `ProjectionMode = Solid`, `FuseArch = True`,
  `OnlySolids = False`, `VisibleOnly = False`.
- **Cost tracks the drawing's edge count.** Substituting crude footprint
  blocks (1833 → 639 edges in the 50-object view) took the redraw 180 → 40 s;
  hiding the section views' own view providers took it 21 → 0.12 s. The
  recompute, by contrast, stayed ~20–25 s in every configuration: that half is
  TechDraw's per-view/dimension/page machinery, insensitive to geometry size.
- **TechDraw has one switch for this** — `DrawPage.KeepUpdated`, documented as
  *"Keep page in sync with model"*, `True` today. Its views have none:
  `DrawProjGroupItem`'s only flags are `CoarseView`, `*Hidden`, `*Visible`,
  `LockPosition`, `Perspective`.

## The outline

Computed from the part's built solid, in its own frame:

1. `TechDraw.projectEx(solid, +Z)` — the same hidden-line projection Draft
   uses, taking the visible edge groups.
2. `TechDraw.findOuterWire(edges)` — TechDraw's own boundary extractor
   (*"planar graph traversal finds OuterWire in edge pile"*).
3. `Part.Face(wire)`, extruded 1 mm — a **thin slab**, so it survives
   `OnlySolids` and behaves like a solid through `cut` and `projectEx`.

Measured over the 23 part types placed in the real document:

| | result |
|---|---|
| outline size | 1 face, **6–54 edges** (the solids draw 9–79) |
| cost | **10–30 ms per part** |
| drawing stays inside the outline | **22 of 23 types** (100 % of drawn vertices) |

**Self-check, per part per build**: every vertex of the part's own drawing must
lie within the outline before it is used. The waste-bin fails (its projection
has two separate outlines and `findOuterWire` returns one) — that part
projects its solid. This is the correctness invariant, enforced mechanically
rather than assumed: **an outline is an optimisation, never a wrong drawing**.

## Where the outline lives

- **On the part's proxy**, not a property — the same hard-won reason
  `partRoles` is not one: declaring a new property on a placed part breaks
  FreeCAD's undo/redo of that object's *other* properties.
- **Lazily** on the first ask by a view, keyed by the shape the part last built
  (its hash, recorded by the part as it rebuilds), dropped when the part
  rebuilds. One-off ~8 s for all 84 parts on a full rebuild; 10–30 ms per
  changed part afterwards — against ~13 s of section-view work on *every*
  recompute today.

## The view

A new tool folder `archplus/tools/sections/` (`object.py`, `gui.py`,
`tests/`), matching the per-tool layout. Names here — folder, object, command
— are provisional.

- **Object**: `ArchPlus_SectionView`, an `App::FeaturePython` whose `execute`
  writes the 2D compound into `obj.Shape` — the same kind of compound Draft's
  `Shape2DView` produces, so a TechDraw `DrawProjGroupItem` keeps using it as
  `Source` unchanged.
- **Reads**: `Base` (the plane: `Objects`, the cut volume from its `Shape`,
  `Placement`, `Clip`, `Depth`), plus `ProjectionMode`, `FuseArch`,
  `OnlySolids`, `VisibleOnly`, `ExclusionNames`, `AutoUpdate` — and one new
  flag, **`PartOutlines`** (default on): draw ArchPlus parts as their cached
  plan outline.
- **Per object**: a library part with `PartOutlines` on contributes its cached
  outline — no `cut`, no projection; everything else is cut
  (`Arch.getCutVolume`) and projected exactly as Draft does.
- **Substitution conditions** — the outline is used only when it cannot change
  the drawing: the view projects along +Z, the part's rotation is about Z, and
  the cut plane does not pass through the part's height. Anything else, or a
  part failing its self-check, projects its solid (today's drawing).
- **No FreeCAD module is patched.** Everything is public API calls of the kind
  ArchPlus already makes: `Draft.getType`, `groups.get_group_contents`,
  `Arch.getCutVolume`, `Part`, `TechDraw.projectEx`, `TechDraw.findOuterWire`.

## Adoption

A command converts a selected Draft `Shape2DView`: it copies `Base` and the
settings, creates the ArchPlus view, re-points every TechDraw view whose
`Source` referenced the old one, and removes the old one **only after every
re-point succeeded**. One view at a time, so a converted view can be compared
against an unconverted one.

Converting a view **renumbers it** — the furniture's edges are replaced by its
outline — so the dimensions measuring that view need re-picking once. Measured
on the 50-object view: the wall edges keep their indices (Draft fuses the walls
first, so the first 104 indices are unchanged) while 535 of the first 639
shift, and the view ends up roughly a third smaller.

The command refuses to convert a view whose settings it does not reproduce
(`HiddenLines`, `Tessellation`, `InPlace`, `Clip`, `Depth`, `ExclusionPoints`,
or a `ProjectionMode` other than `Solid`), naming the setting — a converted
view can never silently draw differently.

## Expected payoff, and what it is not

- The parts are **~70 % of the section views' cost** (measured by removing
  them: 2.44 → 0.71 s and 3.63 → 0.71 s on the two planes that list parts
  directly), and their per-object `cut` disappears with the outlines, so expect
  the four views **~13 s → ~4–5 s**.
- The drawings shrink by **roughly a third**: the 50-object view's parts
  contribute ~900 of its 1833 edges and their outlines bring back ~300, so
  ~1833 → ~1250. The redraw should improve by more than that ratio, because
  the measured relationship is superlinear — a 2.9× smaller drawing gave a
  4.5× faster redraw — so **~1.5–2×** is the honest expectation, and the
  acceptance measurement settles it.
- It is **not** the 4.5× the crude blocks showed: that came from a 2.9×
  smaller drawing (1833 → 639), which is a different, less faithful outline.
- The redraw remains the larger half of the freeze, and the levers that remove
  it are configuration, not this feature: `DrawPage.KeepUpdated = False` while
  modelling, plus not displaying the section views (measured 180 → 21 → 0.12 s).
  Deferred here, documented for the user.

## Rejected approaches, with the measurements

- **Patch Draft's `Shape2DView._get_shapes`.** Touches no FreeCAD *file*, but
  changes Draft's behaviour from outside — ruled out by the project's rule that
  FreeCAD code is not touched.
- **Companion outline objects** (one hidden outline object per part, which
  Draft's view would pick up). No patching, but `ExclusionNames` cannot reach
  group-listed objects, so the planes would have to become explicit lists
  ArchPlus maintains (a new wall would silently go missing) or the furniture
  would have to leave the level groups.
- **Caching the exact projection instead** (drawing-preserving: verified
  idempotent, 23 of 23 types reproduce edge for edge). A view's cost tracks the
  drawing's edge count, which stays identical, so it buys little and cannot
  touch the redraw by construction.
- **Building the silhouette from the projected faces.** King-bed 79 → 16 edges,
  but **5 of 23 types produced no closed outline at all**, and the desk came
  out as a 23 mm² sliver.
- **The shadow of the up-facing faces** (flattened and fused). Usable on all
  23, but *bigger* than the solid's own drawing (bed 124 edges vs 79), and
  `removeSplitter` did not merge it.
- **Peeling every boundary loop** with `findOuterWire`. Keeps the internal
  loops too (bed 48 edges vs 16), so the drawing grows instead of shrinking.

## Out of scope (deferred, deliberately)

- **The freeze-drawings toggle** (`DrawPage.KeepUpdated`, the section views'
  `AutoUpdate`, their 3D visibility). It is the lever for the freeze itself and
  a separate decision.
- **Outlines for non-plan views.** The cache is a plan projection; elevations
  and sections project their solids.
- **Per-part switches** (outline / block / none per manifest).
- **`ProjectionMode` other than Solid**, `HiddenLines`, `Tessellation`,
  `Clip`/`Depth`, `InPlace`, `ExclusionPoints`.
- **The level compounds** (27 MB of the 56 MB file) and the load/save cost they
  cause.
- **The lowercase duplicate claims** (`edge10`, `edge23`) that print a
  "Claim on missing edge" warning on every recompute.

## Verification

- **Acceptance** (`archplus/freecad_tests/`): our view's walls and openings
  geometry is identical to Draft's for the same plane; every part's drawn
  geometry lies within its outline; the outlines' edges are present.
- **Fallbacks**: a part straddling the cut plane, a part rotated about X, a
  non-plan projection direction, and a part whose outline fails the self-check
  each project their solids.
- **Cache**: computed once per part and reused across views and after a move;
  dropped when a part's parameters change. Asserted as *work skipped*, not as
  wall-clock time.
- **Convert command**: converts, re-points the TechDraw `Source`, removes the
  old view; refuses a wrong selection and unsupported settings.
- **Pure unit tests** for the validity rules over plain data (direction,
  rotation axis, cut straddle, self-check decision), using the existing
  `conftest.py` fakes.
- **The real document**: convert one view, then measure the section views'
  `execute` and the redraw before and after — the honest payoff number, since
  the ~4–5 s estimate is assembled from measured pieces rather than measured
  end to end.
- Existing suites: headless pytest, and the `archplus/freecad_tests` modules
  that touch placed parts, walls and doors.
