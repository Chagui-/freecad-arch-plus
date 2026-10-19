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
  An outline riding in the same compound keeps its occlusion against the walls
  — and against the floor slabs under it: it is extruded over the part's own
  height at the part's own z, so what hides the part hides its outline too. The
  first measurement of the compound change got that wrong (a 1 mm slab in the
  projection plane, hidden by the level-2 planes' floor slabs: 15/15, 21/21 and
  28/28 furniture outlines gone from those three views, which the height fixes).
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
3. `Part.Face(wire)`, extruded from the part's own base over the part's own
   height — a solid prism, so it survives `OnlySolids` and behaves like a
   solid through `cut` and `projectEx`, and so that what hides the part hides
   its outline: hidden-line removal works in depth, and a flat slab in the
   projection plane would be hidden by whatever the part stands on.

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
- **Lazily** on the first ask by a view, keyed by the part's *placed* shape —
  its hash plus its face count and rounded volume, computed on the ask rather
  than recorded at rebuild — and dropped when that shape or its placement
  changes, so a moved part is re-outlined at its new position. (The cached
  outline is in world coordinates, so a key that ignored the placement would
  hand a moved part an outline at its old position.) One-off ~8 s for all 84
  parts on a full rebuild; 10–30 ms per changed part afterwards — against
  ~13 s of section-view work on *every* recompute today.

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
  the part lies wholly inside the band the cut keeps — below the section plane,
  and above `plane_z - Depth` when the plane sets a Depth. A part the plane cuts
  through, one wholly above it that the cut removes altogether, and one under
  that floor all draw their solid. Anything else, or a part failing its
  self-check, projects its solid (today's drawing).
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
(`HiddenLines`, `Tessellation`, `Clip`, `ExclusionPoints`, or a
`ProjectionMode` other than `Solid`), naming the setting — a converted
view can never silently draw differently. `InPlace` and `Depth` are not
among them: `InPlace` only means anything in the Cutlines/Cutfaces modes,
which the projection mode already refuses, and `Depth` is the *section
plane's* property, honoured as Draft honours it, not one a view can set.

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
  `Clip`, `ExclusionPoints`. (`InPlace` and `Depth` are not in this list: the
  former is inert in Solid mode, the latter is the section plane's own
  property and is honoured.)
- **The level compounds** (27 MB of the 56 MB file) and the load/save cost they
  cause.
- **The lowercase duplicate claims** (`edge10`, `edge23`) that print a
  "Claim on missing edge" warning on every recompute.

## Verification

- **Acceptance** (`archplus/freecad_tests/`): our view's walls and openings
  geometry is identical to Draft's for the same plane; every part's drawn
  geometry lies within its outline; the outlines' edges are present.
- **Fallbacks**: a part straddling the cut plane, a part wholly above it (the
  cut removes it altogether), a part rotated about X, a non-plan projection
  direction, and a part whose outline fails the self-check each project their
  solids.
- **Cache**: computed once per part and reused across views and while the part
  is not changed; dropped when the part's shape or placement changes, so a
  move re-outlines the moved part (the key is taken from `obj.Shape`, which
  carries the placement). Asserted as *work skipped*, not as wall-clock time.
- **Convert command**: converts, re-points the TechDraw `Source`, removes the
  old view; refuses a wrong selection and unsupported settings.
- **Pure unit tests** for the validity rules over plain data (direction,
  rotation axis, the part lying wholly below the cut, self-check decision),
  using the existing `conftest.py` fakes.
- **The real document**: convert one view, then measure the section views'
  `execute` and the redraw before and after — the honest payoff number, since
  the ~4–5 s estimate is assembled from measured pieces rather than measured
  end to end.
- Existing suites: headless pytest, and the `archplus/freecad_tests` modules
  that touch placed parts, walls and doors.

## Addendum (2026-10-18): the substitute is the drawing, not the outline

The outline above shipped and was rejected on sight: in a plan cut, furniture
read as bounding boxes. From above a bed, a wardrobe or a sofa *is* a
rectangle, so the filled outer boundary drops exactly what makes the drawing
read as a room - the mattress and pillows, the door seams, the seat.

The substitute is now the part's cached **plan drawing**:

- the same visible projection the outline used, laid flat at the part's own
  top, minus the edges the boundary prism already draws;
- plus the boundary extruded as a prism from the part's base to one millimetre
  below its top, so the hidden-line pass still treats the substitute as the
  part: what hides the part hides it (a chair under a table, substituted or
  not) and what the part hides stays hidden.

Measured over the 36 library part types (edges a view then draws): **985** for
the solids, **887** for the drawings, **448** for the footprints that shipped.
So fidelity is nearly free in edge count - the earlier "inner loops are three
times the footprint" figure was the king bed alone, not the rule (loops in
aggregate: 885 of 985) - and the saving that remains is the parts' `cut` and
their place in the per-view hidden-line pass, not the drawing's size.

Correctness is asserted as *line coverage* in both directions
(`verify_sections._draws_the_same_lines`), not edge identity: the boundary
prism's wire splits a long boundary edge into pieces, so 14 of 41 measured
fixtures draw the same lines with some edges split. Nothing is ever missing
(0 missing of 1001 drawn edges) and no line is added (all 59 extra edges lie
on a line the solid already draws).

The footprint's other costs went with it: a part whose drawing has two
separate outlines (the waste bin) no longer falls back to its solid - both
outlines are drawn - and a hairline footprint no longer refuses its drawing.
What it still saves is the view's own execute, and the saving scales with how
much of the view is furniture. Measured on a crafted room (4 walls, a slab, a
1400 plane), the view rebuilds in **0.14 s** against **0.25 s** with 10 library
parts (45%) and in **0.68 s** against **4.50 s** with all 37 part types (85%),
on drawings of 781 against 766 edges. The redraw half is unchanged by
construction: it tracks the drawing's edge count, and the drawing now has the
solids' edges - that half is governed by configuration (`DrawPage.KeepUpdated`,
the views' 3D visibility, `AutoUpdate`), not by what the parts are substituted
with.

The cache is unchanged: keyed on the part's placed shape (hash, face count,
rounded volume), so a rebuild or a move re-draws it.
