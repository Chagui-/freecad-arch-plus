# Section Outlines Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A placed library part contributes its cached plan outline instead of
its solid to a section view, so the drawing is built from a fraction of the
edges and every stage that scales with edges gets cheaper.

**Architecture:** One new geometry helper (`common/geometry.py`) computes a
part's plan outline by projecting its solid with the same hidden-line call
Draft uses and taking TechDraw's own outer-wire extractor over the result, as
a thin slab; the parts library caches it per placed part; and a new
ArchPlus-owned section view replaces Draft's `Shape2DView` one view at a time,
substituting each part's outline for its solid only when that cannot change the
drawing. No FreeCAD module is patched — only public API calls.

**Tech Stack:** Python 3, FreeCAD 1.1 (`Part`, `Draft`, `TechDraw`, `FreeCAD`),
PySide6 for the command, `pytest` for pure logic, `archplus/freecad_tests`
scripted verification inside FreeCAD for anything that touches geometry.

**Spec:** `docs/superpowers/specs/2026-10-10-section-outlines-design.md`

## Global Constraints

- FreeCAD 1.1. The reference behaviour is
  `Mod/Draft/draftobjects/shape2dview.py`; read it, mirror it, never modify it.
- `archplus/tools/*/gui.py` and `archplus/common/widgets.py` must not import
  `Part`, `Sketcher`, `ArchComponent`, `Arch`, `Draft` or
  `archplus.common.geometry` at module scope — enforced by
  `archplus/common/tests/test_lazy_imports.py`. Import them inside functions.
- Pure logic (no FreeCAD) lives in a `model.py`-style module, the walls
  precedent (`archplus/tools/walls/model.py`).
- Every new file starts with `# SPDX-License-Identifier: LGPL-2.1-or-later`
  and a comment saying why the file exists.
- Headless tests: `python3 -m pytest -q` from the repo root (556 tests pass on
  this branch before any change).
- FreeCAD tests: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe"
  archplus/freecad_tests/run_all.py` — delete
  `%TEMP%\archplus_verify.marker` first, or it skips the run.
- Commit messages are imperative sentences, no `feat:`/`fix:` prefixes (the
  repo's own style).
- The user's live document is NOT a test fixture. Never open, edit or save it;
  the real-document measurement in Task 7 is the only step that touches it, and
  it is explicitly opt-in.

## Review Focus

The five inputs most likely to bite a user of this feature, each pinned to a
test in the task that owns the code:

1. **A part whose plan projection has two separate outlines** (the waste-bin):
   `findOuterWire` returns one loop, so the outline would silently drop the
   other → Task 1 (`_covers` rejects it, the part keeps its solid) and Task 5
   (the view falls back for it).
2. **A part the section plane cuts through** (a floor-to-ceiling wardrobe in a
   plan cut at 1400): the outline is flat at the part's base, so it would draw
   the whole footprint where the solid draws a slice → Task 3 (`cut_straddles`)
   and Task 5 (the view projects the solid).
3. **A part rotated about X or Y** (not about Z): its local plan projection is
   not its placed one → Task 3 (`rotation_is_about_z`) and Task 5.
4. **A view converted without its Placement** (the user arranged the four views
   on the page at offsets like `(10856, 0, 0)`): the drawing would jump to the
   model's own coordinates → Task 6 (the convert command copies Placement, and
   the check asserts the converted view's shape bbox matches the old one's).
5. **A view whose settings the new object does not reproduce** (`HiddenLines`,
   `Tessellation`, `Clip`, `Depth`, `InPlace`, `ExclusionPoints`, a
   `ProjectionMode` other than `Solid`): silently converting it would draw
   something different → Task 6 (the command refuses, naming the setting).

Also pinned: an empty or `None` `Base`, a plane whose `Objects` list is empty,
and a part whose outline cannot be computed at all — all three must leave the
view with an empty (not stale) shape or fall back to the solid, never raise
into the recompute (Task 4, Task 5).

---

## File Structure

| File | Responsibility |
|---|---|
| `archplus/common/geometry.py` (modify) | Add `plan_outline(shape)`: a shape's plan outline as a thin slab, or `None` when it cannot be trusted. The FreeCAD-side geometry helper — the repo's existing lazy-import boundary. |
| `archplus/tools/partslib/object.py` (modify) | Add `_LibraryPart.planOutline(obj)`: the per-part cache in front of `plan_outline`. |
| `archplus/tools/sections/__init__.py` (create) | Package marker, empty like its siblings. |
| `archplus/tools/sections/model.py` (create) | Pure rules: is the view a plan, is the rotation about Z, does the cut straddle the part, and the decision that combines them. No FreeCAD imports. |
| `archplus/tools/sections/object.py` (create) | `_SectionView` proxy (properties, `execute`, `_build`), the factory `makeSectionView`. Mirrors Draft's `execute` for the parts it is not substituting. |
| `archplus/tools/sections/gui.py` (create) | The convert command and its registration. Lazy imports only. |
| `archplus/tools/sections/tests/__init__.py`, `tests/test_model.py` (create) | Headless unit tests for the pure rules. |
| `archplus/freecad_tests/verify_sections.py` (create) | The FreeCAD checks: outline geometry, cache behaviour, the view's equivalence to Draft's, the fallbacks, the convert command. |
| `archplus/freecad_tests/run_all.py` (modify) | Register the new module. |
| `InitGui.py` (modify) | Menu-only entry for the convert command. |
| `docs/TOOLS.md` (modify) | A section for the tool. |

Task order follows dependency: 1 (geometry) → 2 (cache) → 3 (rules) → 4 (view,
non-part path) → 5 (outline substitution) → 6 (convert command) → 7 (docs and
the real-document measurement). Tasks 4 and 5 depend on 1–3; task 6 depends on
4 and 5.

---

### Task 1: The plan outline geometry

**Files:**
- Modify: `archplus/common/geometry.py`
- Create: `archplus/freecad_tests/verify_sections.py`
- Modify: `archplus/freecad_tests/run_all.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `plan_outline(shape, thickness=1.0) -> Part.Shape | None` in
  `archplus.common.geometry` — a flat outline slab at z = 0 in the shape's own
  frame, or `None` when the outline cannot be trusted. Task 2 calls it; Tasks 4
  and 5 consume its result.

- [ ] **Step 1: Write the failing check**

Create `archplus/freecad_tests/verify_sections.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section-view checks. Run inside a FreeCAD GUI session.
#
# A section view draws library parts as their cached plan outline instead of
# their solid. The outline is an optimisation, never a wrong drawing: it is
# used only when it covers everything the solid's own drawing shows, and this
# module is where that claim is tested - on a real part, a part the cut passes
# through, a part rotated off-plan, and against Draft's own view, which must
# keep drawing the walls identically.

import FreeCAD
import Part

from archplus.common import geometry as common_geometry
from archplus.freecad_tests import _harness as h


def _a_part():
    """One placed library part with a real shape."""
    from archplus.tools.partslib import object as pobj

    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", "OutlinePart")
    pobj._LibraryPart(obj)
    obj.Shape = Part.makeBox(600, 400, 700)
    return obj


def _visible_edges(shape, direction=None):
    """The edges Draft's getProjected keeps, as comparable tuples."""
    import TechDraw

    direction = direction or FreeCAD.Vector(0, 0, 1)
    groups = TechDraw.projectEx(shape, direction)
    out = []
    for group in groups[0:5]:
        if group.isNull():
            continue
        for edge in group.Edges:
            a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
            out.append(tuple(sorted(((round(a.x, 3), round(a.y, 3), round(a.z, 3)),
                                     (round(b.x, 3), round(b.y, 3), round(b.z, 3))))))
    return set(out)


def run():
    doc = h.fresh_doc("ArchPlusSections")
    part = _a_part()

    outline = common_geometry.plan_outline(part.Shape)
    h.check("a box gets an outline", outline is not None)
    h.check("the outline is a 1mm slab", outline is not None
            and abs(outline.BoundBox.ZLength - 1.0) < 1e-6
            and outline.Volume > 0)
    # Counted on the *drawing*, not the raw shapes: the slab's own edges are
    # three times its silhouette's (top loop, bottom loop, 1mm verticals), so
    # a raw count would say nothing about what a view has to draw.
    h.check("the outline draws no more edges than the solid",
            len(_visible_edges(outline)) <= len(_visible_edges(part.Shape)))

    # The outline is the filled outer boundary: a loop nested inside it (a
    # smaller block on top of a bigger one) is dropped on purpose, not
    # refused. Reproducing it was measured bigger than the solid's own
    # drawing, which is the thing this feature exists to shrink.
    nested = Part.makeCompound([Part.makeBox(600, 400, 300),
                                Part.makeBox(300, 200, 300,
                                             FreeCAD.Vector(150, 100, 300))])
    nested_outline = common_geometry.plan_outline(nested)
    h.check("a nested loop is dropped, not refused",
            nested_outline is not None
            and len(_visible_edges(nested_outline)) == 4)

    # A projection too small to be a usable outline is refused.
    h.check("a hairline projection gets no outline",
            common_geometry.plan_outline(Part.makeBox(0.5, 0.5, 10)) is None)

    # A shape with two separate outlines: the outer wire is one of them, so
    # the other reaches outside the outline and it must be refused.
    two = Part.makeCompound([Part.makeBox(400, 400, 300),
                             Part.makeBox(400, 400, 300,
                                          FreeCAD.Vector(2000, 0, 0))])
    h.check("a two-outline shape gets no outline",
            common_geometry.plan_outline(two) is None)

    # An empty shape is refused rather than raising.
    h.check("an empty shape gets no outline",
            common_geometry.plan_outline(Part.Shape()) is None)

    FreeCAD.closeDocument(doc.Name)
    return h.failures()
```

- [ ] **Step 2: Register it and run it to verify it fails**

In `archplus/freecad_tests/run_all.py`, add the import beside the others:

```python
from archplus.freecad_tests import verify_sections
```

and the run line after `verify_part_colours`:

```python
    _run_one("verify_sections", verify_sections.run)
```

Run (delete the marker first, or the run is skipped):

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: `FAIL` lines for the outline checks — `plan_outline` does not exist
yet, so the module raises `AttributeError` and `run_all` reports
`CRASH in verify_sections`.

- [ ] **Step 3: Implement `plan_outline`**

In `archplus/common/geometry.py`, append (module scope already imports `Part`,
which is what this file exists for):

```python
def plan_outline(shape, thickness=1.0):
    """The plan outline of `shape` as a thin slab, or None.

    The outline is what a section view may draw instead of the part's solid:
    the **filled outer boundary** of the shape's plan drawing. It is built by
    projecting the shape with the same hidden-line call Draft's Shape2DView
    uses, taking TechDraw's own outer-wire extractor over the result, and
    extruding that face a hair - a slab, not a bare wire, because OnlySolids
    views and the section cut both drop non-solid geometry.

    What it deliberately does not reproduce: loops nested inside the outer
    boundary - a smaller block on top of a bigger one, a table's top over its
    pedestal, a hole through a part. There the drawing is a filled footprint.
    Reproducing every loop was measured *bigger* than the solid's own drawing
    (the bed: 48 edges against 16), which is the opposite of what this
    feature exists to do. docs/TOOLS.md says the same to the user.

    Returns None whenever the outline cannot be trusted: no geometry, no
    outer wire, a degenerate face, or a shape whose own drawing reaches
    *outside* the outer wire (a part with two separate outlines, like a
    waste bin with an overhanging lid). Callers then draw the solid, which
    is always right and merely slower.

    A view drawing this value draws its silhouette - the face it was
    extruded from, which sits in the projection plane (z = 0) where Draft's
    own projected edges sit.
    """
    import TechDraw
    from FreeCAD import Vector

    if shape is None or shape.isNull() or not shape.Faces:
        return None
    try:
        groups = TechDraw.projectEx(shape, Vector(0, 0, 1))
    except Exception:
        return None
    drawn = [e for g in groups[0:5] if not g.isNull() for e in g.Edges]
    if not drawn:
        return None
    try:
        wire = TechDraw.findOuterWire(drawn)
    except Exception:
        return None
    if wire is None:
        return None
    try:
        face = Part.Face(wire)
    except Exception:
        return None
    if face.isNull() or face.Area <= 1.0:
        return None
    if not _covers(face, drawn):
        return None
    return face.extrude(Vector(0, 0, thickness))


def _covers(face, drawn, tolerance=0.5):
    """True when the shape's own drawing stays inside `face`.

    Containment, not equality: a loop nested inside the face is covered, and
    dropping it is the documented simplification (see plan_outline). What
    this rejects is a drawing that reaches *outside* the outline.
    """
    for edge in drawn:
        for vertex in edge.Vertexes:
            try:
                distance = Part.Vertex(vertex.Point).distToShape(face)[0]
            except Exception:
                return False
            if distance > tolerance:
                return False
    return True
```

- [ ] **Step 4: Run the checks to verify they pass**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: every `verify_sections` check `PASS`, and the run's summary reports
`0 check(s) failed` (the other modules are unaffected).

- [ ] **Step 5: Commit**

```
git add archplus/common/geometry.py archplus/freecad_tests/verify_sections.py archplus/freecad_tests/run_all.py
git commit -m "Give a shape its plan outline, and refuse the ones that cannot be trusted"
```

---

### Task 2: The per-part outline cache

**Files:**
- Modify: `archplus/tools/partslib/object.py` (class `_LibraryPart`)
- Modify: `archplus/freecad_tests/verify_sections.py`

**Interfaces:**
- Consumes: `plan_outline(shape, thickness=1.0)` from Task 1.
- Produces: `_LibraryPart.planOutline(obj) -> Part.Shape | None` — the cached
  outline for a placed part, or `None` when it has none. Task 5 calls it
  through `part.Proxy.planOutline(part)`.

- [ ] **Step 1: Write the failing check**

Append to `verify_sections.py`'s `run()`, before `closeDocument`:

```python
    from archplus.tools.partslib import object as pobj

    proxy = part.Proxy
    first = proxy.planOutline(part)
    h.check("a placed part answers with an outline", first is not None)
    h.check("the outline is cached, not rebuilt",
            proxy.planOutline(part) is first)
    before = proxy._outline_key
    part.Shape = Part.makeBox(900, 400, 700)
    h.check("a rebuild drops the cache", proxy.planOutline(part) is not first)
    h.check("the new outline is cached too",
            proxy.planOutline(part) is proxy.planOutline(part))
    h.check("the key followed the rebuild", proxy._outline_key != before)

    empty = pobj._LibraryPart.__new__(pobj._LibraryPart)
    h.check("a part with no shape answers None",
            empty.planOutline(Part.Shape()) is None)
```

- [ ] **Step 2: Run it to verify it fails**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: `FAIL` — `_LibraryPart` has no `planOutline`.

- [ ] **Step 3: Implement the cache**

In `archplus/tools/partslib/object.py`, add to `_LibraryPart` (after
`_resolveCurrent`):

```python
    def planOutline(self, obj):
        """The part's cached plan outline (a thin slab), or None.

        What a section view draws instead of the solid. Computed on the first
        ask and kept until the part rebuilds, keyed by the shape it was built
        from, because the projection costs 10-30ms and a view asks on every
        recompute.

        None means "no outline to be had" - no shape, or a projection whose
        outer wire does not cover the part's own drawing (see
        common.geometry.plan_outline). The caller then draws the solid, which
        is always correct and merely slower, so a failure here must never
        raise.
        """
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull() or not shape.Faces:
            return None
        key = (shape.hashCode(), len(shape.Faces), round(shape.Volume, 3))
        if getattr(self, "_outline_key", None) == key:
            return self._outline
        from archplus.common import geometry as common_geometry

        outline = None
        try:
            outline = common_geometry.plan_outline(shape)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: cannot outline %s (%s); drawing its solid\n"
                % (obj.Label, exc))
        self._outline = outline
        self._outline_key = key
        return outline
```

- [ ] **Step 4: Run the checks to verify they pass**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: all `verify_sections` checks `PASS`, `0 check(s) failed`.

- [ ] **Step 5: Run the headless suite to make sure nothing else moved**

```
python3 -m pytest -q
```

Expected: `556 passed`.

- [ ] **Step 6: Commit**

```
git add archplus/tools/partslib/object.py archplus/freecad_tests/verify_sections.py
git commit -m "Cache each placed part's plan outline until it rebuilds"
```

---

### Task 3: The pure substitution rules

**Files:**
- Create: `archplus/tools/sections/__init__.py`
- Create: `archplus/tools/sections/model.py`
- Create: `archplus/tools/sections/tests/__init__.py`
- Create: `archplus/tools/sections/tests/test_model.py`

**Interfaces:**
- Consumes: nothing (plain data in, plain answers out).
- Produces: `is_plan_direction(direction)`, `rotation_is_about_z(axis, angle)`,
  `cut_straddles(z_min, z_max, plane_z)` and
  `use_outline(z_range, plane_z, direction, axis, angle) -> bool`, all in
  `archplus.tools.sections.model`. Task 5 calls `use_outline`.

- [ ] **Step 1: Write the failing tests**

Create `archplus/tools/sections/__init__.py` and
`archplus/tools/sections/tests/__init__.py` (both empty, matching the sibling
tools), then `archplus/tools/sections/tests/test_model.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The rules that decide whether a part's cached outline may stand in for its
# solid. Pure data, so they are testable without FreeCAD - which matters,
# because each one is a way a drawing could come out wrong: a view that is not
# a plan, a part rotated off plan, and a part the cut plane passes through.

from archplus.tools.sections import model


def test_plan_direction_is_z():
    assert model.is_plan_direction((0.0, 0.0, 1.0))
    assert not model.is_plan_direction((0.0, 1.0, 0.0))
    assert not model.is_plan_direction((0.0, 0.0, -1.0))


def test_a_z_rotation_keeps_the_plan_projection():
    assert model.rotation_is_about_z((0.0, 0.0, 1.0), 1.5707963)
    assert model.rotation_is_about_z((0.0, 0.0, 1.0), 0.0)


def test_an_off_axis_rotation_does_not():
    assert not model.rotation_is_about_z((1.0, 0.0, 0.0), 0.5)
    assert not model.rotation_is_about_z((0.0, 1.0, 0.0), 0.5)


def test_only_a_part_below_the_cut_is_whole():
    # Through the part: the solid would be sliced.
    assert not model.part_is_below_the_cut(2400.0, 1400.0)
    # Wholly above: the cut removes it from the drawing entirely, so a
    # footprint there would be a part the drawing does not have.
    assert not model.part_is_below_the_cut(3900.0, 1400.0)
    # Wholly below: untouched, and drawn as its plan silhouette.
    assert model.part_is_below_the_cut(3900.0, 4200.0)
    # Top exactly at the plane: the cut takes only what is above it.
    assert model.part_is_below_the_cut(3900.0, 3900.0)


def test_a_plan_cut_through_a_part_refuses_its_outline():
    # A floor-standing wardrobe under a 1400mm plan cut: the solid is sliced,
    # a flat outline at its base would not be.
    assert not model.use_outline((0.0, 2400.0), 1400.0,
                                 (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 0.0)
    # A wall cabinet above the same cut: the cut removes its solid outright,
    # so a footprint would be a part the drawing does not have.
    assert not model.use_outline((1500.0, 2100.0), 1400.0,
                                 (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 0.0)


def test_a_part_below_the_cut_uses_its_outline():
    assert model.use_outline((3000.0, 3900.0), 4200.0,
                             (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 0.0)


def test_an_off_axis_rotation_refuses_the_outline():
    assert not model.use_outline((3000.0, 3900.0), 4200.0,
                                 (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.5)


def test_an_elevation_refuses_the_outline():
    assert not model.use_outline((3000.0, 3900.0), 4200.0,
                                 (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.0)
```

- [ ] **Step 2: Run the tests to verify they fail**

```
python3 -m pytest archplus/tools/sections/tests/test_model.py -q
```

Expected: an import failure for the missing module —
`ImportError: cannot import name 'model' from 'archplus.tools.sections'` (the
package `__init__.py` from Step 1 imports fine; it is the submodule that is
absent).

- [ ] **Step 3: Implement the rules**

Create `archplus/tools/sections/model.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section view rules - plain data only.
#
# Whether a part's cached plan outline may stand in for its solid is a
# question about numbers: which way the view projects, how the part is
# rotated, and where the cut plane sits against the part's height. Kept free
# of FreeCAD imports so each rule is testable headlessly, and so a wrong
# answer is caught by a unit test rather than by a drawing that looks subtly
# off. Do not add FreeCAD, Part or PySide dependencies here.

TOLERANCE = 1e-6


def is_plan_direction(direction, tolerance=TOLERANCE):
    """True when a view projects along +Z, i.e. it is a plan cut."""
    x, y, z = direction
    return abs(x) <= tolerance and abs(y) <= tolerance \
        and abs(z - 1.0) <= tolerance


def rotation_is_about_z(axis, angle, tolerance=TOLERANCE):
    """True when a placement's rotation leaves the plan projection alone.

    A part rotated about Z still projects to the same outline from above; one
    tilted about X or Y does not, and must be drawn as its solid.
    """
    if abs(angle) <= tolerance:
        return True
    return abs(axis[0]) <= tolerance and abs(axis[1]) <= tolerance


def part_is_below_the_cut(z_max, plane_z, tolerance=TOLERANCE):
    """True when the section plane leaves the part whole.

    The cut removes everything above the plane - that is what makes a plan a
    plan - so a part reaching above it is drawn differently: a sliced one
    shows its section, and one wholly above is removed from the drawing
    altogether. Neither is its footprint, so neither may take an outline.
    Only a part wholly below the plane is drawn as its plan silhouette.
    """
    return z_max <= plane_z + tolerance


def use_outline(z_range, plane_z, direction, axis, angle):
    """Whether a part's cached outline may stand in for its solid.

    All three conditions must hold: the view is a plan, the part is not
    rotated off plan, and the part lies below the cut. Anything else draws
    the solid, which is what the view drew before this feature.
    """
    return (is_plan_direction(direction)
            and rotation_is_about_z(axis, angle)
            and part_is_below_the_cut(z_range[1], plane_z))
```

- [ ] **Step 4: Run the tests to verify they pass**

```
python3 -m pytest archplus/tools/sections/tests/test_model.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Commit**

```
git add archplus/tools/sections/__init__.py archplus/tools/sections/model.py archplus/tools/sections/tests/__init__.py archplus/tools/sections/tests/test_model.py
git commit -m "Decide when a part's outline may stand in for its solid"
```

---

### Task 4: The section view, drawing exactly what Draft draws

**Files:**
- Create: `archplus/tools/sections/object.py`
- Modify: `archplus/freecad_tests/verify_sections.py`

**Interfaces:**
- Consumes: nothing from Tasks 1–3 yet (this task draws every object as its
  solid; Task 5 adds the outlines).
- Produces: `makeSectionView(doc=None, base=None, name="SectionView") ->
  Part::FeaturePython` and the proxy `_SectionView` with `setProperties(obj)`,
  `execute(obj)` and `_build(obj)`. Task 6 calls `makeSectionView` and copies
  settings onto the returned object.

- [ ] **Step 1: Write the failing check**

While you are in the file, align its header comment with the contract
`plan_outline` now states: the outline is the shape's **filled outer boundary**
and is used when the solid's own drawing stays *inside* it — the header
currently says "covers everything the solid's own drawing shows", which reads
as the equality contract that was ruled out (reproducing every loop draws more
edges than the solid). This is also the step where the header's other promise
("and against Draft's own view") becomes true.

Append to `verify_sections.py` (a new helper plus checks inside `run()`):

```python
def _walls_and_plane(doc):
    """A wall on a sketch, and a section plane through it - the smallest
    document whose section view has real geometry."""
    import Sketcher

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                                        FreeCAD.Vector(4000, 0, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(4000, 0, 0),
                                        FreeCAD.Vector(4000, 3000, 0)), False)

    from archplus.tools.walls import object as wobj

    wall = wobj.makeWall(doc, sketch=sketch)
    plane = doc.addObject("App::FeaturePython", "Section")
    import ArchSectionPlane

    ArchSectionPlane._SectionPlane(plane)
    # The wall root has no shape of its own - its segments carry the geometry
    # - and Draft's gather does not descend into an ArchPlus wall root: the
    # root is not a Draft group, so `walls=True` does not make it one. A
    # section plane therefore has to reference the segments, which is what the
    # real documents do. Referencing the root alone leaves Draft's own view
    # raising IndexError on its empty material bucket, and this fixture would
    # compare two empty drawings.
    plane.Objects = list(wall.Group)
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    doc.recompute()
    return wall, plane
```

and in `run()`:

```python
    wall, plane = _walls_and_plane(doc)

    # Draft's own view, as the reference behaviour.
    reference = doc.addObject("Part::Part2DObjectPython", "Reference")
    import draftobjects.shape2dview as s2v

    s2v.Shape2DView(reference)
    reference.Base = plane
    reference.ProjectionMode = "Solid"
    doc.recompute()

    from archplus.tools.sections import object as sobj

    # Compared with the same settings set explicitly on both, rather than by
    # relying on the two objects defaulting alike.
    view = sobj.makeSectionView(doc, base=plane)
    view.FuseArch = True
    reference.FuseArch = True
    doc.recompute()

    h.check("the new view draws something", len(view.Shape.Edges) > 0)
    h.check("the new view draws exactly what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    h.check("the view keeps its own placement",
            view.Placement.Base == FreeCAD.Vector(0, 0, 0))

    # A fresh view must default to what a fresh Draft view defaults to, or
    # converting a view would change its drawing by the act of converting.
    fresh_reference = doc.addObject("Part::Part2DObjectPython", "FreshReference")
    s2v.Shape2DView(fresh_reference)
    fresh = sobj.makeSectionView(doc)
    h.check("a fresh view defaults like Draft's",
            fresh.FuseArch == fresh_reference.FuseArch
            and fresh.OnlySolids == fresh_reference.OnlySolids
            and fresh.VisibleOnly == fresh_reference.VisibleOnly
            and fresh.ProjectionMode == fresh_reference.ProjectionMode)

    # A clipping plane does not clip here either: Draft declares Clip on the
    # view itself (default False), so its Base.Clip branch is dead code.
    plane.Clip = True
    doc.recompute()
    h.check("a clipping plane draws what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    plane.Clip = False
    doc.recompute()

    # With the fuse off, still exactly what Draft draws with it off: this is
    # the only path that ever runs that branch on a converted view whose
    # FuseArch is false.
    view.FuseArch = False
    reference.FuseArch = False
    doc.recompute()
    h.check("with FuseArch off, still what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    view.FuseArch = True
    reference.FuseArch = True
    doc.recompute()

    # Emptying a plane that had geometry must leave an empty shape, not the
    # last one it drew.
    kept = list(plane.Objects or [])
    plane.Objects = []
    doc.recompute()
    h.check("emptying a plane leaves an empty shape",
            view.Shape.isNull() or len(view.Shape.Edges) == 0)
    plane.Objects = kept
    doc.recompute()

    # A plane with nothing to draw leaves an empty shape, not a stale one.
    import ArchSectionPlane

    empty_plane = doc.addObject("App::FeaturePython", "EmptyPlane")
    ArchSectionPlane._SectionPlane(empty_plane)
    bare = sobj.makeSectionView(doc, base=empty_plane)
    doc.recompute()
    h.check("an empty plane draws nothing", bare.Shape.isNull()
            or len(bare.Shape.Edges) == 0)

    # No base at all must not raise into the recompute.
    nothing = sobj.makeSectionView(doc, base=None)
    doc.recompute()
    h.check("no base draws nothing", nothing.Shape.isNull()
            or len(nothing.Shape.Edges) == 0)
```

- [ ] **Step 2: Run it to verify it fails**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: `CRASH in verify_sections` — `archplus.tools.sections.object` does
not exist.

- [ ] **Step 3: Implement the view**

Create `archplus/tools/sections/object.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# ArchPlus section views: a plan cut that draws library parts as their cached
# plan outline instead of their solid.
#
# Why our own object rather than Draft's Shape2DView: the outline has to be
# substituted where the shapes are gathered, and Draft offers no seam there
# (its only per-object call is _get_shapes(shape), which never sees the
# object). Patching Draft was ruled out - this add-on calls FreeCAD's APIs, it
# does not change them. So this view mirrors Draft's Shape2DView.execute for
# the parts it is not substituting: same gathering, same cut, same projection,
# same flags. Where it mirrors, the comment says so.
#
# The projection is the same call Draft makes (TechDraw.projectEx over the
# visible edge groups), which is what makes "the walls draw identically" a
# testable claim rather than a hope.

import FreeCAD

PROP_GROUP = "Section"


class _SectionView:
    def __init__(self, obj):
        obj.Proxy = self
        self.setProperties(obj)

    def setProperties(self, obj):
        """Declare the settings this view reproduces.

        Only the flags whose behaviour is mirrored from Draft are declared -
        a setting that cannot be honoured must not exist, so a converted view
        can never draw something other than what it says.
        """
        pl = obj.PropertiesList
        if "Base" not in pl:
            obj.addProperty("App::PropertyLink", "Base", PROP_GROUP,
                            "The section plane this view cuts through")
        if "ProjectionMode" not in pl:
            obj.addProperty("App::PropertyEnumeration", "ProjectionMode",
                            PROP_GROUP, "How the objects are projected")
            obj.ProjectionMode = ["Solid"]
            obj.ProjectionMode = "Solid"
        if "FuseArch" not in pl:
            obj.addProperty("App::PropertyBool", "FuseArch", PROP_GROUP,
                            "Fuse wall and structure objects of one material")
            # False, as a fresh Draft view's is: this view has to draw what
            # the view it replaces draws, and the convert command copies that
            # view's value across.
            obj.FuseArch = False
        if "OnlySolids" not in pl:
            obj.addProperty("App::PropertyBool", "OnlySolids", PROP_GROUP,
                            "Project solid geometry only")
            obj.OnlySolids = False
        if "VisibleOnly" not in pl:
            obj.addProperty("App::PropertyBool", "VisibleOnly", PROP_GROUP,
                            "Project visible objects only")
            obj.VisibleOnly = False
        if "ExclusionNames" not in pl:
            obj.addProperty("App::PropertyStringList", "ExclusionNames",
                            PROP_GROUP,
                            "Names of objects left out of the projection")
        if "PartOutlines" not in pl:
            obj.addProperty("App::PropertyBool", "PartOutlines", PROP_GROUP,
                            "Draw library parts as their cached plan outline")
            obj.PartOutlines = True
        if "AutoUpdate" not in pl:
            obj.addProperty("App::PropertyBool", "AutoUpdate", PROP_GROUP,
                            "Recompute this view when its inputs change")
            obj.AutoUpdate = True

    def execute(self, obj):
        """Rebuild the view's shape; never raise into the recompute.

        A failure keeps the last good shape and says so, because a stale
        drawing beats a broken document - and a view that raised here would
        take the whole recompute down with it.
        """
        if not getattr(obj, "AutoUpdate", True):
            return
        try:
            shape = self._build(obj)
        except Exception as exc:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: section view '%s' could not rebuild (%s); "
                "keeping the last shape\n" % (obj.Label, exc))
            return
        obj.Shape = shape

    def _build(self, obj):
        import Part

        plane = obj.Base
        if plane is None:
            return Part.makeCompound([])
        direction = plane.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        objs = self._objects(obj, plane)
        shapes = self._shapes(obj, objs)
        return self._project(obj, shapes, plane, direction)

    def _objects(self, obj, plane):
        """The plane's objects, expanded and filtered the way Draft does."""
        from draftutils import groups, gui_utils

        excluded = set(getattr(obj, "ExclusionNames", None) or [])
        objs = [o for o in (getattr(plane, "Objects", None) or [])
                if o.Name not in excluded]
        objs = groups.get_group_contents(objs, walls=True)
        if getattr(obj, "VisibleOnly", False):
            objs = gui_utils.remove_hidden(objs)
        return objs

    def _shapes(self, obj, objs):
        """The shapes to cut and project - Draft's gather, mirrored."""
        import Draft

        onlysolids = bool(getattr(obj, "OnlySolids", False))
        shapes = []
        if getattr(obj, "FuseArch", False):
            # Draft's Shape2DView.execute: wall and structure shapes fuse per
            # material, everything else is projected as it is.
            per_material = {}
            for o in objs:
                shape = getattr(o, "Shape", None)
                if shape is None:
                    continue
                if Draft.getType(o) in ("Wall", "Structure"):
                    material = (o.Material.Name
                                if (hasattr(o, "Material") and o.Material)
                                else "None")
                    per_material.setdefault(material, []).extend(
                        self._sub_shapes(shape, onlysolids))
                else:
                    shapes.extend(self._sub_shapes(shape, onlysolids))
            for group in per_material.values():
                fused = group.pop()
                if group:
                    try:
                        fused = fused.multiFuse(group)
                    except Exception:
                        for other in group:
                            fused = fused.fuse(other)
                    try:
                        fused = fused.removeSplitter()
                    except Exception:
                        pass
                if fused.Solids:
                    shapes.extend(fused.Solids)
                else:
                    shapes.extend(fused.SubShapes)
        else:
            for o in objs:
                shape = getattr(o, "Shape", None)
                if shape is not None:
                    shapes.extend(self._sub_shapes(shape, onlysolids))
        return shapes

    def _sub_shapes(self, shape, onlysolids):
        """Draft's _get_shapes, mirrored."""
        if onlysolids:
            return shape.Solids
        if shape.isNull():
            return []
        if shape.ShapeType == "Compound":
            return shape.SubShapes
        return [shape.copy()]

    def _project(self, obj, shapes, plane, direction):
        """Cut against the section volume, then project - Draft's own two
        steps, in Draft's own order."""
        import Arch
        import Part
        import TechDraw

        cutplane = plane.Shape
        # Draft's resolution, read as its code actually behaves: it declares
        # Clip on the view itself (default False), so its `obj.Base.Clip`
        # branch is dead - Draft's own TODO says as much - and the view's
        # value always wins. This view declares no Clip, and the convert
        # command refuses a view that sets it, so this is False: a clipping
        # plane does not clip here either, exactly as in Draft. Depth *is* the
        # plane's - Draft's Shape2DView has no Depth of its own.
        clip = bool(getattr(obj, "Clip", False))
        depth = getattr(plane, "Depth", None)
        depth = depth.Value if depth is not None else None
        _cutp, cutv, _iv = Arch.getCutVolume(cutplane, shapes, clip, depth)

        cuts = []
        for sh in shapes:
            if cutv is not None and not cutv.isNull() and not sh.isNull():
                if sh.Volume < 0:
                    sh.reverse()
                try:
                    cut = sh.cut(cutv)
                except Exception:
                    cuts.extend(self._sub_shapes(sh, obj.OnlySolids))
                else:
                    cuts.extend(self._sub_shapes(cut, obj.OnlySolids))
            else:
                cuts.extend(self._sub_shapes(sh, obj.OnlySolids))
        compound = Part.makeCompound(cuts)

        # Draft's getProjected: the visible edge groups of the projection.
        groups = TechDraw.projectEx(compound, direction)
        edges = [e for g in groups[0:5] if not g.isNull() for e in g.Edges]
        return Part.makeCompound(edges)


def makeSectionView(doc=None, base=None, name="SectionView"):
    """Create an ArchPlus section view, optionally on a section plane."""
    import Part

    doc = doc or FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    _SectionView(obj)
    if base is not None:
        obj.Base = base
    obj.Shape = Part.makeCompound([])
    return obj
```

- [ ] **Step 4: Run the checks to verify they pass**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: `verify_sections` checks `PASS`, `0 check(s) failed`. If "draws
exactly what Draft draws" fails, compare the two edge sets and fix the
mirroring (the usual cause is the fuse order or the cut volume arguments) —
that check is the feature's correctness gate.

- [ ] **Step 5: Run the headless suite**

```
python3 -m pytest -q
```

Expected: `564 passed` (556 + the 8 rules tests Task 3 added).

- [ ] **Step 6: Commit**

```
git add archplus/tools/sections/object.py archplus/freecad_tests/verify_sections.py
git commit -m "Add a section view that draws exactly what Draft's draws"
```

---

### Task 5: Substituting the parts' outlines

**Files:**
- Modify: `archplus/tools/sections/object.py`
- Modify: `archplus/freecad_tests/verify_sections.py`

**Interfaces:**
- Consumes: `model.use_outline(...)` (Task 3), `part.Proxy.planOutline(part)`
  (Task 2).
- Produces: `_SectionView._outline_for(obj, part, plane, direction) ->
  Part.Shape | None` — the placed outline for a part, or `None` to draw its
  solid. Nothing later depends on it.

- [ ] **Step 1: Write the failing checks**

Append to `verify_sections.py`, and call it from `run()` after the last of the
wall view checks (the no-base one) — the `import ArchSectionPlane` above it is
then in scope for the part-only plane this block adds:

```python
def _part_view(doc, plane):
    """Add a placed library part to `plane`, and return it.

    The caller builds the views it compares; this only sets up the part the
    substitution is about."""
    from archplus.tools.partslib import object as pobj

    part = doc.addObject("Part::FeaturePython", "PlacedPart")
    pobj._LibraryPart(part)
    part.Shape = Part.makeBox(600, 400, 700)
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 0),
                                       FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [part]
    doc.recompute()
    return part
```

and in `run()`:

```python
    part = _part_view(doc, plane)
    view.PartOutlines = True
    doc.recompute()
    solid_view = sobj.makeSectionView(doc, base=plane)
    solid_view.PartOutlines = False
    # Same flags as `view` apart from the one under test, so the difference
    # between the two drawings is attributable to that one alone.
    solid_view.FuseArch = view.FuseArch
    doc.recompute()

    # With the part out of the plane, outlines on and off must draw the walls
    # identically: the substitution may only ever change the parts.
    with_part = list(plane.Objects or [])
    plane.Objects = [o for o in with_part if o is not part]
    doc.recompute()
    h.check("with the part out, outlines change nothing",
            _visible_edges(view.Shape) == _visible_edges(solid_view.Shape))
    plane.Objects = with_part
    doc.recompute()

    # Not "smaller": for a plain box the outline's silhouette is the same
    # rectangle the solid draws, so equal is the honest expectation here.
    # The real parts (many visible edges) are where the drawing shrinks, and
    # Task 7 measures that on the real document.
    h.check("outlines on: the drawing did not grow",
            len(view.Shape.Edges) <= len(solid_view.Shape.Edges))
    h.check("outlines on: the part's outline is what got drawn",
            _visible_edges(part.Proxy.planOutline(part))
            <= _visible_edges(view.Shape))

    # The outline is already in world coordinates, so the view must not place
    # it again: on a plane holding only this part, the drawing must sit
    # exactly on the part. Placing it twice would put it at (1000, 1000).
    alone = doc.addObject("App::FeaturePython", "PartOnlyPlane")
    ArchSectionPlane._SectionPlane(alone)
    alone.Objects = [part]
    alone.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    alone_view = sobj.makeSectionView(doc, base=alone)
    doc.recompute()
    box = alone_view.Shape.BoundBox
    h.check("the outline sits where the part is",
            abs(box.XMin - 500) < 1e-3 and abs(box.YMin - 500) < 1e-3
            and abs(box.XMax - 1100) < 1e-3 and abs(box.YMax - 900) < 1e-3)

    # A part with its base exactly on the plane is above the cut, so the cut
    # removes it from both drawings: this pins that no outline is added at the
    # boundary (a dropped tolerance would add the part's four edges).
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 1200),
                                       FreeCAD.Rotation())
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    doc.recompute()
    h.check("a part at the cut's own height adds no outline",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))

    # A part wholly above the cut: the cut removes its solid, so the drawing
    # has nothing of it. A footprint here would be a part the cut deleted -
    # this is the check that fails if only a *straddling* part is refused.
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 1500),
                                       FreeCAD.Rotation())
    doc.recompute()
    h.check("a part above the cut adds no footprint",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))

    # A part tilted about X keeps its solid too.
    plane.Placement.Base = FreeCAD.Vector(0, 0, 5000)
    part.Placement = FreeCAD.Placement(
        FreeCAD.Vector(500, 500, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 30))
    doc.recompute()
    h.check("a part rotated off plan keeps its solid",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))

    # A view that is not a plan (the plane tilted) keeps solids as well.
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 0),
                                       FreeCAD.Rotation())
    plane.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 30)
    doc.recompute()
    h.check("an elevation keeps the solid",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))
    plane.Placement.Rotation = FreeCAD.Rotation()
    doc.recompute()

    # A part whose own drawing has two separate outlines gets no outline (the
    # waste-bin case), so the view falls back to its solid.
    bin_part = doc.addObject("Part::FeaturePython", "TwoOutlinePart")
    pobj._LibraryPart(bin_part)
    bin_part.Shape = Part.makeCompound([Part.makeBox(400, 400, 300),
                                        Part.makeBox(400, 400, 300,
                                                     FreeCAD.Vector(2000, 0, 0))])
    # Clear of the wall band: the check is that the fallback draws this part's
    # solid, and a part buried in the wall has its edges hidden, so they would
    # not be in the drawing at all.
    bin_part.Placement = FreeCAD.Placement(FreeCAD.Vector(3000, 2000, 0),
                                           FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [bin_part]
    doc.recompute()
    h.check("a part with no trustworthy outline keeps its solid",
            bin_part.Proxy.planOutline(bin_part) is None
            and bin_part.Proxy._outline_key is not None  # the None is cached
            and _visible_edges(bin_part.Shape) <= _visible_edges(view.Shape))

    # The substitution is only visible on a part whose outline differs from its
    # own drawing: a block on a bigger block draws 8 edges as a solid and 4 as
    # an outline (its outer boundary). This is the check that fails when the
    # substitution does not happen at all - a plain box draws the same
    # rectangle either way.
    nested_part = doc.addObject("Part::FeaturePython", "NestedPart")
    pobj._LibraryPart(nested_part)
    nested_part.Shape = Part.makeCompound([Part.makeBox(600, 400, 300),
                                           Part.makeBox(300, 200, 300,
                                                        FreeCAD.Vector(150, 100, 300))])
    nested_part.Placement = FreeCAD.Placement(FreeCAD.Vector(6000, 2000, 0),
                                              FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [nested_part]
    doc.recompute()
    nested_solid_view = sobj.makeSectionView(doc, base=plane)
    nested_solid_view.PartOutlines = False
    nested_solid_view.FuseArch = view.FuseArch
    doc.recompute()
    h.check("the substituted drawing is the outline, not the solid",
            len(view.Shape.Edges) < len(nested_solid_view.Shape.Edges))
    h.check("and what it drops is the nested loop",
            len(_visible_edges(nested_part.Shape) - _visible_edges(view.Shape))
            == 4)

    # Turning the flag off draws the solid again.
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 0),
                                       FreeCAD.Rotation())
    view.PartOutlines = False
    doc.recompute()
    h.check("PartOutlines off draws the solid again",
            _visible_edges(view.Shape) == _visible_edges(solid_view.Shape))
```

- [ ] **Step 2: Run it to verify it fails**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: `FAIL` on "the substituted drawing is the outline, not the solid" —
`PartOutlines` is declared but ignored, so the view draws the nested part's
solid and the two drawings are the same size.

- [ ] **Step 3: Implement the substitution**

In `archplus/tools/sections/object.py`, replace `_build` and `_shapes` with
the split version — and while you are in `_shapes`, change its
`getattr(obj, "FuseArch", True)` fallback to `False`, which is what the
declared default now is and what Draft's own fallback is:

```python
    def _build(self, obj):
        import Part

        plane = obj.Base
        if plane is None:
            return Part.makeCompound([])
        direction = plane.Placement.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
        objs = self._objects(obj, plane)
        outlines = []
        solids = []
        for o in objs:
            outline = self._outline_for(obj, o, plane, direction)
            if outline is not None:
                outlines.append(outline)
            else:
                solids.append(o)
        shapes = self._shapes(obj, solids)
        return self._project(obj, shapes, outlines, plane, direction)

    def _outline_for(self, obj, candidate, plane, direction):
        """The placed outline for a library part, or None to draw its solid.

        Every condition here is one the design doc pins: the flag is on, the
        part has an outline, the view is a plan, the part is not rotated off
        plan, and the cut does not pass through it. Any of them failing means
        the solid is drawn - correct, just slower.
        """
        if not getattr(obj, "PartOutlines", True):
            return None
        from archplus.tools.partslib import object as pobj

        if not pobj.isLibraryPart(candidate):
            return None
        shape = getattr(candidate, "Shape", None)
        if shape is None or shape.isNull():
            return None
        from archplus.tools.sections import model

        placement = candidate.Placement
        box = shape.BoundBox
        if not model.use_outline(
                (box.ZMin, box.ZMax), plane.Placement.Base.z, direction,
                tuple(placement.Rotation.Axis), placement.Rotation.Angle):
            return None
        # A library part from an older add-on build has no planOutline: draw
        # its solid rather than raising into the recompute.
        plan_outline = getattr(getattr(candidate, "Proxy", None),
                               "planOutline", None)
        if plan_outline is None:
            return None
        # Already in world coordinates: a Part::Feature's Shape carries the
        # object's own placement, so plan_outline projected the *placed* part
        # and the result must not be placed a second time - that would draw
        # the part at twice its offset. It is also the cache's own object:
        # never mutate it, the next ask hands out the same shape.
        return plan_outline(candidate)
```

and in `_project`, draw the outlines' silhouettes without cutting or
projecting them:

```python
    def _project(self, obj, shapes, outlines, plane, direction):
        """Cut the solids against the section volume, project everything -
        Draft's own two steps, in Draft's own order. Each outline is drawn as
        its silhouette, which came out of the same projection, so it costs
        neither a boolean nor a hidden-line pass."""
        import Arch
        import Part
        import TechDraw

        cutplane = plane.Shape
        # Draft's resolution, read as its code actually behaves: it declares
        # Clip on the view itself (default False), so its `obj.Base.Clip`
        # branch is dead - Draft's own TODO says as much - and the view's
        # value always wins. This view declares no Clip, and the convert
        # command refuses a view that sets it, so this is False: a clipping
        # plane does not clip here either, exactly as in Draft. Depth *is* the
        # plane's - Draft's Shape2DView has no Depth of its own.
        clip = bool(getattr(obj, "Clip", False))
        depth = getattr(plane, "Depth", None)
        depth = depth.Value if depth is not None else None
        _cutp, cutv, _iv = Arch.getCutVolume(cutplane, shapes, clip, depth)

        cuts = []
        for sh in shapes:
            if cutv is not None and not cutv.isNull() and not sh.isNull():
                if sh.Volume < 0:
                    sh.reverse()
                try:
                    cut = sh.cut(cutv)
                except Exception:
                    cuts.extend(self._sub_shapes(sh, obj.OnlySolids))
                else:
                    cuts.extend(self._sub_shapes(cut, obj.OnlySolids))
            else:
                cuts.extend(self._sub_shapes(sh, obj.OnlySolids))
        compound = Part.makeCompound(cuts)

        groups = TechDraw.projectEx(compound, direction)
        edges = [e for g in groups[0:5] if not g.isNull() for e in g.Edges]
        for outline in outlines:
            # The silhouette: the face the slab was extruded from, which
            # sits in the projection plane (z = 0) exactly where Draft's own
            # projected edges sit. The slab's raw edges would draw the same
            # picture three times over - top loop, bottom loop, and the 1mm
            # verticals - and every one of them is an edge the redraw pays
            # for. Read-only: `outline` is the part's cached shape, shared
            # with every later recompute.
            flat = [f for f in outline.Faces
                    if abs(f.BoundBox.ZLength) < 1e-9]
            if flat:
                edges.extend(min(flat, key=lambda f: f.BoundBox.ZMin)
                             .OuterWire.Edges)
            else:
                edges.extend(outline.Edges)
        return Part.makeCompound(edges)
```

- [ ] **Step 4: Run the checks to verify they pass**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: all `verify_sections` checks `PASS`, `0 check(s) failed`.

- [ ] **Step 5: Run the headless suite**

```
python3 -m pytest -q
```

Expected: `564 passed`.

- [ ] **Step 6: Commit**

```
git add archplus/tools/sections/object.py archplus/freecad_tests/verify_sections.py
git commit -m "Draw library parts as their cached plan outline in a section view"
```

---

### Task 6: Converting an existing view

**Files:**
- Create: `archplus/tools/sections/gui.py`
- Create: `archplus/tools/sections/resources/icons/SectionView.svg`
- Modify: `archplus/freecad_tests/verify_sections.py`
- Modify: `archplus/common/tests/test_lazy_imports.py`
- Modify: `InitGui.py`

**Interfaces:**
- Consumes: `makeSectionView(doc, base, name)` (Task 4).
- Produces: `convertSectionView(view) -> bool` and the command
  `ArchPlus_SectionView` in `archplus.tools.sections.gui`.

- [ ] **Step 1: Write the failing checks**

Append to `verify_sections.py`, and call from `run()`:

```python
def _convert(doc, plane):
    """A Draft view to convert, plus a TechDraw view reading it."""
    import TechDraw

    draft = doc.addObject("Part::Part2DObjectPython", "ToConvert")
    import draftobjects.shape2dview as s2v

    s2v.Shape2DView(draft)
    draft.Base = plane
    draft.FuseArch = True
    draft.ProjectionMode = "Solid"
    draft.Placement = FreeCAD.Placement(FreeCAD.Vector(9000, 0, 0),
                                        FreeCAD.Rotation())
    doc.recompute()

    reader = doc.addObject("TechDraw::DrawProjGroupItem", "Reader")
    reader.Source = [draft]
    doc.recompute()
    return draft, reader
```

and in `run()`:

```python
    draft, reader = _convert(doc, plane)
    old_bbox = draft.Shape.BoundBox

    from archplus.tools.sections import gui as sgu

    h.check("the conversion reports success", sgu.convertSectionView(draft))
    h.check("the old view is gone", doc.getObject("ToConvert") is None)
    converted = next((o for o in doc.Objects if o.Label == "ToConvert"), None)
    h.check("the new view exists", converted is not None)
    h.check("the reader points at the new view",
            converted is not None and converted in list(reader.Source or []))
    h.check("the placement came across",
            converted is not None
            and abs(converted.Placement.Base.x - 9000) < 1e-6)
    h.check("the drawing did not jump",
            converted is not None
            and abs(converted.Shape.BoundBox.XMin - old_bbox.XMin) < 1e-3)

    # A view using a setting the new object does not reproduce is refused.
    other = doc.addObject("Part::Part2DObjectPython", "HiddenLines")
    s2v.Shape2DView(other)
    other.Base = plane
    other.HiddenLines = True
    doc.recompute()
    h.check("an unsupported setting is refused",
            sgu.convertSectionView(other) is False)
    h.check("the refused view is still there", doc.getObject("HiddenLines") is not None)

    # A view that is not on a section plane is refused too: this view only
    # gathers a section plane's objects, so converting one would draw blank.
    base_less = doc.addObject("Part::Part2DObjectPython", "NoBase")
    s2v.Shape2DView(base_less)
    doc.recompute()
    h.check("a view with no section plane is refused",
            sgu.convertSectionView(base_less) is False)
    h.check("the base-less view is still there",
            doc.getObject("NoBase") is not None)
```

- [ ] **Step 2: Run it to verify it fails**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: `CRASH in verify_sections` — `archplus.tools.sections.gui` does not
exist.

- [ ] **Step 3: Implement the command**

First the icon (`archplus/tools/sections/resources/icons/SectionView.svg` — a
plan cut with an outline inside it):

```svg
<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16">
  <rect x="1.5" y="1.5" width="13" height="13" fill="none" stroke="#000000" stroke-width="1.2"/>
  <rect x="4.5" y="4.5" width="7" height="7" fill="none" stroke="#000000" stroke-width="0.8" stroke-dasharray="1.5 1"/>
</svg>
```

Then create `archplus/tools/sections/gui.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The section view command: convert a Draft Shape2DView into an ArchPlus one.
#
# One view at a time, on purpose - a converted view renumbers its drawing, so
# the dimensions measuring it need re-picking once. Converting one, comparing
# it against an unconverted one, and only then converting the rest is the
# migration the design doc describes.
#
# A view whose settings the ArchPlus view does not reproduce is refused, by
# name, rather than converted: silently dropping HiddenLines or a non-Solid
# projection mode would draw something the user did not ask for.

import FreeCAD

# Draft's Shape2DView settings this view does not reproduce, with the value
# that means "not used" (None = the property is absent on that object).
UNSUPPORTED = (
    ("ProjectionMode", "Solid"),
    ("HiddenLines", False),
    ("Tessellation", False),
    ("InPlace", False),
    ("Clip", False),
    ("Depth", 0.0),
)


def unsupported_settings(view):
    """The settings that stop this view being converted, as readable names."""
    found = []
    for name, neutral in UNSUPPORTED:
        if not hasattr(view, name):
            continue
        value = getattr(view, name)
        if name == "Depth":
            value = value.Value
        if value != neutral:
            found.append("%s = %s" % (name, value))
    points = list(getattr(view, "ExclusionPoints", None) or [])
    if points:
        found.append("ExclusionPoints")
    return found


def convertSectionView(view):
    """Replace a Draft Shape2DView with an ArchPlus section view.

    Copies the base, the placement and the settings the new view reproduces,
    re-points every TechDraw view reading the old one, and only then removes
    it - so a failure part-way leaves the document usable.
    """
    from archplus.tools.sections import object as sections_object

    if not _is_draft_view(view):
        FreeCAD.Console.PrintWarning(
            "ArchPlus: '%s' is not a Draft section view\n" % view.Label)
        return False
    if not _is_section_plane(view.Base):
        FreeCAD.Console.PrintWarning(
            "ArchPlus: '%s' is not on a section plane; not converted\n"
            % view.Label)
        return False
    found = unsupported_settings(view)
    if found:
        FreeCAD.Console.PrintWarning(
            "ArchPlus: '%s' uses %s, which an ArchPlus section view does not "
            "reproduce; not converted\n" % (view.Label, ", ".join(found)))
        return False

    doc = view.Document
    doc.openTransaction("Convert to ArchPlus section view")
    try:
        new = sections_object.makeSectionView(doc, base=view.Base)
        new.Label = view.Label
        new.Placement = view.Placement
        _copy_settings(view, new)
        if not _repoint_sources(doc, view, new):
            raise RuntimeError("a TechDraw view could not be re-pointed")
        doc.removeObject(view.Name)
    except Exception as exc:
        doc.abortTransaction()
        FreeCAD.Console.PrintError(
            "ArchPlus: could not convert '%s': %s\n" % (view.Label, exc))
        return False
    doc.commitTransaction()
    doc.recompute()
    return True


def _is_draft_view(view):
    proxy = getattr(view, "Proxy", None)
    return type(proxy).__name__ == "Shape2DView"


def _is_section_plane(base):
    """True when `base` is the kind of plane this view knows how to gather.

    Draft's Shape2DView also accepts a building part or an IFC annotation as
    its base, and gathers those differently (the level's Group, a synthetic
    cut plane). This view reproduces the section plane case only, so any
    other base is refused rather than converted into a blank drawing.
    """
    import Draft

    return base is not None and Draft.getType(base) == "SectionPlane"


def _copy_settings(view, new):
    for name in ("FuseArch", "OnlySolids", "VisibleOnly"):
        if hasattr(view, name):
            setattr(new, name, getattr(view, name))
    if hasattr(view, "ExclusionNames"):
        new.ExclusionNames = list(view.ExclusionNames or [])


def _repoint_sources(doc, old, new):
    """Point every TechDraw view that read `old` at `new` instead."""
    for obj in doc.Objects:
        source = getattr(obj, "Source", None)
        if not source:
            continue
        if not any(item is old for item in source):
            continue
        try:
            obj.Source = [new if item is old else item for item in source]
        except Exception:
            return False
    return True


class ConvertSectionViewCommand:
    def GetResources(self):
        import os

        return {"Pixmap": os.path.join(os.path.dirname(__file__),
                                       "resources", "icons", "SectionView.svg"),
                "MenuText": "Convert section view",
                "ToolTip": "Draw library parts as their plan outline in the "
                           "selected Draft section view"}

    def IsActive(self):
        return bool(_selected_views())

    def Activated(self):
        for view in _selected_views():
            convertSectionView(view)


def _selected_views():
    import FreeCADGui

    return [sel.Object for sel in FreeCADGui.Selection.getSelectionEx()
            if _is_draft_view(sel.Object)]


if FreeCAD.GuiUp:
    import FreeCADGui

    FreeCADGui.addCommand("ArchPlus_SectionView", ConvertSectionViewCommand())
```

- [ ] **Step 4: Add the menu entry, and put the new gui module under the import guard**

The lazy-import guard exists for exactly the failure mode this file risks - a
module-scope `Part`/`Draft` import in a gui.py that BIM's startup imports
before those modules are safe to touch. Add it to the guard's list in
`archplus/common/tests/test_lazy_imports.py`:

```python
MODULES = (
    "archplus.tools.doors.gui",
    "archplus.tools.windows.gui",
    "archplus.tools.stairs.gui",
    "archplus.tools.partslib.gui",
    "archplus.tools.walk.gui",
    "archplus.tools.sections.gui",
    "archplus.common.widgets",
)
```

In `InitGui.py`, add the command to the list and register it in the menu only
(a one-shot migration command does not belong on the modelling toolbar, and
keeping it off the toolbar leaves the README toolbar image alone):

```python
    commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows",
                "ArchPlus_PartsLibrary", "ArchPlus_WalkThrough", "ArchPlus_WallTools"]
    menu_only = ["ArchPlus_SectionView"]
```

and inside `add_ui`:

```python
        import archplus.tools.sections.gui  # noqa: F401
        workbench.appendToolbar(toolbar, commands)
        workbench.appendMenu(toolbar, commands + menu_only)
```

- [ ] **Step 5: Run the checks to verify they pass**

```
del %TEMP%\archplus_verify.marker
"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
```

Expected: all `verify_sections` checks `PASS`, `0 check(s) failed`.

- [ ] **Step 6: Run the headless suite**

```
python3 -m pytest -q
```

Expected: `564 passed` (the lazy-import guard must stay green — `gui.py`
imports `FreeCAD` only at module scope, everything else inside functions).

- [ ] **Step 7: Commit**

```
git add archplus/tools/sections/gui.py archplus/tools/sections/resources/icons/SectionView.svg archplus/freecad_tests/verify_sections.py archplus/common/tests/test_lazy_imports.py InitGui.py
git commit -m "Convert a Draft section view to an ArchPlus one, one view at a time"
```

---

### Task 7: Document it, and measure the real thing

**Files:**
- Modify: `docs/TOOLS.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code-facing.

- [ ] **Step 1: Write the tool's docs section**

Add to `docs/TOOLS.md`, beside the other tools' sections, in their voice:

```markdown
## Section views

**Convert section view** (BIM workbench, ArchPlus menu) replaces a Draft
`Shape2DView` with an ArchPlus one. The difference is what it draws for
placed library parts: instead of projecting their solids, it draws each
part's cached plan outline - the outer boundary of the part's own plan
projection, computed once and reused until the part rebuilds. A furnished
plan's drawings shrink by about a third and the section views rebuild in a
fraction of the time, because the parts are most of what they project.

The outline is the part's **filled footprint**: a boundary nested inside it
(a smaller block on top of a bigger one, a hole through a part) is not drawn.
Reproducing every loop was measured to make the drawings *bigger* than
drawing the solids, which is the opposite of the point.

The outline is used only where the drawing cannot mean something else: the
view must be a plan cut, the part must not be rotated off plan, and the
section plane must not cut through the part. Otherwise that part is drawn as
its solid, exactly as before. Turning **PartOutlines** off on the view draws
every part as its solid.

Converting a view **renumbers it**, so the TechDraw dimensions measuring that
view need re-picking once - convert one view, compare it, then convert the
rest. A view using `HiddenLines`, `Tessellation`, `Clip`, `Depth`,
`InPlace`, `ExclusionPoints` or a projection mode other than `Solid` is
refused rather than converted, because this view does not reproduce those.

While modelling, two switches keep the drawings from chasing every change:
set **KeepUpdated** to false on the TechDraw page, and hide the section
views in the 3D view. Both are reversible, and the drawings catch up when
you turn them back on.
```

- [ ] **Step 2: Measure the payoff on the real document (opt-in, manual)**

This is the only step that touches the user's own file. Ask before running it,
and do it on a copy:

1. Open a copy of the furnished document.
2. In the Python console, time the four section views before conversion:
   `import time; t=time.time(); [o.Proxy.execute(o) for o in FreeCAD.ActiveDocument.Objects if type(getattr(o,'Proxy',None)).__name__=='Shape2DView']; print(time.time()-t)`
   and record the total and each view's edge count.
3. Convert one view with the menu command, then re-time and re-count.
4. Move one library part, then time `doc.recompute()` and `FreeCADGui.updateGui()`.
5. Record the numbers in the branch's PR description: the views' execute
   time, the drawings' edge counts, and the recompute/redraw after a part
   move — the honest payoff, since the plan's ~4–5 s estimate is assembled
   from measured pieces rather than measured end to end.

- [ ] **Step 3: Commit**

```
git add docs/TOOLS.md
git commit -m "Document the section view and what its outlines do"
```

---

## Self-Review

**Spec coverage:** every spec section maps to a task — the outline algorithm and
its self-check (Task 1), the cache on the proxy (Task 2), the substitution
conditions (Tasks 3 and 5), the view object and its flags (Task 4), the
outline path and its fallbacks (Task 5), the convert command and its refusals
(Task 6), the docs and the real-document measurement (Task 7). The spec's
"Verification" list is Tasks 1, 2, 4, 5 and 6; "Out of scope" items (the
freeze toggle, non-plan views, per-part switches, other projection modes, the
level compounds, the lowercase claims) appear in no task, deliberately.

**Placeholder scan:** no `TBD`/`TODO`/"handle edge cases" — every step carries
its code, its command and its expected output.

**Type consistency:** `plan_outline(shape, thickness=1.0)` is defined in Task 1
and called only by `_LibraryPart.planOutline` in Task 2;
`use_outline(z_range, plane_z, direction, axis, angle)` is defined and tested
in Task 3 and called in Task 5 with exactly those arguments;
`makeSectionView(doc, base, name)` is defined in Task 4 and used in Tasks 5
and 6; `convertSectionView(view)` is defined and used in Task 6.

**Review Focus:** the five inputs named at the top are each pinned — the
two-outline part (Task 1's compound check, Task 5's fallback), the
cut-straddling part and the off-plan part (Task 3's tests, Task 5's checks),
the lost Placement (Task 6's "drawing did not jump"), the unsupported settings
(Task 6's refusal check). Empty `Base`, empty `Objects` and a missing outline
are pinned in Tasks 4 and 5.
