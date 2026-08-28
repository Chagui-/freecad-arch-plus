# ArchPlus Wall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A sketch-driven Wall tool where a wall references (never owns) a shared sketch and builds one extruded segment group per claimed sketch edge, with inherited config, per-segment opening cuts, and task panels.

**Architecture:** One FreeCAD object class (`Part::FeaturePython` + `GroupExtensionPython`) plays both roles: the `Wall` root (no shape, holds defaults + hosted openings) and nestable `WallSegment` children (fused extrusions of claimed edges minus intersecting openings). Pure claim/inheritance/matching logic lives in a FreeCAD-free `model.py` so headless pytest drives it; `object.py` is the thin FreeCAD proxy layer; `gui.py` holds commands, ViewProvider and task panels.

**Tech Stack:** Python, FreeCAD 1.1 (`App`, `Part`, `Sketcher`), PySide (QtGui/QtCore), pytest with the repo's conftest fakes, FreeCAD-session verification via `archplus/freecad_tests`.

**Spec:** `docs/superpowers/specs/2026-08-28-wall-segments-design.md` — the plan argues from the spec; read both.

## Global Constraints

- FreeCAD 1.1; all lengths handled internally in **mm** (FreeCAD's base unit).
- New files carry the repo's LGPL-2.1-or-later header block (copy from `archplus/tools/stairs/object.py` lines 1-32, updating the copyright line to `Copyright (c) 2026 Andres <andres@neltu.me>`).
- No code comments beyond module docstrings/header; docstrings for functions.
- Commands register as `ArchPlus_Walls` / `ArchPlus_WallSplit`; the toolbar list lives in `InitGui.py`.
- Type strings: root `"Wall"`, children `"WallSegment"` (via `proxy.Type`).
- Child conventions: `Width`/`Height` `0 = inherit`; `Align` enum starts with `"Inherit"`.
- Headless pytest must never import FreeCAD; GUI modules may import FreeCAD/PySide at module scope (conftest fakes cover them).
- All work on branch `feat/wall-segments` (already created, checked out).
- Run the full suite before the final commit: `pytest` from the repo root, plus the FreeCAD-session suite (`"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`).

## File Structure

```
archplus/tools/walls/
    __init__.py              empty package marker
    model.py                 pure: effective_config, ClaimNode, resolve_claims,
                             match_edge, _point_seg_dist
    object.py                FreeCAD proxy _Wall, footprint(), opening_volume(),
                             makeWall(), makeSegment(), splitSegment(),
                             wall_root(), is_segment(), all_segments(),
                             effectiveValues(), _ensureVP-free
    gui.py                   _ViewProviderWall, WallPlusCommand, WallSplitCommand,
                             WallPlusTaskPanel, WallSegmentTaskPanel,
                             showWallPanel(), showSegmentPanel(), ICON
    resources/icons/         WallPlus.svg, dimensions_ref_plan.svg,
                             align_offset_ref.svg
    tests/test_model.py      headless tests for model.py
    tests/test_panel.py      headless tests for panel collect/load logic
archplus/freecad_tests/verify_walls.py    FreeCAD-session verification
```

Modified: `InitGui.py` (toolbar list), `archplus/freecad_tests/run_all.py`
(registration), `archplus/tools/windows/object.py`, `archplus/tools/doors/object.py`,
`archplus/tools/windows/gui.py`, `archplus/tools/doors/gui.py` (hosting
compatibility), `docs/TOOLS.md`, `docs/ROADMAP.md`.

---

### Task 1: Package scaffold + pure claim/inheritance model

**Files:**
- Create: `archplus/tools/walls/__init__.py`
- Create: `archplus/tools/walls/model.py`
- Create: `archplus/tools/walls/tests/test_model.py`
- Create: `archplus/tools/walls/tests/__init__.py`

**Interfaces:**
- Produces (all in `archplus.tools.walls.model`):
  - `DEFAULT_CONFIG = {"Width": 300.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}`
  - `effective_config(chain, defaults=None) -> {"Width": float, "Height": float, "Align": str, "Offset": float}`
  - `class ClaimNode(node, claimed, rest=False)` with attributes `.node`, `.claimed` (frozenset of subname strings), `.rest` (bool), `.children` (list)
  - `resolve_claims(nodes, sketch_edge_names) -> (built, warnings)` where `built: {node: frozenset(subnames)}`, `warnings: list[str]`
  - `match_edge(polylines, point, tol=1.0) -> int | None`
  - `INHERIT_ALIGN = "Inherit"`

- [ ] **Step 1: Create the package markers**

```bash
mkdir -p archplus/tools/walls/tests archplus/tools/walls/resources/icons
touch archplus/tools/walls/__init__.py archplus/tools/walls/tests/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Write `archplus/tools/walls/tests/test_model.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Pure wall-model tests: config inheritance, claim resolution, edge matching.
# model.py must stay importable without FreeCAD.

from archplus.tools.walls import model


def _node(key, claimed=(), rest=False, children=()):
    n = model.ClaimNode(key, claimed, rest=rest)
    n.children = list(children)
    return n


# --- effective_config ------------------------------------------------------

def test_config_leaf_overrides_parent():
    cfg = model.effective_config([
        {"Width": 200.0, "Height": None, "Align": "Inherit"},
        {"Width": 300.0, "Height": 2800.0, "Align": "Center"},
    ])
    assert cfg == {"Width": 200.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}


def test_config_zero_means_inherit():
    cfg = model.effective_config([
        {"Width": 0, "Height": 0, "Align": "Inherit"},
        {"Width": 400.0, "Height": 2600.0, "Align": "Left"},
    ])
    assert cfg["Width"] == 400.0 and cfg["Height"] == 2600.0 and cfg["Align"] == "Left"


def test_config_falls_back_to_defaults():
    cfg = model.effective_config([{"Width": None, "Height": None, "Align": None}])
    assert cfg == {"Width": 300.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}


def test_config_offset_comes_from_the_root_dict():
    cfg = model.effective_config([
        {"Width": 200.0},
        {"Width": 300.0, "Offset": 50.0},
    ])
    assert cfg["Offset"] == 50.0


# --- resolve_claims ----------------------------------------------------------

EDGES = ["Edge1", "Edge2", "Edge3", "Edge4"]


def test_rest_child_claims_everything_unclaimed():
    rest = _node("rest", rest=True)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[rest.node] == frozenset(EDGES)
    assert warnings == []


def test_explicit_claim_beats_rest():
    rest = _node("rest", rest=True)
    ext = _node("ext", ("Edge1",))
    built, warnings = model.resolve_claims([rest, ext], EDGES)
    assert built[ext.node] == frozenset(["Edge1"])
    assert built[rest.node] == frozenset(["Edge2", "Edge3", "Edge4"])


def test_group_excludes_descendant_claims():
    rest = _node("rest", rest=True)
    short = _node("short", ("Edge2",))
    rest.children.append(short)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[short.node] == frozenset(["Edge2"])
    assert built[rest.node] == frozenset(["Edge1", "Edge3", "Edge4"])


def test_conflicting_claims_build_nowhere_with_warning():
    a = _node("a", ("Edge1", "Edge2"))
    b = _node("b", ("Edge1",))
    built, warnings = model.resolve_claims([a, b], EDGES)
    assert built[a.node] == frozenset(["Edge2"])
    assert built[b.node] == frozenset()
    assert any("Edge1" in w for w in warnings)


def test_two_rest_children_warns_and_keeps_first():
    r1 = _node("r1", rest=True)
    r2 = _node("r2", rest=True)
    built, warnings = model.resolve_claims([r1, r2], EDGES)
    assert built[r1.node] == frozenset(EDGES)
    assert built[r2.node] == frozenset()
    assert any("one rest" in w for w in warnings)


def test_rest_with_explicit_edges_warns_and_ignores_them():
    rest = _node("rest", ("Edge1",), rest=True)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[rest.node] == frozenset(EDGES)
    assert any("explicit" in w for w in warnings)


def test_nested_rest_warns_and_treats_as_normal():
    rest = _node("rest", rest=True)
    bad = _node("bad", ("Edge3",), rest=True)
    rest.children.append(bad)
    built, warnings = model.resolve_claims([rest], EDGES)
    assert built[bad.node] == frozenset(["Edge3"])
    assert any("direct child" in w for w in warnings)


def test_no_rest_leaves_new_edges_unbuilt():
    a = _node("a", ("Edge1",))
    built, warnings = model.resolve_claims([a], EDGES)
    assert built[a.node] == frozenset(["Edge1"])
    assert frozenset(["Edge2", "Edge3", "Edge4"]).isdisjoint(built[a.node])


def test_claim_on_missing_edge_warns_and_is_dropped():
    a = _node("a", ("Edge9",))
    built, warnings = model.resolve_claims([a], EDGES)
    assert built[a.node] == frozenset()
    assert any("Edge9" in w for w in warnings)


# --- match_edge --------------------------------------------------------------

def test_match_edge_finds_nearest_polyline():
    polylines = [
        [(0.0, 0.0, 0.0), (4000.0, 0.0, 0.0)],
        [(0.0, 3000.0, 0.0), (4000.0, 3000.0, 0.0)],
    ]
    assert model.match_edge(polylines, (2000.0, 3025.0, 0.0)) == 1
    assert model.match_edge(polylines, (2000.0, 10.0, 0.0)) == 0


def test_match_edge_respects_tolerance():
    polylines = [[(0.0, 0.0, 0.0), (4000.0, 0.0, 0.0)]]
    assert model.match_edge(polylines, (2000.0, 50.0, 0.0), tol=1.0) is None
    assert model.match_edge(polylines, (2000.0, 0.5, 0.0), tol=1.0) == 0


def test_match_edge_empty_inputs():
    assert model.match_edge([], (0.0, 0.0, 0.0)) is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest archplus/tools/walls/tests/test_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'archplus.tools.walls.model'`

- [ ] **Step 4: Write the model**

Write `archplus/tools/walls/model.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Pure logic for the Walls tool: config inheritance, claim resolution and
# edge matching. No FreeCAD imports, so pytest drives this headlessly;
# object.py converts document objects into the plain data these functions eat.

DEFAULT_CONFIG = {"Width": 300.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}

INHERIT_ALIGN = "Inherit"


def effective_config(chain, defaults=None):
    """Resolve config over a leaf-first chain of property dicts.

    chain: list of dicts, leaf (self) first, then each ancestor, root last.
    Width/Height: None or 0 means inherit from the next dict. Align: None or
    "Inherit" means inherit. Missing keys inherit too. Falls back to
    DEFAULT_CONFIG after the chain.

    Returns {"Width": float, "Height": float, "Align": str, "Offset": float}.
    """
    defaults = defaults if defaults is not None else DEFAULT_CONFIG
    width = height = align = offset = None
    for props in chain:
        if width is None:
            w = props.get("Width")
            width = float(w) if w not in (None, 0) else None
        if height is None:
            h = props.get("Height")
            height = float(h) if h not in (None, 0) else None
        if align is None:
            a = props.get("Align")
            align = a if a not in (None, INHERIT_ALIGN) else None
        if offset is None:
            offset = props.get("Offset")
    return {
        "Width": width if width is not None else float(defaults["Width"]),
        "Height": height if height is not None else float(defaults["Height"]),
        "Align": align if align is not None else defaults["Align"],
        "Offset": offset if offset is not None else float(defaults["Offset"]),
    }


class ClaimNode:
    """One segment in the claim tree (plain data; node identity is the
    document object, passed in as an opaque handle)."""

    def __init__(self, node, claimed, rest=False):
        self.node = node
        self.claimed = frozenset(claimed)
        self.rest = rest
        self.children = []


def resolve_claims(nodes, sketch_edge_names):
    """Distribute sketch edges over a claim tree.

    nodes: list of ClaimNode roots (direct children of the wall, in order).
    sketch_edge_names: list of edge subnames, in sketch order.

    Returns (built, warnings):
      built: {node: frozenset(subnames)} - edges each node extrudes
      warnings: list[str] - one message per problem found
    """
    warnings = []

    for n in nodes:
        for d in _walk_descendants(n):
            if d.rest:
                warnings.append(
                    "Rest only applies to direct children of the wall; "
                    "segment '%s' treated as normal"
                    % getattr(d.node, "Label", d.node))
                d.rest = False
    for n in nodes:
        if n.rest and n.claimed:
            warnings.append(
                "Rest segment '%s' ignores its explicit edges"
                % getattr(n.node, "Label", n.node))
            n.claimed = frozenset()
    rest_nodes = [n for n in nodes if n.rest]
    if len(rest_nodes) > 1:
        for extra in rest_nodes[1:]:
            warnings.append(
                "Only one rest segment is allowed; '%s' treated as normal"
                % getattr(extra.node, "Label", extra.node))
            extra.rest = False
        rest_nodes = rest_nodes[:1]

    sketch_set = set(sketch_edge_names)

    owners = {}
    for node, subs in _iter_claims(nodes):
        for sub in subs:
            if sub not in sketch_set:
                warnings.append("Claim on missing edge %s ignored" % sub)
                continue
            owners.setdefault(sub, []).append(node)
    conflicted = {sub for sub, ns in owners.items() if len(ns) > 1}
    for sub in sorted(conflicted):
        warnings.append(
            "Edge %s claimed by several segments; it builds nowhere" % sub)

    claimed_set = set(owners) - conflicted
    rest_edges = sketch_set - claimed_set if rest_nodes else frozenset()
    rest_node = rest_nodes[0] if rest_nodes else None

    built = {}

    def assign(n):
        below = frozenset().union(*(assign(c) for c in n.children)) \
            if n.children else frozenset()
        edges = set(n.claimed) - conflicted - below
        if n is rest_node:
            edges |= (rest_edges - below)
        built[n.node] = frozenset(edges)
        return edges | below

    for n in nodes:
        assign(n)
    return built, warnings


def match_edge(polylines, point, tol=1.0):
    """Nearest edge index to `point`, within tol, or None.

    polylines: sequence of point lists [(x, y, z), ...] in global coords.
    point: (x, y, z).
    """
    best = None
    best_d = float("inf")
    for i, poly in enumerate(polylines):
        for a, b in zip(poly, poly[1:]):
            d = _point_seg_dist(point, a, b)
            if d < best_d:
                best_d = d
                best = i
    return best if best_d <= tol else None


def _point_seg_dist(p, a, b):
    ax, ay, az = a
    bx, by, bz = b
    px, py, pz = p
    abx, aby, abz = bx - ax, by - ay, bz - az
    apx, apy, apz = px - ax, py - ay, pz - az
    denom = abx * abx + aby * aby + abz * abz
    t = 0.0 if denom == 0 else max(
        0.0, min(1.0, (apx * abx + apy * aby + apz * abz) / denom))
    cx, cy, cz = ax + t * abx, ay + t * aby, az + t * abz
    dx, dy, dz = px - cx, py - cy, pz - cz
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _walk_descendants(n):
    for c in n.children:
        yield c
        for d in _walk_descendants(c):
            yield d


def _iter_claims(nodes):
    for n in nodes:
        yield n, n.claimed
        for node, subs in _iter_claims(n.children):
            yield node, subs
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest archplus/tools/walls/tests/test_model.py -v`
Expected: PASS (14 passed)

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/walls/__init__.py archplus/tools/walls/model.py \
        archplus/tools/walls/tests/
git commit -m "Add the pure claim and inheritance model for walls"
```

---

### Task 2: Wall objects — proxy, factories, execute

**Files:**
- Create: `archplus/tools/walls/object.py`
- Create: `archplus/freecad_tests/verify_walls.py`
- Modify: `archplus/freecad_tests/run_all.py`

**Interfaces:**
- Consumes: `model.DEFAULT_CONFIG`, `model.effective_config`, `model.ClaimNode`, `model.resolve_claims`, `model.match_edge` (Task 1).
- Produces (in `archplus.tools.walls.object`):
  - `class _Wall` — proxy with `.Type` in `("Wall", "WallSegment")`, `setProperties(obj, root)`, `onChanged(obj, prop)`, `execute(obj)`
  - `makeWall(doc=None, sketch=None, name="Wall") -> wall` (root + one rest child "Segments")
  - `makeSegment(parent, name="Segments") -> segment` (nesting supported; `Wall` link = root; `Base` seeded from parent)
  - `splitSegment(segment, subnames, name=None) -> new segment` (moves claims into a new sibling)
  - `wall_root(segment) -> root wall or None`
  - `is_segment(obj) -> bool`
  - `all_segments(root) -> list[segment]`
  - `effectiveValues(segment) -> {"Width": float, "Height": float, "Align": str, "Offset": float}`
  - `footprint(edge, width, align, offset) -> Part.Face | None`
  - `opening_volume(win, root) -> Part.Shape | None`

- [ ] **Step 1: Write `archplus/tools/walls/object.py`**

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WallsPlus objects: a wall that references a shared sketch (never owns it)
# and builds one segment group per claimed sketch edge. One class plays both
# roles: the Wall root (no shape; defaults + hosted openings) and nestable
# WallSegment children (fused extrusions minus intersecting openings).

import FreeCAD
from FreeCAD import Vector

from archplus.tools.walls import model

TYPE_WALL = "Wall"
TYPE_SEGMENT = "WallSegment"


class _Wall:
    """Proxy for both roles: the root wall and its segments."""

    def __init__(self, obj, root=False):
        obj.Proxy = self
        self.Type = TYPE_WALL if root else TYPE_SEGMENT
        self.setProperties(obj, root)

    def setProperties(self, obj, root):
        pl = obj.PropertiesList
        if "Base" not in pl:
            obj.addProperty("App::PropertyLink", "Base", "Wall",
                            "The base sketch; shared freely with other tools")
        if root:
            if "Width" not in pl:
                obj.addProperty("App::PropertyLength", "Width", "Wall",
                                "Default wall thickness (mm)")
            if "Height" not in pl:
                obj.addProperty("App::PropertyLength", "Height", "Wall",
                                "Default wall height above the sketch plane (mm)")
            if "Align" not in pl:
                obj.addProperty("App::PropertyEnumeration", "Align", "Wall",
                                "Which side of the baseline the wall extends from")
                obj.Align = ["Center", "Left", "Right"]
                obj.Align = "Center"
            if "Offset" not in pl:
                obj.addProperty("App::PropertyDistance", "Offset", "Wall",
                                "Extra distance between the baseline and the wall "
                                "(Left/Right only)")
            if "Subtractions" not in pl:
                obj.addProperty("App::PropertyLinkList", "Subtractions", "Wall",
                                "Hosted doors/windows; each segment cuts the ones "
                                "intersecting it")
            if "Tag" not in pl:
                obj.addProperty("App::PropertyString", "Tag", "Wall",
                                "Reference code shown in schedules")
        else:
            if "Wall" not in pl:
                obj.addProperty("App::PropertyLink", "Wall", "Wall",
                                "The wall this segment belongs to")
            if "Edges" not in pl:
                obj.addProperty("App::PropertyLinkSubList", "Edges", "Wall",
                                "Claimed sketch edges; empty with Rest=true claims "
                                "everything unclaimed")
            if "Rest" not in pl:
                obj.addProperty("App::PropertyBool", "Rest", "Wall",
                                "Claim every sketch edge no other segment claims "
                                "(one per wall)")
            if "Width" not in pl:
                obj.addProperty("App::PropertyLength", "Width", "Wall",
                                "0 = inherit from the wall/group")
            if "Height" not in pl:
                obj.addProperty("App::PropertyLength", "Height", "Wall",
                                "0 = inherit from the wall/group")
            if "Align" not in pl:
                obj.addProperty("App::PropertyEnumeration", "Align", "Wall",
                                "Inherit = use the wall/group alignment")
                obj.Align = ["Inherit", "Center", "Left", "Right"]
                obj.Align = "Inherit"

    def onChanged(self, obj, prop):
        if prop == "Base" and obj.Base is not None and self.Type == TYPE_WALL:
            for seg in all_segments(obj):
                seg.Base = obj.Base

    def execute(self, obj):
        import Part
        if self.Type == TYPE_WALL:
            obj.Shape = Part.Shape()
            self._reportClaims(obj)
            return
        self._buildSegment(obj)

    def _reportClaims(self, obj):
        sketch = obj.Base
        if sketch is None or not hasattr(sketch, "Shape"):
            return
        names = _sketchEdgeNames(sketch)
        nodes = [_claimNode(n) for n in getattr(obj, "Group", []) if is_segment(n)]
        built, warnings = model.resolve_claims(nodes, names)
        for w in warnings:
            FreeCAD.Console.PrintWarning("ArchPlus: %s\n" % w)
        claimed = set().union(*built.values()) if built else set()
        has_rest = any(getattr(n, "Rest", False) for n in nodes)
        if not has_rest:
            unclaimed = [n for n in names if n not in claimed]
            if unclaimed:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: %d sketch edge(s) unclaimed and no rest segment "
                    "to build them\n" % len(unclaimed))
        for win in list(getattr(obj, "Subtractions", None) or []):
            sub = opening_volume(win, obj)
            if sub is None:
                continue
            hit = False
            for seg in all_segments(obj):
                if seg.Shape.isNull():
                    continue
                if seg.Shape.BoundBox.intersect(sub.BoundBox):
                    hit = True
                    break
            if not hit:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: opening '%s' intersects no segment and is not "
                    "applied\n" % win.Label)

    def _buildSegment(self, obj):
        import Part
        sketch = obj.Base
        if sketch is None or not hasattr(sketch, "Shape"):
            obj.Shape = Part.Shape()
            return
        subnames = self._claimedEdges(obj)
        if not subnames:
            obj.Shape = Part.Shape()
            return
        cfg = effectiveValues(obj)
        height = cfg["Height"]
        if height <= 0:
            obj.Shape = Part.Shape()
            return
        normal = sketch.Placement.Rotation.multVec(Vector(0, 0, 1))
        solids = []
        for sub in subnames:
            try:
                edge = sketch.Shape.getElement(sub)
            except Exception:
                continue
            edge.transformShape(sketch.Placement.toMatrix())
            face = footprint(edge, cfg["Width"], cfg["Align"], cfg["Offset"])
            if face is None:
                continue
            solids.append(face.extrude(normal * height))
        if not solids:
            obj.Shape = Part.Shape()
            return
        shape = solids.pop(0)
        for s in solids:
            shape = shape.fuse(s)
        root = obj.Wall
        if root is not None:
            for win in list(getattr(root, "Subtractions", None) or []):
                sub = opening_volume(win, root)
                if sub is None or sub.Volume == 0:
                    continue
                if not shape.BoundBox.intersect(sub.BoundBox):
                    continue
                if shape.common(sub).Volume < 1e-9:
                    continue
                try:
                    shape = shape.cut(sub)
                except Exception:
                    pass
        obj.Shape = shape

    def _claimedEdges(self, obj):
        root = obj.Wall or obj
        sketch = root.Base
        if sketch is None or not hasattr(sketch, "Shape"):
            return []
        nodes = [_claimNode(n) for n in getattr(root, "Group", []) if is_segment(n)]
        built, _warnings = model.resolve_claims(nodes, _sketchEdgeNames(sketch))
        return sorted(built.get(obj, frozenset()))


def _claimNode(obj):
    subs = []
    for _link, subs_ in getattr(obj, "Edges", None) or []:
        subs.extend(subs_)
    node = model.ClaimNode(obj, subs, bool(getattr(obj, "Rest", False)))
    node.children = [_claimNode(c) for c in getattr(obj, "Group", [])
                     if is_segment(c)]
    return node


def _sketchEdgeNames(sketch):
    return [n for n in sketch.Shape.ElementMap if n.startswith("Edge")]


def is_segment(obj):
    return getattr(getattr(obj, "Proxy", None), "Type", None) == TYPE_SEGMENT


def wall_root(segment):
    return getattr(segment, "Wall", None)


def all_segments(root):
    out = []
    for o in getattr(root, "Group", []) or []:
        if is_segment(o):
            out.append(o)
            out.extend(all_segments(o))
    return out


def parent_group(obj):
    for parent in obj.InList:
        if hasattr(parent, "Group") and obj in parent.Group:
            return parent
    return None


def effectiveValues(segment):
    """Resolved config for a segment (walks the tree, falls back to defaults)."""
    chain = []
    node = segment
    seen = set()
    while node is not None and node.Name not in seen:
        seen.add(node.Name)
        chain.append({
            "Width": _propValue(node, "Width"),
            "Height": _propValue(node, "Height"),
            "Align": getattr(node, "Align", None),
            "Offset": _propValue(node, "Offset"),
        })
        node = parent_group(node)
    return model.effective_config(chain)


def _propValue(obj, name):
    prop = getattr(obj, name, None)
    if prop is None:
        return None
    try:
        return float(prop.Value)
    except Exception:
        return None


def footprint(edge, width, align, offset):
    """The wall footprint face for one sketch edge, in global coords."""
    import Part
    try:
        if align == "Center":
            a = edge.makeOffset2D(offset - width / 2.0)
            b = edge.makeOffset2D(offset + width / 2.0)
        else:
            side = 1.0 if align == "Right" else -1.0
            a = edge.makeOffset2D(side * offset)
            b = edge.makeOffset2D(side * (offset + width))
        pa1, pa2 = a.Vertexes[0].Point, a.Vertexes[-1].Point
        pb1, pb2 = b.Vertexes[0].Point, b.Vertexes[-1].Point
        wire = Part.Wire([Part.Edge(Part.LineSegment(pa1, pb1)), b,
                          Part.Edge(Part.LineSegment(pb2, pa2)), a])
        return Part.Face(wire)
    except Exception:
        return None


def opening_volume(win, root):
    """The subtraction volume for a hosted door/window (or None)."""
    proxy = getattr(win, "Proxy", None)
    if proxy is not None and hasattr(proxy, "getSubVolume"):
        try:
            return proxy.getSubVolume(win, host=root)
        except Exception:
            return None
    return getattr(win, "Shape", None)


def makeWall(doc=None, sketch=None, name="Wall"):
    """Create the wall root plus one rest child. Returns the root."""
    doc = doc or FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    obj.addExtension("App::GroupExtensionPython", None)
    _Wall(obj, root=True)
    obj.Base = sketch
    obj.Width = "300 mm"
    obj.Height = "2800 mm"
    obj.Align = "Center"
    obj.Offset = "0 mm"
    seg = makeSegment(obj, name="Segments")
    seg.Rest = True
    return obj


def makeSegment(parent, name="Segments"):
    """Create a segment as a child of `parent` (the wall root or a segment)."""
    obj = parent.Document.addObject("Part::FeaturePython", name)
    obj.addExtension("App::GroupExtensionPython", None)
    _Wall(obj, root=False)
    root = wall_root(parent) if is_segment(parent) else parent
    obj.Wall = root
    obj.Base = parent.Base
    obj.Align = "Inherit"
    parent.addObject(obj)
    return obj


def splitSegment(segment, subnames, name=None):
    """Move claimed edges from `segment` into a new sibling segment."""
    parent = parent_group(segment) or wall_root(segment)
    new = makeSegment(parent, name or "Segments")
    new.Edges = [(new.Base, sub) for sub in subnames]
    if not segment.Rest:
        remaining = []
        for link, subs in getattr(segment, "Edges", None) or []:
            subs = tuple(s for s in subs if s not in subnames)
            if subs:
                remaining.append((link, subs))
        segment.Edges = remaining
    return new
```

Note for the implementer: `makeWall`/`makeSegment` create the ViewProvider later (Task 4 attaches it); objects must function without it.

- [ ] **Step 2: Write the first verification checks**

Write `archplus/freecad_tests/verify_walls.py`:

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Wall checks: creation, claims, config inheritance, split, sketch edits,
# hosted openings, reload. Mirrors the spec's verify list.

from archplus.freecad_tests import _harness as h

import FreeCAD
import Part

from archplus.tools.walls import object as walls_object


def _line_sketch(doc, lines, name="FloorPlan"):
    sk = doc.addObject("Sketcher::SketchObject", name)
    for (x1, y1), (x2, y2), construction in lines:
        sk.addGeometry(Part.LineSegment(FreeCAD.Vector(x1, y1, 0),
                                        FreeCAD.Vector(x2, y2, 0)),
                       construction)
    return sk


def _expected_volume(width, height, lengths):
    return width * height * sum(lengths)


def _w1_creation(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
        ((0, 6000), (4000, 6000), True),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    h.check("W1 root type and single child",
            wall.Proxy.Type == "Wall" and len(wall.Group) == 1)
    seg = wall.Group[0]
    h.check("W1 rest child defaults",
            seg.Proxy.Type == "WallSegment" and seg.Rest and seg.Wall is wall)
    h.check("W1 rest child builds 2 edges, construction excluded",
            abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000, 4000])) < 1e-3)
    return wall, sk


def _w2_inheritance(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    wall.Width = "400 mm"
    doc.recompute()
    rest = wall.Group[0]
    h.check("W2 root width change reaches the rest child",
            abs(rest.Shape.Volume - _expected_volume(400, 2800, [4000, 4000])) < 1e-3)
    ext = walls_object.makeSegment(wall, name="exterior")
    ext.Edges = [(sk, ("Edge2",))]
    doc.recompute()
    h.check("W2 explicit claim removed from rest",
            abs(rest.Shape.Volume - _expected_volume(400, 2800, [4000])) < 1e-3)
    h.check("W2 new sibling builds its claim",
            abs(ext.Shape.Volume - _expected_volume(400, 2800, [4000])) < 1e-3)
    short = walls_object.makeSegment(ext, name="short")
    short.Edges = [(sk, ("Edge1",))]
    short.Height = "2200 mm"
    doc.recompute()
    h.check("W2 nested child overrides height and inherits width",
            abs(short.Shape.Volume - _expected_volume(400, 2200, [4000])) < 1e-3)
    h.check("W2 ancestor excludes descendant claims (rest builds nothing)",
            rest.Shape.Volume < 1e-3)
    h.check("W2 sibling unaffected by nested child",
            abs(ext.Shape.Volume - _expected_volume(400, 2800, [4000])) < 1e-3)
    return wall, sk


def _w3_sketch_edits(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    sk.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 6000, 0),
                                    FreeCAD.Vector(4000, 6000, 0)), False)
    doc.recompute()
    h.check("W3 new sketch edge lands in the rest child",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000] * 3)) < 1e-3)
    sk.delGeometry(3)
    doc.recompute()
    h.check("W3 deleted edge drops from the rest child",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000, 4000])) < 1e-3)
    sk.movePoint(0, 1, FreeCAD.Vector(5000, 0, 0))
    doc.recompute()
    h.check("W3 moved vertex: claim follows the edge",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [5000, 4000])) < 1e-3)
    return wall, sk


def run():
    doc = h.fresh_doc()
    _w1_creation(doc)
    _w2_inheritance(doc)
    _w3_sketch_edits(doc)
```

- [ ] **Step 3: Register the verifier**

In `archplus/freecad_tests/run_all.py`: add `from archplus.freecad_tests import verify_walls` next to the other verify imports, and `_run_one("verify_walls", verify_walls.run)` after the `verify_sketch_visibility` line.

- [ ] **Step 4: Run headless tests (must stay green)**

Run: `pytest -v`
Expected: PASS — all existing tests plus the 14 model tests.

- [ ] **Step 5: Run the FreeCAD verification**

Run: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: PASS — all existing checks plus W1/W2/W3. If a check fails, read the `archplus_verify.log` temp file for the measured detail and fix `object.py` accordingly (do not weaken the check).

- [ ] **Step 6: Commit**

```bash
git add archplus/tools/walls/object.py archplus/freecad_tests/
git commit -m "Add wall and segment objects with claim-driven extrusion"
```

---

### Task 3: Reference images and tool icon

**Files:**
- Create: `archplus/tools/walls/resources/icons/WallPlus.svg`
- Create: `archplus/tools/walls/resources/icons/dimensions_ref_plan.svg`
- Create: `archplus/tools/walls/resources/icons/align_offset_ref.svg`

**Interfaces:**
- Produces: three SVG files loaded by name through `widgets.ref_image` / `widgets.set_ref_image` (`archplus/common/widgets.py:51-65`) and the command `Pixmap`. The diagrams are the approved v8 mockups: baseline drawn OVER the wall band, W dimension on the left with filled arrowheads, baseline label centered under the line's right end, and the align trio with plain gaps (no ticks/arrows).

- [ ] **Step 1: Write the wall icon**

`WallPlus.svg` (a filled wall band with a dashed baseline):

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 32 32">
  <rect x="9" y="8" width="14" height="16" fill="#dbe7f2" stroke="#4a7bab" stroke-width="1.5"/>
  <line x1="5" y1="16" x2="27" y2="16" stroke="#a00" stroke-width="1.5" stroke-dasharray="4 3"/>
</svg>
```

- [ ] **Step 2: Write the plan reference image**

`dimensions_ref_plan.svg` (approved mockup v8 top view):

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="310" height="118" viewBox="0 0 310 118">
  <text x="8" y="14" font-size="10" fill="#8a8783">PLAN (top view)</text>
  <rect x="90" y="40" width="130" height="36" fill="#dbe7f2" stroke="#4a7bab" stroke-width="1.2"/>
  <line x1="100" y1="58" x2="250" y2="58" stroke="#a00" stroke-width="1.2" stroke-dasharray="5 4"/>
  <text x="250" y="74" font-size="9" fill="#a00" text-anchor="middle">baseline</text>
  <line x1="80" y1="40" x2="80" y2="76" stroke="#333" stroke-width="1"/>
  <line x1="80" y1="40" x2="90" y2="40" stroke="#333" stroke-width="1"/>
  <line x1="80" y1="76" x2="90" y2="76" stroke="#333" stroke-width="1"/>
  <polygon points="85,44 75,44 80,36" fill="#333"/>
  <polygon points="85,72 75,72 80,80" fill="#333"/>
  <text x="66" y="61" font-size="10" fill="#333" text-anchor="end">W</text>
  <text x="150" y="100" font-size="9" fill="#555">Align: Center — the wall straddles the baseline</text>
</svg>
```

- [ ] **Step 3: Write the align/offset reference image**

`align_offset_ref.svg` (approved mockup v8 trio):

```svg
<svg xmlns="http://www.w3.org/2000/svg" width="310" height="80" viewBox="0 0 310 80">
  <g>
    <rect x="14" y="40" width="40" height="14" fill="#dbe7f2" stroke="#4a7bab"/>
    <line x1="8" y1="24" x2="64" y2="24" stroke="#a00" stroke-width="1.1" stroke-dasharray="4 3"/>
    <text x="37" y="36" font-size="9" fill="#333" text-anchor="middle">Offset</text>
    <text x="34" y="68" font-size="9" fill="#555">Left</text>
  </g>
  <g>
    <rect x="104" y="23" width="40" height="14" fill="#dbe7f2" stroke="#4a7bab"/>
    <line x1="98" y1="30" x2="154" y2="30" stroke="#a00" stroke-width="1.1" stroke-dasharray="4 3"/>
    <text x="124" y="68" font-size="9" fill="#555">Center</text>
  </g>
  <g>
    <rect x="194" y="12" width="40" height="14" fill="#dbe7f2" stroke="#4a7bab"/>
    <line x1="188" y1="42" x2="244" y2="42" stroke="#a00" stroke-width="1.1" stroke-dasharray="4 3"/>
    <text x="217" y="37" font-size="9" fill="#333" text-anchor="middle">Offset</text>
    <text x="214" y="68" font-size="9" fill="#555">Right</text>
  </g>
  <text x="150" y="79" font-size="9" fill="#8a8783">Offset: distance from the baseline to the wall (Left / Right only)</text>
</svg>
```

- [ ] **Step 4: Verify the SVGs parse**

Run (from the repo root): `python -c "import xml.dom.minidom,glob; [xml.dom.minidom.parse(p) for p in glob.glob('archplus/tools/walls/resources/icons/*.svg')]; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add archplus/tools/walls/resources/icons/
git commit -m "Add wall reference diagrams and icon"
```

---

### Task 4: GUI — ViewProvider, create command, wall task panel

**Files:**
- Create: `archplus/tools/walls/gui.py`
- Create: `archplus/tools/walls/tests/test_panel.py`
- Modify: `InitGui.py`
- Modify: `archplus/freecad_tests/verify_walls.py`

**Interfaces:**
- Consumes: everything from Task 2, `widgets.length_input`, `widgets.mm`, `widgets.set_mm`, `widgets.ref_image` (`archplus/common/widgets.py`), the stairs panel lifecycle pattern (`archplus/tools/stairs/gui.py`: debounce QTimer 200ms, `_startPreview` creating the object in create mode, `FreeCADGui.Control.showDialog(panel)`, `accept()`/`reject()` committing/rolling back).
- Produces (in `archplus.tools.walls.gui`):
  - `ICON` — path string to `WallPlus.svg`
  - `class WallPlusTaskPanel` — root panel; `_collect()` returns `{"width": float, "height": float, "align": str, "offset": float, "tag": str, "base": obj|None, "rest": obj|None}`
  - `class WallPlusCommand` — `ArchPlus_Walls`
  - `showWallPanel(obj)` — opens the root panel for an existing wall
  - `_ensureVP(obj)` — attaches `_ViewProviderWall`

- [ ] **Step 1: Write the failing panel tests**

Write `archplus/tools/walls/tests/test_panel.py` (mirrors `test_stairs.py`'s fake-widget pattern):

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall task panels, driven through fakes exactly like
# test_stairs.py: the panel reads/writes object properties, so _collect /
# _loadFromObject carry the decisions worth testing here.

import types

from archplus.tools.walls import gui as wg
from conftest import FakeCombo, FakeNum, FakeCheck, quantity


class _FakeLine:
    """A QLineEdit stand-in: holds one string."""

    def __init__(self, v=""):
        self._v = v

    def text(self):
        return self._v

    def setText(self, v):
        self._v = v


def _panel(cls, obj):
    p = object.__new__(cls)
    p.obj, p._building = obj, True
    p.width = FakeNum(); p.height = FakeNum()
    p.align = FakeCombo(["Center", "Left", "Right"])
    p.offset = FakeNum(); p.tag = _FakeLine()
    return p


def _root_obj(**over):
    values = dict(Width=300.0, Height=2800.0, Align="Center", Offset=0.0)
    values.update(over)
    ns = types.SimpleNamespace()
    for k, v in values.items():
        if k == "Align":
            ns.Align = v
        else:
            setattr(ns, k, quantity(v))
    return ns


def test_root_collect_reads_all_fields():
    p = _panel(wg.WallPlusTaskPanel, _root_obj())
    p.align.setCurrentText("Right")
    p.offset.setValue(50.0)
    p.width.setValue(400.0)
    got = p._collect()
    assert got["width"] == 400.0
    assert got["align"] == "Right"
    assert got["offset"] == 50.0


def test_root_load_pushes_object_values_onto_widgets():
    p = _panel(wg.WallPlusTaskPanel, _root_obj(Width=400.0, Align="Left"))
    p._loadFromObject()
    assert p.width.value() == 400.0
    assert p.align.currentText() == "Left"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `pytest archplus/tools/walls/tests/test_panel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'archplus.tools.walls.gui'`

- [ ] **Step 3: Write `archplus/tools/walls/gui.py`**

```python
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WallsPlus GUI: commands, ViewProvider and the two task panels (wall root
# and segment). Follows the stairs/windows panel pattern: docked form,
# debounced live preview, reference diagrams, description lines.

import os

import FreeCAD
import FreeCADGui

from PySide import QtCore, QtGui

from archplus.common import widgets
from archplus.tools.walls import object as walls_object
from archplus.tools.walls import model

_DIR = os.path.dirname(__file__)
ICON = os.path.join(_DIR, "resources", "icons", "WallPlus.svg")
_ICON_DIR = os.path.join(_DIR, "resources", "icons")

WIDTH_DESC = "Thickness of the wall, perpendicular to its baseline."
HEIGHT_DESC = "Vertical height, measured from the sketch plane."
ALIGN_DESC = "Which side of the baseline the wall extends from."
OFFSET_DESC = "Extra distance between the baseline and the wall (Left/Right only)."


def _desc(text):
    lbl = QtGui.QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #8a8783; font-size: 10px;")
    return lbl


def _sketches_in_doc(doc):
    out = []
    for o in doc.Objects:
        if o.isDerivedFrom("Sketcher::SketchObject"):
            out.append(o)
    return out


class _ViewProviderWall:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ICON

    def setEdit(self, vobj, mode=0):
        obj = vobj.Object
        if getattr(getattr(obj, "Proxy", None), "Type", None) == walls_object.TYPE_WALL:
            showWallPanel(obj)
        else:
            showSegmentPanel(obj)
        return True

    def unsetEdit(self, vobj, mode=0):
        FreeCADGui.Control.closeDialog()
        return False


def _ensureVP(obj):
    vp = obj.ViewObject
    if getattr(getattr(vp, "Proxy", None), "__class__", None) is not _ViewProviderWall:
        _ViewProviderWall(vp)


class WallPlusTaskPanel:
    """Edit/create panel for the wall root."""

    def __init__(self, obj=None):
        self.obj = obj
        self.editing = obj is not None
        self._building = True

        title = "Edit Wall" if self.editing else "Wall"
        self.form = QtGui.QWidget()
        self.form.setWindowTitle(title)
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))
        outer = QtGui.QVBoxLayout(self.form)

        dimBox = QtGui.QGroupBox("Dimensions")
        dimV = QtGui.QVBoxLayout(dimBox)
        dimV.addWidget(widgets.ref_image(_ICON_DIR, "dimensions_ref_plan",
                                         QtCore.QSize(290, 110)))
        dimV.addWidget(widgets.ref_image(_ICON_DIR, "align_offset_ref",
                                         QtCore.QSize(290, 80)))
        dimForm = QtGui.QFormLayout()
        self.width = widgets.length_input(300)
        self.height = widgets.length_input(2800)
        self.align = QtGui.QComboBox()
        self.align.addItems(["Center", "Left", "Right"])
        self.offset = widgets.length_input(0)
        dimForm.addRow("W · Width", self.width)
        dimV.addWidget(_desc(WIDTH_DESC))
        dimForm.addRow("H · Height", self.height)
        dimV.addWidget(_desc(HEIGHT_DESC))
        dimForm.addRow("Align", self.align)
        dimV.addWidget(_desc(ALIGN_DESC))
        dimForm.addRow("Offset", self.offset)
        dimV.addWidget(_desc(OFFSET_DESC))
        dimV.addLayout(dimForm)
        dimV.addWidget(_desc("These are the defaults — children follow them "
                             "unless they override."))
        outer.addWidget(dimBox)

        skBox = QtGui.QGroupBox("Sketch & claims")
        skForm = QtGui.QFormLayout(skBox)
        self.sketch = QtGui.QComboBox()
        self.rest = QtGui.QComboBox()
        skForm.addRow("Sketch", self.sketch)
        skV = QtGui.QVBoxLayout()
        skV.addLayout(skForm)
        skV.addWidget(_desc("The base sketch. Shared freely — other walls can "
                            "use it too."))
        restForm = QtGui.QFormLayout()
        restForm.addRow("Rest segment", self.rest)
        skV.addLayout(restForm)
        skV.addWidget(_desc("This segment auto-claims any new sketch edge. "
                            "\"None\" = new edges build nothing."))
        self.stats = QtGui.QLabel()
        self.stats.setStyleSheet("color: #2e7d32;")
        skV.addWidget(self.stats)
        outer.addWidget(skBox)

        metaBox = QtGui.QGroupBox("Metadata")
        metaForm = QtGui.QFormLayout(metaBox)
        self.tag = QtGui.QLineEdit()
        self.tag.setPlaceholderText("e.g. W01")
        metaForm.addRow("Tag / Mark", self.tag)
        outer.addWidget(metaBox)

        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        for w in (self.width, self.height, self.offset):
            w.valueChanged.connect(self._schedule)
        self.align.currentIndexChanged.connect(self._schedule)
        self.tag.textChanged.connect(self._schedule)
        self.sketch.currentIndexChanged.connect(self._schedule)
        self.rest.currentIndexChanged.connect(self._schedule)

        self._building = False
        if self.obj is not None:
            self._loadFromObject()
        else:
            self._startPreview()
        self._updateCombos()
        self._updateStats()

    def _schedule(self, *args):
        if not self._building and self.obj is not None:
            self._timer.start()

    def _apply(self):
        try:
            vals = self._collect()
            o = self.obj
            o.Width = "%s mm" % vals["width"]
            o.Height = "%s mm" % vals["height"]
            o.Align = vals["align"]
            o.Offset = "%s mm" % vals["offset"]
            o.Tag = vals["tag"]
            if vals["base"] is not None:
                o.Base = vals["base"]
            o.recompute()
            self._updateStats()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus: %s\n" % exc)

    def _collect(self):
        return dict(
            width=widgets.mm(self.width),
            height=widgets.mm(self.height),
            align=self.align.currentText(),
            offset=widgets.mm(self.offset),
            tag=self.tag.text(),
            base=self.sketch.currentData(),
            rest=self.rest.currentData(),
        )

    def _loadFromObject(self):
        o = self.obj
        widgets.set_mm(self.width, o.Width.Value)
        widgets.set_mm(self.height, o.Height.Value)
        self.align.setCurrentText(o.Align)
        widgets.set_mm(self.offset, o.Offset.Value)
        self.tag.setText(getattr(o, "Tag", ""))

    def _updateCombos(self):
        doc = FreeCAD.ActiveDocument
        self._building = True
        self.sketch.clear()
        for sk in _sketches_in_doc(doc):
            self.sketch.addItem(sk.Label, sk)
        base = self.obj.Base if self.obj is not None else None
        if base is not None:
            idx = self.sketch.findData(base)
            if idx >= 0:
                self.sketch.setCurrentIndex(idx)
        self.rest.clear()
        self.rest.addItem("None", None)
        if self.obj is not None:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    self.rest.addItem(o.Label, o)
            rest = [o for o in self.obj.Group
                    if walls_object.is_segment(o) and getattr(o, "Rest", False)]
            if rest:
                idx = self.rest.findData(rest[0])
                if idx >= 0:
                    self.rest.setCurrentIndex(idx)
        self._building = False

    def _updateStats(self):
        try:
            o = self.obj
            if o is None or o.Base is None:
                self.stats.setText("")
                return
            nodes = [walls_object._claimNode(n) for n in o.Group
                     if walls_object.is_segment(n)]
            built, _warnings = model.resolve_claims(
                nodes, walls_object._sketchEdgeNames(o.Base))
            claimed = set().union(*built.values()) if built else set()
            total = len(walls_object._sketchEdgeNames(o.Base))
            self.stats.setText("%d edges claimed · %d unclaimed"
                               % (len(claimed), total - len(claimed)))
        except Exception:
            self.stats.setText("")

    def _startPreview(self):
        from archplus.tools.walls import object as walls_object  # noqa: F401
        doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument()
        doc.openTransaction("Create Wall")
        sel = FreeCADGui.Selection.getSelection()
        sketch = sel[0] if sel and sel[0].isDerivedFrom("Sketcher::SketchObject") else None
        self.obj = walls_object.makeWall(doc, sketch=sketch)
        _ensureVP(self.obj)
        _ensureVP(self.obj.Group[0])
        self._apply()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    def accept(self):
        self._apply()
        vals = self._collect()
        if vals["rest"] is not None:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    o.Rest = (o is vals["rest"])
        else:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    o.Rest = False
        if FreeCAD.ActiveDocument is not None:
            if self.editing:
                FreeCAD.ActiveDocument.recompute()
            else:
                FreeCAD.ActiveDocument.commitTransaction()
                FreeCAD.ActiveDocument.recompute()

    def reject(self):
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.abortTransaction()


class WallPlusCommand:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Wall",
                "ToolTip": "Build walls from a shared sketch"}

    def IsActive(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return False
        sel = FreeCADGui.Selection.getSelection()
        return bool(sel) and sel[0].isDerivedFrom("Sketcher::SketchObject")

    def Activated(self):
        FreeCADGui.Control.showDialog(WallPlusTaskPanel())


def showWallPanel(obj):
    FreeCADGui.Control.showDialog(WallPlusTaskPanel(obj))


def showSegmentPanel(obj):
    FreeCADGui.Control.showDialog(WallSegmentTaskPanel(obj))


class WallSegmentTaskPanel:
    """Edit panel for one segment: overrides with the inherit-checkbox
    pattern plus a read-only claims summary. Implemented in Task 5; this
    stub lets Task 4's imports and _ensureVP wiring stay complete."""

    def __init__(self, obj=None):
        self.obj = obj
        self.form = QtGui.QWidget()

    def accept(self):
        return True

    def reject(self):
        return True


FreeCADGui.addCommand("ArchPlus_Walls", WallPlusCommand())
```

- [ ] **Step 4: Register the toolbar entries**

In `InitGui.py` line 22, extend the commands list:

```python
    commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows",
                "ArchPlus_PartsLibrary", "ArchPlus_Walls"]
```

In `InitGui.py` `add_ui` (line 39-42), add `import archplus.tools.walls.gui  # noqa: F401`.

- [ ] **Step 5: Run the headless tests**

Run: `pytest archplus/tools/walls/tests/test_panel.py -v && pytest -v`
Expected: PASS — the two panel tests plus the full headless suite. The stub `WallSegmentTaskPanel` must not break `conftest` fakes.

- [ ] **Step 6: Extend the FreeCAD verification**

Append to `verify_walls.py` and call from `run()`:

```python
def _w4_panel(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    from archplus.tools.walls import gui as walls_gui
    panel = walls_gui.WallPlusTaskPanel(wall)
    panel._loadFromObject()
    from archplus.common import widgets
    widgets.set_mm(panel.width, 450.0)
    panel.align.setCurrentText("Left")
    panel._apply()
    doc.recompute()
    h.check("W4 panel edits reach the wall and its child",
            abs(wall.Width.Value - 450.0) < 1e-9
            and wall.Align == "Left"
            and abs(wall.Group[0].Shape.Volume
                    - _expected_volume(450, 2800, [4000])) < 1e-3)
    panel.reject()
```

- [ ] **Step 7: Run the FreeCAD verification**

Run: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: PASS — W1–W4 included.

- [ ] **Step 8: Commit**

```bash
git add archplus/tools/walls/gui.py archplus/tools/walls/tests/test_panel.py \
        archplus/tools/walls/tests/__init__.py InitGui.py \
        archplus/freecad_tests/verify_walls.py
git commit -m "Add wall create command and wall task panel"
```

---

### Task 5: Segment panel and the split command

**Files:**
- Modify: `archplus/tools/walls/gui.py` (replace the `WallSegmentTaskPanel` stub; add `WallSplitCommand` and its registration)
- Modify: `conftest.py` (give `FakeNum` a no-op `setEnabled`)
- Modify: `archplus/tools/walls/tests/test_panel.py`
- Modify: `archplus/freecad_tests/verify_walls.py`
- Modify: `InitGui.py` (add `ArchPlus_WallSplit` to the command list)

**Interfaces:**
- Consumes: `model.match_edge`, `walls_object.splitSegment`, `walls_object.effectiveValues`, `walls_object._claimNode`, `walls_object._sketchEdgeNames`, `walls_object.wall_root`, `showSegmentPanel`.
- Produces:
  - `class WallSegmentTaskPanel` — segment panel; `_collect()` returns `{"width": float, "height": float, "align": str}` where unchecked fields are `0`/`"Inherit"`; `_loadFromObject()` drives the checkbox pattern (checked = override + editable, unchecked = greyed inherited value).
  - `class WallSplitCommand` — `ArchPlus_WallSplit`, active when a `WallSegment` is selected.

- [ ] **Step 1: Give `FakeNum` a `setEnabled` no-op**

In `conftest.py`, in `class FakeNum` right after `setMinimum` (line ~299):

```python
    def setEnabled(self, _):
        pass
```

Run `pytest -v` to confirm the shared fakes still pass for stairs/windows/doors tests before continuing.

- [ ] **Step 2: Write the failing panel tests**

Append to `archplus/tools/walls/tests/test_panel.py`:

```python
def _seg_obj(**over):
    values = dict(Width=200.0, Height=0.0, Align="Inherit")
    values.update(over)
    ns = types.SimpleNamespace()
    for k, v in values.items():
        if k == "Align":
            ns.Align = v
        else:
            setattr(ns, k, quantity(v))
    return ns


def _seg_panel(obj):
    p = object.__new__(wg.WallSegmentTaskPanel)
    p.obj, p._building = obj, True
    p.overrideW = FakeCheck(); p.overrideH = FakeCheck()
    p.width = FakeNum(); p.height = FakeNum()
    p.align = FakeCombo(["Inherit", "Center", "Left", "Right"])
    p.stats = FakeCheck()
    return p


def test_segment_collect_overrides_only_checked_fields():
    p = _seg_panel(_seg_obj())
    p.overrideW.setChecked(True); p.width.setValue(250.0)
    p.overrideH.setChecked(False)
    p.align.setCurrentText("Inherit")
    got = p._collect()
    assert got == {"width": 250.0, "height": 0.0, "align": "Inherit"}


def test_segment_load_checks_override_for_nonzero_width():
    p = _seg_panel(_seg_obj(Width=200.0, Height=0.0, Align="Inherit"))
    p._loadFromObject()
    assert p.overrideW.isChecked() is True
    assert p.overrideH.isChecked() is False
    assert p.width.value() == 200.0
    assert p.align.currentText() == "Inherit"
```

- [ ] **Step 3: Run them to verify they fail**

Run: `pytest archplus/tools/walls/tests/test_panel.py -v`
Expected: FAIL — the two new tests fail against the stub panel.

- [ ] **Step 4: Implement the segment panel**

Replace the `WallSegmentTaskPanel` stub in `archplus/tools/walls/gui.py`:

```python
class WallSegmentTaskPanel:
    """Edit panel for one segment: W/H/Align overrides with the
    inherit-checkbox pattern, plus a read-only claims summary."""

    def __init__(self, obj=None):
        self.obj = obj
        self.editing = obj is not None
        self._building = True

        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Edit Segment")
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))
        outer = QtGui.QVBoxLayout(self.form)

        ovBox = QtGui.QGroupBox("Override")
        ovV = QtGui.QVBoxLayout(ovBox)
        ovV.addWidget(widgets.ref_image(_ICON_DIR, "dimensions_ref_plan",
                                        QtCore.QSize(290, 110)))
        ovForm = QtGui.QFormLayout()
        self.overrideW = QtGui.QCheckBox("W · Width")
        self.overrideH = QtGui.QCheckBox("H · Height")
        self.width = widgets.length_input(0)
        self.height = widgets.length_input(0)
        self.align = QtGui.QComboBox()
        self.align.addItems(["Inherit", "Center", "Left", "Right"])
        ovForm.addRow(self.overrideW, self.width)
        ovV.addWidget(_desc("Checked = this segment overrides the wall default."))
        ovForm.addRow(self.overrideH, self.height)
        ovV.addWidget(_desc("Inherited from the wall/group. Check to override, "
                            "pre-filled with the inherited value."))
        ovForm.addRow("Align", self.align)
        ovV.addLayout(ovForm)
        outer.addWidget(ovBox)

        clBox = QtGui.QGroupBox("Claims")
        clV = QtGui.QVBoxLayout(clBox)
        self.stats = QtGui.QLabel()
        self.stats.setStyleSheet("color: #2e7d32;")
        clV.addWidget(self.stats)
        clV.addWidget(_desc("Split / reassign edges with \"Split from "
                            "selection…\" in the 3D view. Rest and Sketch are "
                            "set in the wall panel."))
        outer.addWidget(clBox)

        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        for w in (self.width, self.height):
            w.valueChanged.connect(self._schedule)
        self.align.currentIndexChanged.connect(self._schedule)
        self.overrideW.toggled.connect(self._onOverrideW)
        self.overrideH.toggled.connect(self._onOverrideH)

        self._building = False
        self._loadFromObject()
        self._updateStats()

    def _schedule(self, *args):
        if not self._building and self.obj is not None:
            self._timer.start()

    def _inherited(self):
        try:
            return walls_object.effectiveValues(self.obj)
        except Exception:
            return dict(model.DEFAULT_CONFIG)

    def _onOverrideW(self, checked):
        if self._building or self.obj is None:
            return
        if checked:
            widgets.set_mm(self.width, self._inherited()["Width"])
        else:
            self.obj.Width = 0
            self._loadFromObject()

    def _onOverrideH(self, checked):
        if self._building or self.obj is None:
            return
        if checked:
            widgets.set_mm(self.height, self._inherited()["Height"])
        else:
            self.obj.Height = 0
            self._loadFromObject()

    def _apply(self):
        try:
            vals = self._collect()
            o = self.obj
            o.Width = "%s mm" % vals["width"]
            o.Height = "%s mm" % vals["height"]
            o.Align = vals["align"]
            o.recompute()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus: %s\n" % exc)

    def _collect(self):
        return dict(
            width=widgets.mm(self.width) if self.overrideW.isChecked() else 0.0,
            height=widgets.mm(self.height) if self.overrideH.isChecked() else 0.0,
            align=self.align.currentText(),
        )

    def _loadFromObject(self):
        self._building = True
        o = self.obj
        w = getattr(o, "Width", None)
        wv = w.Value if w is not None else 0.0
        self.overrideW.setChecked(wv != 0.0)
        inherited = self._inherited()
        widgets.set_mm(self.width, wv if wv else inherited["Width"])
        h = getattr(o, "Height", None)
        hv = h.Value if h is not None else 0.0
        self.overrideH.setChecked(hv != 0.0)
        widgets.set_mm(self.height, hv if hv else inherited["Height"])
        self.align.setCurrentText(getattr(o, "Align", "Inherit"))
        self.width.setEnabled(self.overrideW.isChecked())
        self.height.setEnabled(self.overrideH.isChecked())
        self._building = False

    def _updateStats(self):
        try:
            o = self.obj
            root = walls_object.wall_root(o) or o
            if root.Base is None:
                self.stats.setText("")
                return
            nodes = [walls_object._claimNode(n) for n in root.Group
                     if walls_object.is_segment(n)]
            built, _warnings = model.resolve_claims(
                nodes, walls_object._sketchEdgeNames(root.Base))
            mine = built.get(o, frozenset())
            auto = len(mine)
            self.stats.setText("%d edges claimed · %d auto" % (auto, auto))
        except Exception:
            self.stats.setText("")

    def accept(self):
        self._apply()
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.recompute()

    def reject(self):
        pass
```

- [ ] **Step 5: Implement the split command**

Append to `archplus/tools/walls/gui.py`:

```python
def _claimedEdgePolylines(segment):
    """[(subname, [global points])] for each claimed edge, for matching."""
    sketch = segment.Base
    out = []
    if sketch is None or not hasattr(sketch, "Shape"):
        return out
    for sub in sorted(walls_object._claimedEdges(segment)):
        try:
            edge = sketch.Shape.getElement(sub)
            edge.transformShape(sketch.Placement.toMatrix())
            pts = [edge.Vertexes[0].Point]
            for p in edge.discretize(16)[1:]:
                pts.append(p)
            out.append((sub, pts))
        except Exception:
            continue
    return out


class WallSplitCommand:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Split segment",
                "ToolTip": "Move selected wall faces into a new segment group"}

    def IsActive(self):
        for sel in FreeCADGui.Selection.getSelectionEx():
            if walls_object.is_segment(sel.Object):
                return True
        return False

    def Activated(self):
        from archplus.tools.walls import object as walls_object
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("Split wall segment")
        for sel in FreeCADGui.Selection.getSelectionEx():
            obj = sel.Object
            if not walls_object.is_segment(obj):
                continue
            if sel.HasSubObjects:
                picked = []
                for name in sel.SubElementNames:
                    if not name.startswith("Face"):
                        continue
                    try:
                        face = obj.Shape.getElement(name)
                    except Exception:
                        continue
                    idx = model.match_edge(
                        [pts for _sub, pts in _claimedEdgePolylines(obj)],
                        tuple(face.CenterOfGravity), tol=5.0)
                    if idx is not None:
                        picked.append(_claimedEdgePolylines(obj)[idx][0])
                if picked:
                    walls_object.splitSegment(obj, sorted(set(picked)))
            else:
                subs = [sub for sub in walls_object._claimedEdges(obj)]
                if subs:
                    walls_object.splitSegment(obj, subs)
        doc.recompute()
        doc.commitTransaction()


FreeCADGui.addCommand("ArchPlus_WallSplit", WallSplitCommand())
```

- [ ] **Step 6: Register the toolbar entry**

In `InitGui.py`, extend the commands list to include `"ArchPlus_WallSplit"` after `"ArchPlus_Walls"`.

- [ ] **Step 7: Run the headless tests**

Run: `pytest archplus/tools/walls/tests/test_panel.py -v && pytest -v`
Expected: PASS.

- [ ] **Step 8: Extend the FreeCAD verification**

Append to `verify_walls.py` and call from `run()`:

```python
def _w5_split(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    rest = wall.Group[0]
    walls_object.splitSegment(rest, ["Edge1"], name="exterior")
    doc.recompute()
    new = [o for o in wall.Group if o is not rest][0]
    h.check("W5 split moved the claim",
            abs(new.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    h.check("W5 source keeps the remainder",
            abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    nested = walls_object.makeSegment(new, name="short")
    nested.Edges = [(sk, ("Edge2",))]
    nested.Height = "2200 mm"
    doc.recompute()
    h.check("W5 nesting after split inherits the group",
            abs(nested.Shape.Volume - _expected_volume(300, 2200, [4000])) < 1e-3
            and new.Shape.Volume < 1e-3
            and abs(rest.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3)
    wall.addObject(new)
    doc.recompute()
    h.check("W5 re-parenting preserves geometry",
            abs(nested.Shape.Volume - _expected_volume(300, 2200, [4000])) < 1e-3)
    return wall, sk
```

- [ ] **Step 9: Run the FreeCAD verification**

Run: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: PASS — W1–W5 included. If W5 re-parenting shows stale geometry after `addObject` without recompute, keep the explicit `doc.recompute()` in the check and note it in `docs/TOOLS.md` (tree moves need a recompute; F5).

- [ ] **Step 10: Commit**

```bash
git add archplus/tools/walls/gui.py archplus/tools/walls/tests/test_panel.py \
        InitGui.py archplus/freecad_tests/verify_walls.py
git commit -m "Add segment panel and split command for walls"
```

---

### Task 6: Hosting — doors/windows cut their openings into segments

**Files:**
- Modify: `archplus/tools/windows/object.py`
- Modify: `archplus/tools/doors/object.py`
- Modify: `archplus/tools/windows/gui.py`
- Modify: `archplus/tools/doors/gui.py`
- Modify: `archplus/freecad_tests/verify_walls.py`

**Interfaces:**
- Consumes: `walls_object.TYPE_WALL`/`TYPE_SEGMENT`, `wall_root` semantics (the `Wall` link), the window/door `Hosts` + `getSubVolume` machinery.
- Produces: hosted doors/windows cut the exact segments their opening intersects; `Hosts` points at the wall root.

- [ ] **Step 1: Guard the width-probing path for hosts without Arch props**

In `archplus/tools/windows/object.py`, `getSubVolume` (line 785):

```python
        propSetUuid = host.Proxy.ArchSkPropSetPickedUuid
```
becomes
```python
        propSetUuid = getattr(host.Proxy, "ArchSkPropSetPickedUuid", "")
```
and (line 798):
```python
                    if host.OverrideWidth:
```
becomes
```python
                    if getattr(host, "OverrideWidth", None):
```

Apply the same two guards in `archplus/tools/doors/object.py` — locate them with:
`grep -n "ArchSkPropSetPickedUuid\|OverrideWidth" archplus/tools/doors/object.py`

- [ ] **Step 2: Walk segment picks up to the wall root**

In `archplus/tools/windows/gui.py` (lines 1155 and 1320) and
`archplus/tools/doors/gui.py` (lines 958 and 1121), immediately before each
`if Draft.getType(host) in ("Wall", "Structure", "Roof"):` block, add:

```python
                if Draft.getType(host) == "WallSegment":
                    host = getattr(host, "Wall", host)
```

- [ ] **Step 3: Anchor the sill to the sketch plane for shape-less hosts**

In `archplus/tools/windows/gui.py` `_hostBaseZ` (line 830):

```python
        for h in (getattr(self.obj, "Hosts", None) or []):
            try:
                zs.append(h.Shape.BoundBox.ZMin)
            except Exception:
                pass
```
becomes
```python
        for h in (getattr(self.obj, "Hosts", None) or []):
            try:
                if getattr(h, "Shape", None) is not None and not h.Shape.isNull():
                    zs.append(h.Shape.BoundBox.ZMin)
                elif getattr(h, "Base", None) is not None:
                    zs.append(h.Base.Placement.Base.z)
            except Exception:
                pass
```

If `archplus/tools/doors/gui.py` has an equivalent method (search
`grep -n "_hostBaseZ\|BoundBox.ZMin" archplus/tools/doors/gui.py`), apply the
same change there.

- [ ] **Step 4: Extend the FreeCAD verification with hosting checks**

Append to `verify_walls.py` and call from `run()`:

```python
def _w6_hosting(doc):
    sk = _line_sketch(doc, [((0, 0), (4000, 0), False)])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    seg = wall.Group[0]
    full = seg.Shape.Volume

    from archplus.tools.windows import gui as wg
    from archplus.tools.windows import object as wo
    spec = dict(shape="Rectangular", operation="Fixed", width=1000,
                height=1000, frameWidth=50, sashThk=45, frameDepth=100,
                swingSide="Left", swingDir="Inward", panelPos="Front")
    wsk, wp = wg._makeWindowGeometry(spec)
    win = wo.makeWindow(wsk, 1000, 1000, wp, name="Win")
    wsk.Placement = FreeCAD.Placement(
        FreeCAD.Vector(1500, 0, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win.Hosts = [wall]
    wall.Subtractions = [win]
    doc.recompute()

    h.check("W6 hosted window cuts its segment",
            seg.Shape.Volume < full - 1000 * 300 * 1000 * 0.5)
    wall.Subtractions = []
    doc.recompute()
    h.check("W6 unhosting restores the segment",
            abs(seg.Shape.Volume - full) < 1e-3)

    # spanning opening: two collinear runs, two siblings, one window
    sk2 = _line_sketch(doc, [
        ((0, 5000), (2000, 5000), False),
        ((2000, 5000), (4000, 5000), False),
    ], name="SplitRun")
    wall2 = walls_object.makeWall(doc, sketch=sk2, name="Wall2")
    doc.recompute()
    a, b = wall2.Group[0], walls_object.makeSegment(wall2, name="b")
    a.Edges = [(sk2, ("Edge1",))]
    a.Rest = False
    b.Edges = [(sk2, ("Edge2",))]
    doc.recompute()
    fa, fb = a.Shape.Volume, b.Shape.Volume
    wsk2, wp2 = wg._makeWindowGeometry(spec)
    win2 = wo.makeWindow(wsk2, 1000, 1000, wp2, name="Win2")
    wsk2.Placement = FreeCAD.Placement(
        FreeCAD.Vector(1500, 5000, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    win2.Hosts = [wall2]
    wall2.Subtractions = [win2]
    doc.recompute()
    h.check("W6 spanning window cuts both collinear segments",
            a.Shape.Volume < fa - 100 and b.Shape.Volume < fb - 100)
    return wall, sk
```

If the cut volume assertion is off (subvolume depth follows `wall.Width`
+100 mm and the window sketch orientation), inspect measured volumes from the
failure detail and adjust the bound only if geometry proves the cut lands in
both segments — never weaken it below "strictly less than full minus 100 mm³
per segment".

- [ ] **Step 5: Extend the verification with the save/reload check**

Append to `verify_walls.py` and call from `run()` as the last group:

```python
def _w7_reload(doc):
    sk = _line_sketch(doc, [
        ((0, 0), (4000, 0), False),
        ((0, 3000), (4000, 3000), False),
    ])
    wall = walls_object.makeWall(doc, sketch=sk)
    doc.recompute()
    walls_object.splitSegment(wall.Group[0], ["Edge1"], name="exterior")
    doc.recompute()
    import os
    import tempfile
    path = os.path.join(tempfile.gettempdir(), "archplus_walls_reload.FCStd")
    if os.path.exists(path):
        os.remove(path)
    doc.saveAs(path)
    FreeCAD.closeDocument(doc.Name)
    doc2 = FreeCAD.openDocument(path)
    doc2.recompute()
    wall2 = doc2.getObject("Wall")
    ok = wall2 is not None and len(wall2.Group) == 2
    for seg in (wall2.Group if ok else []):
        ok = ok and abs(seg.Shape.Volume - _expected_volume(300, 2800, [4000])) < 1e-3
        ok = ok and seg.Proxy.Type == "WallSegment" and seg.Wall is wall2
    h.check("W7 reload preserves tree, claims and inheritance", ok)
    FreeCAD.closeDocument(doc2.Name)
```

- [ ] **Step 6: Run the FreeCAD verification**

Run: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: PASS — W1–W7, plus the pre-existing window/door suites (the
`getSubVolume` guards must not regress `verify_openings`).

- [ ] **Step 7: Commit**

```bash
git add archplus/tools/windows/object.py archplus/tools/doors/object.py \
        archplus/tools/windows/gui.py archplus/tools/doors/gui.py \
        archplus/freecad_tests/verify_walls.py
git commit -m "Host doors and windows on walls with per-segment opening cuts"
```

---

### Task 7: Docs and full-suite sign-off

**Files:**
- Modify: `docs/TOOLS.md`
- Modify: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: everything above; documents the shipped tool.

- [ ] **Step 1: Document the Walls tool**

In `docs/TOOLS.md`, add a Walls section following the existing per-tool
format:

- concepts: a wall references its base sketch (never owns it); a `Wall`
  root holds defaults + hosted openings; `WallSegment` children are segment
  groups claiming sketch edges; `Rest` = auto-claim of unclaimed edges
  (at most one, direct child of the wall); nesting = inherited overrides;
  `0`/`Inherit` = inherit.
- commands: `Wall` (select a sketch first), `Split segment` (select built
  faces in the 3D view).
- panels: Edit Wall (dimensions with reference diagrams, sketch & claims,
  metadata) and Edit Segment (override checkboxes, claims summary).
- known limitation: collinear runs in different groups butt with coplanar
  faces and can flicker in the 3D view (cosmetic); tree re-parenting needs a
  recompute.

In `docs/ROADMAP.md`, move walls from "planned" to "shipped" (adjust the
wording to whatever section currently lists it).

- [ ] **Step 2: Run the headless suite**

Run: `pytest -v`
Expected: PASS — every test in the repo, including all walls tests.

- [ ] **Step 3: Run the FreeCAD verification suite**

Run: `"C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py`
Expected: PASS — every check including W1–W6.

- [ ] **Step 4: Commit**

```bash
git add docs/TOOLS.md docs/ROADMAP.md
git commit -m "Document the Walls tool and mark it shipped"
```

---

## Verification summary (what "done" means)

- `pytest -v` green headlessly (model + panel logic, ~18 new tests).
- FreeCAD-session suite green: W1 creation/claims, W2 inheritance/nesting,
  W3 sketch edits, W4 panel edits, W5 split/re-parent, W6 hosted + spanning
  openings, W7 save/reload, plus all pre-existing suites (openings,
  placement, reload…).
- Doors/windows still host on Arch walls (no regression) *and* now host on
  ArchPlus walls.
- Spec coverage: objects/tree (§3), claims/rebuild (§4), config (§5),
  geometry (§6), hosting incl. the "opening not applied" and unclaimed-edge
  warnings (§7, §9 — warnings print via `PrintWarning`; the harness verifies
  their geometry outcomes, not the console text), workflow/panels (§8),
  files/tests (§10), docs (§12).
