# Wall Length Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Selecting a wall segment in FreeCAD draws a CAD-style length dimension (line, oblique end ticks, screen-facing label) above the wall's top edge, as a Coin overlay with no document objects, tracking reflows.

**Architecture:** A new `dims.py` owns three layers: a FreeCAD-free geometry core (dimension-plane lifting, ticks, arc-length label anchor), a selection mapper that turns `getSelectionEx()` members into dimmed segments (root face picks resolved through the existing `resolveRootFace` + pick recorder), and a thin Coin/pivy builder that writes one named `SoSeparator` into each dimmed segment's `RootNode` — the exact mechanism of the existing face highlight. One global selection observer, registered at `gui.py` import time like `_PickPointRecorder`, diffs the desired dimmed set against the drawn overlays on every selection event; `_ViewProviderWall.updateData` rebuilds the node when the shape changes.

**Tech Stack:** FreeCAD 1.1 (Part::FeaturePython walls), pivy/Coin 3D nodes, PySide-free overlay logic, headless pytest via the repo-root `conftest.py` fakes.

**Spec:** `docs/superpowers/specs/2026-08-30-wall-length-overlay-design.md`

## Global Constraints

- **Run headless tests with:** `uv run --no-project --with pytest python -m pytest -q` from the repo root (system Python has no pytest; see TESTING.md). Baseline before Task 1: **429 passed** (425 original + 4 from the selection-mapping tests that landed on the base branch); after Task 1: **436 passed** (current HEAD, 99c8b6b). Task 2 → 440, Tasks 3–4 → 449. Any other count is a regression.
- **Base-branch adaptation (2026-08-30 rebase):** the base branch gained native selection mapping — `_WallSelectionObserver` (`_ArchPlusWallSelObs`, `gui.py`) redirects 3D picks to the owning segment and draws per-face highlight overlays; `_ViewProviderWall.updateData` was rewritten to call `observer.refresh(obj)`; `verify_walls.py` numbers its checks through W24 and provides a `_pump()` helper that flushes the observer's deferred QTimer events. Task 4 keeps the observer refresh; Task 5 numbers its check W25 and pumps after every selection change. The dim overlay's node (`ArchPlusSegmentDim`) is distinct from `ArchPlusSegmentHighlight`, so the overlays coexist.
- **FreeCAD-session suite:** `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py` (Windows host; the workstation is WSL). Must report 0 failed checks after Task 5.
- All lengths internally in **mm** (FreeCAD base unit).
- **Python style:** match the surrounding code exactly — `%`-style formatting, no f-strings, no type hints. LGPL header on every new `.py` file: `# SPDX-License-Identifier: LGPL-2.1-or-later` + a `#`-comment block explaining the module's purpose, with `Copyright (c) 2026 Andres <andres@neltu.me>` where other files carry a copyright line (`model.py`-style headers without copyright are also fine — copy the neighbour file's shape).
- `dims.py` imports `FreeCAD`, `FreeCADGui` and `pivy` **only inside functions** (the headless suite runs under conftest fakes; `object.py` already imports `FreeCAD` at module level, which the fakes cover). The `walls_object` import is module-level — there is no import cycle (`object.py` must NOT import `dims` at module level; see Task 4).
- The overlay never creates document objects, never touches selection itself (the observer only reads), and every observer callback / Coin call is wrapped so selection never breaks.
- Line numbers below are indicative — the user commits to this branch concurrently. **Re-read each file region before editing**; anchor edits on symbol names, not stale line numbers.
- All work on branch `feat/wall-length-overlay` (already created, checked out). Commit style: plain imperative summary, no conventional-commit prefixes.

## File Structure

```
archplus/tools/walls/
    dims.py                 NEW  geometry core, selection mapping, Coin overlay,
                            observer install — the whole overlay feature
    object.py               MODIFIED  claimedEdges + segmentAxisPolylines (read-only
                            chain extraction), updateData reflow hook
    gui.py                  MODIFIED  import dims, dims.install() after the pick
                            recorder registration
    tests/test_dims.py      NEW  headless tests (geometry, axis summaries,
                            selection mapping, overlay bookkeeping)
archplus/freecad_tests/verify_walls.py    MODIFIED  _w25_selection_dims GUI check
docs/ROADMAP.md, docs/TOOLS.md            MODIFIED  docs
```

Responsibility split: `object.py` keeps owning everything that reads sketch/edge geometry (`_chainPolyline`, clustering, effective config) and exposes it as plain data; `dims.py` consumes plain data only, so its geometry and bookkeeping stay headless-testable; Coin and FreeCADGui appear only inside `dims.py` function bodies.

---

### Task 1: Geometry core in `dims.py`

**Files:**
- Create: `archplus/tools/walls/dims.py` (geometry core only)
- Test: `archplus/tools/walls/tests/test_dims.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces (later tasks rely on these exact signatures):
  - `DIM_NODE = "ArchPlusSegmentDim"` (module constant)
  - `dim_lift(height) -> float` — dimension-plane height above the segment's base
  - `polyline_length(pts) -> float` — pts: sequence of `(x, y, z)` tuples
  - `format_length(mm) -> str` — user-unit text, `"%.0f mm"` fallback
  - `_dimGeometry(pts, normal, height) -> (line, ticks, label_pt)` — raises `ValueError` on chains with no direction; all coordinates plain tuples; `_dist(a, b) -> float` helper (used by tests)

- [ ] **Step 1: Write the failing tests**

```python
# archplus/tools/walls/tests/test_dims.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall length overlay: dimension geometry, chain
# summaries, selection mapping and overlay bookkeeping. dims.py imports
# FreeCAD/FreeCADGui only inside functions, so the conftest fakes carry the
# whole suite.

import types

import FreeCAD
import FreeCADGui
import pytest

from archplus.tools.walls import dims
from archplus.tools.walls import gui as walls_gui
from archplus.tools.walls import object as walls_object

UP = (0.0, 0.0, 1.0)


# --- dim geometry (Task 1) --------------------------------------------------

def test_polyline_length_sums_segments():
    pts = [(0, 0, 0), (1000, 0, 0), (1000, 500, 0)]
    assert dims.polyline_length(pts) == pytest.approx(1500.0)


def test_dim_lift_clears_the_top_edge():
    # 5 % of the height once that beats the 100 mm floor.
    assert dims.dim_lift(2800.0) == pytest.approx(2940.0)
    # the 100 mm floor for low walls.
    assert dims.dim_lift(1000.0) == pytest.approx(1100.0)


def test_dim_geometry_raises_a_straight_chain():
    line, ticks, label = dims._dimGeometry([(0, 0, 0), (4000, 0, 0)], UP,
                                           2800.0)
    assert line == [(0.0, 0.0, 2940.0), (4000.0, 0.0, 2940.0)]
    assert label == (2000.0, 0.0, 2940.0)
    assert len(ticks) == 2


def test_dim_geometry_ticks_cross_the_ends_at_45_degrees():
    line, ticks, _label = dims._dimGeometry([(0, 0, 0), (4000, 0, 0)], UP,
                                            2800.0)
    for (a, b), end in zip(ticks, line):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
        assert mid == pytest.approx(end)
        assert dims._dist(a, b) == pytest.approx(60.0)
        assert a[2] == b[2] == end[2]


def test_dim_geometry_follows_an_l_chain():
    line, ticks, label = dims._dimGeometry(
        [(0, 0, 0), (4000, 0, 0), (4000, 3000, 0)], UP, 2800.0)
    assert len(line) == 3
    assert line[2] == (4000.0, 3000.0, 2940.0)
    # total 7000, so the arc-length midpoint sits at 3500 on the first leg.
    assert label == (3500.0, 0.0, 2940.0)
    assert len(ticks) == 2


def test_dim_geometry_rejects_degenerate_chains():
    with pytest.raises(ValueError):
        dims._dimGeometry([(0, 0, 0)], UP, 2800.0)


def test_format_length_falls_back_to_millimetres():
    # The conftest fake Units make Quantity() return None, which forces the
    # plain millimetre fallback — exactly the path this test pins.
    assert dims.format_length(2450.0) == "2450 mm"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walls/tests/test_dims.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'archplus.tools.walls.dims'`

- [ ] **Step 3: Write the geometry core**

```python
# archplus/tools/walls/dims.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# On-select length dimensions for wall segments
# (docs/superpowers/specs/2026-08-30-wall-length-overlay-design.md):
# selecting a segment draws a Coin overlay above its top edge — a dimension
# line along the segment's axis, oblique end ticks and a screen-facing
# length label. No document objects are created; the overlay lives in the
# segment's view provider under a tracked node name, like the edit
# highlight. The geometry and selection mapping here work on plain tuples
# so pytest drives them headlessly; FreeCAD and pivy are imported lazily
# inside functions.

# Node name convention: ArchPlusSegmentHighlight, ArchPlusTargetPreview.
DIM_NODE = "ArchPlusSegmentDim"

_DIM_COLOR = (1.0, 0.85, 0.2)   # warm yellow, distinct from the green highlight
_FONT_SIZE = 18                 # SoText2 renders at a constant on-screen size
_LINE_WIDTH = 2.0
_TICK = 60.0                    # mm, oblique end tick
_MARGIN = 100.0                 # mm above the top edge, minimum
_MARGIN_RATIO = 0.05


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def _dist(a, b):
    d = _sub(a, b)
    return (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) ** 0.5


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def _norm(a):
    """The unit vector, or None when a is (near) zero."""
    length = (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5
    if length < 1e-12:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)


def _raise(p, normal, lift):
    return _add(p, _mul(normal, lift))


def dim_lift(height):
    """Height of the dimension plane above the segment's base: the wall's
    top edge plus a margin (at least 100 mm, otherwise 5 % of the height)."""
    return height + max(_MARGIN, height * _MARGIN_RATIO)


def polyline_length(pts):
    """Total length of a polyline of (x, y, z) tuples."""
    total = 0.0
    for a, b in zip(pts, pts[1:]):
        total += _dist(a, b)
    return total


def _midpoint(pts):
    """The arc-length midpoint of the polyline."""
    if len(pts) == 2:
        return _mul(_add(pts[0], pts[1]), 0.5)
    half = polyline_length(pts) / 2.0
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = _dist(a, b)
        if d > 1e-12 and acc + d >= half:
            return _add(a, _mul(_sub(b, a), (half - acc) / d))
        acc += d
    return pts[-1]


def _dimGeometry(pts, normal, height, tick=_TICK):
    """Dimension geometry for one chain: the axis polyline raised to the
    dimension plane, an oblique tick crossing each end (45 degrees to the
    line, centred on the end) and the label anchor at the arc-length
    midpoint. pts and normal are plain (x, y, z) tuples; raises ValueError
    when the chain has no direction."""
    if len(pts) < 2:
        raise ValueError("chain has no direction")
    lift = dim_lift(height)
    line = [_raise(p, normal, lift) for p in pts]
    ticks = []
    for i, step in ((0, 1), (len(line) - 1, -1)):
        d = _norm(_sub(line[i + step], line[i]))
        if d is None:
            continue
        side = _norm(_cross(normal, d))
        u = _norm(_add(d, side)) if side else d
        if u is None:
            continue
        end = line[i]
        ticks.append([_sub(end, _mul(u, tick / 2.0)),
                      _add(end, _mul(u, tick / 2.0))])
    return line, ticks, _midpoint(line)


def format_length(mm):
    """The length in the user's unit scheme (stairs/doors precedent), with
    a plain millimetre fallback for headless runs."""
    try:
        import FreeCAD
        return FreeCAD.Units.Quantity(float(mm),
                                      FreeCAD.Units.Length).UserString
    except Exception:
        return "%.0f mm" % mm
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walls/tests/test_dims.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: **432 passed**

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/walls/dims.py archplus/tools/walls/tests/test_dims.py
git commit -m "Add the dim geometry core for wall length overlays"
```

---

### Task 2: Chain extraction (`object.py`) + plain-data summaries (`dims.py`)

**Files:**
- Modify: `archplus/tools/walls/object.py` (add `claimedEdges` + `segmentAxisPolylines` after `resolveRootFace`)
- Modify: `archplus/tools/walls/dims.py` (add `axis_dims`, `_dimChains`, module-level `walls_object` import)
- Test: `archplus/tools/walls/tests/test_dims.py`

**Interfaces:**
- Consumes: `object.py` internals `_claimedEdges` (via the new public wrapper), `_chainPolyline`, `effectiveValues`, `Vector`; Task 1's `polyline_length`, `_dimGeometry`, `format_length`.
- Produces:
  - `walls_object.claimedEdges(obj) -> [subname]` — the segment's effective claims (public wrapper over the proxy's `_claimedEdges`)
  - `walls_object.segmentAxisPolylines(obj) -> [(points, normal, height)]` — points are FreeCAD Vectors along each claimed chain (world coordinates, as `_buildSegment` consumes them), normal the sketch's global normal Vector, height the effective height in mm; undrawable chains skipped, empty list when nothing builds
  - `dims.axis_dims(segment) -> [(plain_pts, length_mm)]` — per-chain summary, degenerate chains dropped
  - `dims._dimChains(segment) -> [(line, ticks, label_pt, text)]` — per-chain overlay geometry ready for the Coin builder

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/walls/tests/test_dims.py`:

```python
# --- chain summaries (Task 2) -----------------------------------------------

def _segment(name="Segments"):
    return types.SimpleNamespace(
        Name=name, Label=name, Group=[], InList=[], Wall=None,
        Proxy=types.SimpleNamespace(Type="WallSegment"))


_STRAIGHT = [FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(4000, 0, 0)]


def test_axis_dims_sums_chain_lengths(monkeypatch):
    chains = [(_STRAIGHT, FreeCAD.Vector(0, 0, 1), 2800.0)]
    monkeypatch.setattr(walls_object, "segmentAxisPolylines",
                        lambda seg: chains)
    assert dims.axis_dims(_segment()) == [
        ([(0.0, 0.0, 0.0), (4000.0, 0.0, 0.0)], 4000.0)]


def test_axis_dims_skips_degenerate_chains(monkeypatch):
    chains = [([FreeCAD.Vector(0, 0, 0)], FreeCAD.Vector(0, 0, 1), 2800.0)]
    monkeypatch.setattr(walls_object, "segmentAxisPolylines",
                        lambda seg: chains)
    assert dims.axis_dims(_segment()) == []


def test_dim_chains_build_label_and_geometry(monkeypatch):
    chains = [(_STRAIGHT, FreeCAD.Vector(0, 0, 1), 2800.0)]
    monkeypatch.setattr(walls_object, "segmentAxisPolylines",
                        lambda seg: chains)
    line, ticks, label_pt, text = dims._dimChains(_segment())[0]
    assert line == [(0.0, 0.0, 2940.0), (4000.0, 0.0, 2940.0)]
    assert label_pt == (2000.0, 0.0, 2940.0)
    assert text == "4000 mm"  # the fake Units force the fallback format
    assert len(ticks) == 2


def test_dim_chains_skip_undrawable_chains(monkeypatch):
    chains = [(_STRAIGHT, FreeCAD.Vector(0, 0, 1), 2800.0)]
    monkeypatch.setattr(walls_object, "segmentAxisPolylines",
                        lambda seg: chains)

    def boom(*_args):
        raise ValueError("doubled back")

    monkeypatch.setattr(dims, "_dimGeometry", boom)
    assert dims._dimChains(_segment()) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walls/tests/test_dims.py -q`
Expected: FAIL — `AttributeError: module 'archplus.tools.walls.object' has no attribute 'segmentAxisPolylines'`

- [ ] **Step 3: Write the chain extraction in `object.py`**

Re-read `archplus/tools/walls/object.py` and locate the end of `resolveRootFace` (starts near the top of the helpers block, after `all_segments`). Insert immediately after that function, before the next `def`:

```python
def claimedEdges(obj):
    """The sketch subnames the segment effectively builds: its claims minus
    its descendants'. Public wrapper over the proxy's claim resolution so
    sibling modules (the dim overlay) need no proxy internals."""
    proxy = getattr(obj, "Proxy", None)
    if not hasattr(proxy, "_claimedEdges"):
        return []
    return proxy._claimedEdges(obj)


def segmentAxisPolylines(obj):
    """The segment's axis polylines in world coordinates, one per claimed
    chain — the read-only twin of _buildSegment's chain phase. Returns
    [(points, normal, height)]: points are FreeCAD Vectors along the chain,
    normal the sketch's global normal, height the effective wall height in
    mm. Chains that cannot be traversed (doubled back) are skipped."""
    import Part
    sketch = obj.Base
    if sketch is None or not hasattr(sketch, "Shape"):
        return []
    subnames = claimedEdges(obj)
    if not subnames:
        return []
    cfg = effectiveValues(obj)
    if cfg["Height"] <= 0:
        return []
    normal = sketch.getGlobalPlacement().Rotation.multVec(Vector(0, 0, 1))
    edges = []
    for sub in subnames:
        try:
            edges.append(sketch.Shape.getElement(sub))
        except Exception:
            continue
    if not edges:
        return []
    try:
        chains = Part.getSortedClusters(edges)
    except Exception:
        chains = [[edge] for edge in edges]
    out = []
    for chain in chains:
        try:
            out.append((_chainPolyline(chain), normal, cfg["Height"]))
        except Exception:
            continue
    return out
```

- [ ] **Step 4: Write the summaries in `dims.py`**

Add to the import block of `archplus/tools/walls/dims.py` (module level — no cycle: `object.py` does not import `dims`):

```python
from archplus.tools.walls import object as walls_object
```

Append at the end of `archplus/tools/walls/dims.py`:

```python
def axis_dims(segment):
    """Per-chain (points, length_mm) summaries for a segment, plain data.
    Degenerate chains (fewer than two points, zero length) are skipped."""
    out = []
    for pts, _normal, _height in walls_object.segmentAxisPolylines(segment):
        plain = [(p.x, p.y, p.z) for p in pts]
        length = polyline_length(plain)
        if len(plain) >= 2 and length > 1e-9:
            out.append((plain, length))
    return out


def _dimChains(segment):
    """Per-chain overlay geometry for a segment: (line, ticks, label_pt,
    text) with plain tuples, ready for the Coin builder. Chains with no
    direction (doubled back) are skipped."""
    out = []
    for pts, normal, height in walls_object.segmentAxisPolylines(segment):
        plain = [(p.x, p.y, p.z) for p in pts]
        length = polyline_length(plain)
        if len(plain) < 2 or length <= 1e-9:
            continue
        try:
            line, ticks, label_pt = _dimGeometry(
                plain, (normal.x, normal.y, normal.z), height)
        except Exception:
            continue
        out.append((line, ticks, label_pt, format_length(length)))
    return out
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walls/tests/test_dims.py -q`
Expected: PASS (11 tests)

- [ ] **Step 6: Run the full suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: **436 passed**

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/walls/object.py archplus/tools/walls/dims.py archplus/tools/walls/tests/test_dims.py
git commit -m "Read wall segment axis polylines for the length overlay"
```

---

### Task 3: Selection mapping, Coin builder, overlay bookkeeping (`dims.py`)

**Files:**
- Modify: `archplus/tools/walls/dims.py`
- Test: `archplus/tools/walls/tests/test_dims.py`

**Interfaces:**
- Consumes: `walls_object.is_segment`/`is_root`/`resolveRootFace`/`removeFaceHighlight`; `walls_gui._lastPick` (lazy import — `gui.py` will import `dims` in Task 4, so `dims` must import `gui` only inside functions); Task 1–2 functions.
- Produces (Task 4 and 5 rely on these):
  - `dims.addDim(segment) -> bool`, `dims.removeDim(segment) -> None`
  - `dims.sync() -> None` (observer-facing; never raises), `dims.refresh(segment) -> None` (updateData-facing), `dims.install() -> None`
  - `dims._dimTargets() -> [segment]` (test surface), `dims._key(obj) -> (doc_name, obj_name)`

- [ ] **Step 1: Write the failing tests**

Append to `archplus/tools/walls/tests/test_dims.py`:

```python
# --- selection mapping and bookkeeping (Task 3) ------------------------------


@pytest.fixture(autouse=True)
def _reset_overlay_state():
    dims._nodes.clear()
    yield
    dims._nodes.clear()


def _root(*segments):
    root = types.SimpleNamespace(
        Name="Wall", Label="Wall",
        Proxy=types.SimpleNamespace(Type="Wall"),
        Group=list(segments), InList=[])
    for seg in segments:
        seg.Wall = root
        seg.InList = [root]
    return root


def _sel(obj, subs=()):
    return types.SimpleNamespace(Object=obj, SubElementNames=tuple(subs))


def test_dim_targets_direct_segments(monkeypatch):
    a = _segment("a")
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(a)]))
    assert dims._dimTargets() == [a]


def test_dim_targets_resolves_root_face_picks(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    root = _root(a, b)
    seen = []

    def fake_resolve(obj, name, point):
        seen.append((name, point))
        return {"Face1": a, "Face2": b}[name]

    monkeypatch.setattr(walls_object, "resolveRootFace", fake_resolve)
    monkeypatch.setattr(walls_gui, "_lastPick",
                        lambda doc, obj, sub, occurrence=0: (sub, occurrence))
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(root, ("Face1", "Face1", "Face2"))]))
    assert [s.Name for s in dims._dimTargets()] == ["a", "b"]
    assert seen == [("Face1", ("Face1", 0)), ("Face1", ("Face1", 1)),
                    ("Face2", ("Face2", 0))]


def test_dim_targets_ignores_tree_roots_and_foreign_objects(monkeypatch):
    root = _root(_segment("a"))
    box = types.SimpleNamespace(
        Name="Box", Label="Box", Proxy=types.SimpleNamespace(Type="Part"))
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(root), _sel(box)]))
    assert dims._dimTargets() == []


def test_dim_targets_deduplicates_and_keeps_order(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    root = _root(a, b)
    monkeypatch.setattr(
        walls_object, "resolveRootFace",
        lambda obj, name, point: {"Face1": a, "Face2": b}[name])
    monkeypatch.setattr(walls_gui, "_lastPick",
                        lambda doc, obj, sub, occurrence=0: None)
    monkeypatch.setattr(FreeCADGui, "Selection", types.SimpleNamespace(
        getSelectionEx=lambda: [_sel(a), _sel(b),
                                _sel(root, ("Face1", "Face2"))]))
    assert [s.Name for s in dims._dimTargets()] == ["a", "b"]


def test_sync_draws_and_clears_with_selection(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    drawn, cleared = [], []
    monkeypatch.setattr(dims, "_dimTargets", lambda: [a])
    monkeypatch.setattr(dims, "addDim", lambda seg: drawn.append(seg) or True)
    monkeypatch.setattr(dims, "removeDim", lambda seg: cleared.append(seg))
    dims.sync()
    assert drawn == [a]
    assert list(dims._nodes.values()) == [a]
    monkeypatch.setattr(dims, "_dimTargets", lambda: [b])
    dims.sync()
    assert cleared == [a]
    assert [s.Name for s in dims._nodes.values()] == ["b"]
    monkeypatch.setattr(dims, "_dimTargets", lambda: [])
    dims.sync()
    assert cleared == [a, b]
    assert dims._nodes == {}


def test_sync_skips_targets_that_cannot_draw(monkeypatch):
    a = _segment("a")
    monkeypatch.setattr(dims, "_dimTargets", lambda: [a])
    monkeypatch.setattr(dims, "addDim", lambda seg: False)
    monkeypatch.setattr(dims, "removeDim", lambda seg: None)
    dims.sync()
    assert dims._nodes == {}


def test_sync_survives_target_errors(monkeypatch):
    def boom():
        raise RuntimeError("no selection")

    monkeypatch.setattr(dims, "_dimTargets", boom)
    dims.sync()  # must not raise
    assert dims._nodes == {}


def test_refresh_redraws_only_dimmed_segments(monkeypatch):
    a = _segment("a")
    b = _segment("b")
    calls = []
    monkeypatch.setattr(dims, "removeDim", lambda seg: calls.append(("rm", seg)))

    def fake_add(seg):
        calls.append(("add", seg))
        return True

    monkeypatch.setattr(dims, "addDim", fake_add)
    dims._nodes[dims._key(a)] = a
    dims.refresh(a)
    assert calls == [("rm", a), ("add", a)]
    assert dims._nodes == {dims._key(a): a}
    calls.clear()
    dims.refresh(b)
    assert calls == []


def test_refresh_drops_segments_that_stop_drawing(monkeypatch):
    a = _segment("a")
    dims._nodes[dims._key(a)] = a
    monkeypatch.setattr(dims, "removeDim", lambda seg: None)
    monkeypatch.setattr(dims, "addDim", lambda seg: False)
    dims.refresh(a)
    assert dims._nodes == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walls/tests/test_dims.py -q`
Expected: FAIL — `AttributeError: module 'archplus.tools.walls.dims' has no attribute '_dimTargets'`

- [ ] **Step 3: Write the Coin builder, mapping and bookkeeping**

Append at the end of `archplus/tools/walls/dims.py`:

```python
_nodes = {}      # (doc name, object name) -> dimmed segment
_observer = None


def _key(obj):
    return (getattr(getattr(obj, "Document", None), "Name", ""), obj.Name)


def _buildNode(chains):
    """The Coin overlay node for one segment: a dimension line and end
    ticks per chain plus one screen-facing label per chain. chains is what
    _dimChains returns. Labels are wrapped in their own SoSeparator so each
    SoTranslation is applied from an identity state."""
    from pivy import coin
    sep = coin.SoSeparator()
    sep.setName(DIM_NODE)
    style = coin.SoDrawStyle()
    style.lineWidth.setValue(_LINE_WIDTH)
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*_DIM_COLOR)
    coords = coin.SoCoordinate3()
    points = []
    index = []

    def segment(a, b):
        i = len(points)
        points.append(a)
        points.append(b)
        index.extend([i, i + 1, -1])

    for line, ticks, _pt, _text in chains:
        for a, b in zip(line, line[1:]):
            segment(a, b)
        for tick in ticks:
            segment(tick[0], tick[1])
    coords.point.setValues(0, len(points), points)
    lineset = coin.SoIndexedLineSet()
    lineset.coordIndex.setValues(0, len(index), index)
    font = coin.SoFont()
    font.name.setValue("Sans")
    font.size.setValue(_FONT_SIZE)
    sep.addChild(style)
    sep.addChild(mat)
    sep.addChild(coords)
    sep.addChild(lineset)
    sep.addChild(font)
    for _line, _ticks, pt, text in chains:
        label = coin.SoSeparator()
        tr = coin.SoTranslation()
        tr.translation.setValue(pt)
        t2 = coin.SoText2()
        t2.string.setValue(text)
        t2.justification.setValue(coin.SoText2.CENTER)
        label.addChild(tr)
        label.addChild(t2)
        sep.addChild(label)
    return sep


def addDim(segment):
    """Draw the length dim overlay on the segment's view provider. True
    when a node was added."""
    try:
        vobj = getattr(segment, "ViewObject", None)
        if vobj is None or getattr(vobj, "RootNode", None) is None:
            return False
        chains = _dimChains(segment)
        if not chains:
            return False
        walls_object.removeFaceHighlight(vobj, DIM_NODE)
        vobj.RootNode.addChild(_buildNode(chains))
        return True
    except Exception:
        return False


def removeDim(segment):
    """Drop the segment's length dim overlay node, if present."""
    try:
        walls_object.removeFaceHighlight(getattr(segment, "ViewObject", None),
                                         DIM_NODE)
    except Exception:
        pass


def _dimTargets():
    """The segments the current selection implies dims for, deduplicated,
    in first-appearance order. Direct segment members dim themselves; a
    wall root with picked faces dims each face's owning segment (resolved
    through its own recorded pick point, like the split command); a tree-
    selected root with no faces implies nothing — spraying every segment
    with dimensions is noise. gui is imported lazily: gui.py imports this
    module at load time."""
    import FreeCADGui
    from archplus.tools.walls import gui as walls_gui
    out = []
    seen = set()
    for sel in FreeCADGui.Selection.getSelectionEx():
        obj = getattr(sel, "Object", None)
        if walls_object.is_segment(obj):
            k = _key(obj)
            if k not in seen:
                seen.add(k)
                out.append(obj)
        elif walls_object.is_root(obj):
            counts = {}
            for name in (getattr(sel, "SubElementNames", None) or ()):
                if not name.startswith("Face"):
                    continue
                occurrence = counts.get(name, 0)
                counts[name] = occurrence + 1
                point = walls_gui._lastPick(getattr(obj, "Document", None),
                                            obj, name, occurrence)
                resolved = walls_object.resolveRootFace(obj, name, point)
                if resolved is None:
                    continue
                seg = resolved[0]
                k = _key(seg)
                if k not in seen:
                    seen.add(k)
                    out.append(seg)
    return out


def sync():
    """Recompute the dimmed set from the current selection and diff it
    against the drawn overlays. Never raises: selection events must not
    break the session."""
    try:
        want = {}
        for seg in _dimTargets():
            want[_key(seg)] = seg
        for key in list(_nodes):
            if key not in want:
                removeDim(_nodes.pop(key))
        for key, seg in want.items():
            if key not in _nodes and addDim(seg):
                _nodes[key] = seg
    except Exception:
        pass


def refresh(segment):
    """Redraw the segment's dim overlay after its shape changed. No-op
    when the segment is not currently dimmed."""
    try:
        key = _key(segment)
        if key not in _nodes:
            return
        removeDim(segment)
        if addDim(segment):
            _nodes[key] = segment
        else:
            _nodes.pop(key, None)
    except Exception:
        pass


class _SelectionDims:
    """Selection observer redrawing the length dims on every selection
    change."""

    def addSelection(self, *_args):
        sync()

    def removeSelection(self, *_args):
        sync()

    def clearSelection(self, *_args):
        sync()

    def setSelection(self, *_args):
        sync()


def install():
    """Register the selection observer once (gui.py import time, like the
    pick-point recorder)."""
    global _observer
    if _observer is not None:
        return
    try:
        import FreeCADGui
        _observer = _SelectionDims()
        FreeCADGui.Selection.addObserver(_observer)
    except Exception:
        _observer = None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --no-project --with pytest python -m pytest archplus/tools/walls/tests/test_dims.py -q`
Expected: PASS (20 tests)

- [ ] **Step 5: Run the full suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: **445 passed**

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/walls/dims.py archplus/tools/walls/tests/test_dims.py
git commit -m "Draw and track the on-select wall length overlay"
```

---

### Task 4: Wiring — selection events and reflows

**Files:**
- Modify: `archplus/tools/walls/gui.py` (import `dims`, call `dims.install()` after the pick-recorder registration)
- Modify: `archplus/tools/walls/object.py` (`_ViewProviderWall.updateData` reflow hook)

**Interfaces:**
- Consumes: `dims.install`, `dims.refresh` (Task 3).
- Produces: the live behavior — dims follow selection in a real session; labels track reflows. No new names.

- [ ] **Step 1: Wire `gui.py`**

In `archplus/tools/walls/gui.py`, add to the top import block (after
`from archplus.tools.walls import model`):

```python
from archplus.tools.walls import dims
```

Then locate the module-level pick-recorder registration block at the bottom
of the split-command section (search for `_ArchPlusPickRecorder`; it ends
with `except Exception:\n        pass`). Immediately after that block, add:

```python
dims.install()
```

(The import order is cycle-free: `dims` imports `object` at module level and `gui` only inside `_dimTargets`. Under the headless fakes `install()` fails silently — the fake `Selection` has no `addObserver` — which the suite relies on.)

- [ ] **Step 2: Wire the reflow hook in `object.py`**

In `archplus/tools/walls/object.py`, replace `_ViewProviderWall.updateData`
(whole method — since the selection-mapping work landed on the base branch
it delegates to the `_ArchPlusWallSelObs` observer; keep that delegation,
add the dim refresh) with:

```python
    def updateData(self, obj, prop):
        """Refresh the highlight overlay when the shape is rebuilt under a
        live face or edge selection; the overlay keeps its old tessellation
        otherwise. The length dim overlay redraws the same way."""
        if prop != "Shape":
            return
        try:
            import FreeCADGui
            observer = getattr(FreeCADGui, "_ArchPlusWallSelObs", None)
            if observer is not None:
                observer.refresh(obj)
        except Exception:
            pass
        # The lazy import is required: dims imports this module at its own
        # load time, so a module-level import here would cycle.
        try:
            from archplus.tools.walls import dims
            dims.refresh(obj)
        except Exception:
            pass
```

- [ ] **Step 3: Run the full suite**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: **449 passed** (wiring changes no headless behavior — `install()` fails silently under the fakes, `refresh()` no-ops because `_nodes` is empty)

- [ ] **Step 4: Commit**

```bash
git add archplus/tools/walls/gui.py archplus/tools/walls/object.py
git commit -m "Wire the length overlay into selection and reflow"
```

---

### Task 5: FreeCAD-session verification (W25)

**Files:**
- Modify: `archplus/freecad_tests/verify_walls.py` (add `_w25_selection_dims`, register it in `run()`)

**Interfaces:**
- Consumes: `_line_sketch`, `_pump` (flushes the selection observer's deferred QTimer events), `h.check`, `walls_object`, `dims.DIM_NODE`.
- Produces: W25 PASS/FAIL lines in the FreeCAD verification log.

- [ ] **Step 1: Write the W25 check**

Insert after `_w24_click_highlight` in
`archplus/freecad_tests/verify_walls.py`:

```python
def _w25_selection_dims(doc):
    import FreeCADGui
    from pivy import coin
    from archplus.tools.walls import dims
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    vobj = seg.ViewObject

    def dim_nodes():
        return [ch for ch in (vobj.RootNode.getChildren() or [])
                if ch.getName() == dims.DIM_NODE]

    def label_parts():
        named = dim_nodes()
        if not named:
            return None, None
        texts = [ch for ch in named[0].getChildren()
                 if isinstance(ch, coin.SoText2)]
        trans = [ch for ch in named[0].getChildren()
                 if isinstance(ch, coin.SoTranslation)]
        if not texts or not trans:
            return None, None
        return str(texts[0].string[0]), trans[0].translation.getValue()[2]

    expected = FreeCAD.Units.Quantity(4000.0, FreeCAD.Units.Length).UserString
    FreeCADGui.Selection.clearSelection()
    FreeCADGui.Selection.addSelection(seg)
    _pump()
    text, z = label_parts()
    h.check("W25 selecting a segment draws the length dim",
            len(dim_nodes()) == 1 and text == expected,
            detail="text=%r" % text)
    h.check("W25 the label rides above the wall top",
            z is not None and abs(z - 2940.0) < 1e-6, detail="z=%r" % z)
    coords = [ch for ch in (dim_nodes()[0].getChildren() if dim_nodes() else [])
              if isinstance(ch, coin.SoCoordinate3)]
    h.check("W25 the dim line and ticks carry points",
            bool(coords) and coords[0].point.getNum() >= 6)
    seg.Height = 2000
    doc.recompute()
    text, z = label_parts()
    h.check("W25 the dim tracks reflows",
            z is not None and abs(z - 2100.0) < 1e-6, detail="z=%r" % z)
    seg.Height = 2800
    doc.recompute()
    FreeCADGui.Selection.clearSelection()
    _pump()
    h.check("W25 deselecting removes the dim", len(dim_nodes()) == 0)
    pnt = seg.Shape.getElement("Face1").CenterOfGravity
    FreeCADGui.Selection.addSelection(wall, "Face1",
                                      pnt.x, pnt.y, pnt.z)
    _pump()
    h.check("W25 a picked wall face dims its owning segment",
            len(dim_nodes()) == 1)
    FreeCADGui.Selection.clearSelection()
    _pump()
    h.check("W25 clearing drops it again", len(dim_nodes()) == 0)
```

(The 2940/2100 expectations: lift = height + max(100, 5 % height); the
`Quantity` comparison keeps the label check unit-schema-proof. The root
pick mirrors W16's proven `addSelection(wall, "Face1", x, y, z)` pattern;
the base branch's deferred redirect then rewires it to the segment — the
dim survives both routes. `_pump()` flushes the observer's deferred
events so the selection state is settled before each check.)

- [ ] **Step 2: Register the check**

In `verify_walls.py`'s `run()`, add `_w25_selection_dims(doc)` directly
after `_w24_click_highlight(doc)` (and before the
`doc = h.fresh_doc()` / `_w7_reload(doc)` lines).

- [ ] **Step 3: Run the FreeCAD session suite**

Run (Windows host): `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: every W-line PASS including the six new `W24` checks; `0 check(s) failed`.

- [ ] **Step 4: Commit**

```bash
git add archplus/freecad_tests/verify_walls.py
git commit -m "Verify the wall length overlay in the FreeCAD session"
```

---

### Task 6: Docs + final verification

**Files:**
- Modify: `docs/ROADMAP.md` (tick the Walls backlog item)
- Modify: `docs/TOOLS.md` (document the overlay in the Walls section)

- [ ] **Step 1: Update the roadmap**

In `docs/ROADMAP.md`, Walls section, replace the backlog item

```
- [ ] Backlog — live measurements in the 3D view: on-select dimension
  lines and a length label rendered beside the selected segment (Coin
  overlay, dimTracker-style, no document objects; label tracks reflows).
```

with

```
- [x] Shipped — on-select length dimensions in the 3D view: a dimension
  line with oblique end ticks and a length label drawn above the selected
  segment (Coin overlay, no document objects; tracks reflows; see
  [TOOLS.md](TOOLS.md#walls)).
```

Leave the endpoint-handles backlog item untouched.

- [ ] **Step 2: Update the user guide**

In `docs/TOOLS.md`, Walls section, add this bullet as the last item of the
feature bullet list (immediately before `### Edit Wall panel`):

```
- **On-select length dimension** — selecting a wall segment, or clicking
  its face in the 3D view, draws a dimension line above the wall's top
  edge with oblique end ticks and the segment's length; deselecting
  removes it. Multi-selection dims every picked segment.
```

- [ ] **Step 3: Run both suites**

Run: `uv run --no-project --with pytest python -m pytest -q`
Expected: **445 passed**

Run: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: `0 check(s) failed`

- [ ] **Step 4: Commit**

```bash
git add docs/ROADMAP.md docs/TOOLS.md
git commit -m "Document the on-select wall length overlay"
```
