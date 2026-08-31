# archplus/tools/walls/dims.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# On-select length dimensions for wall segments
# (docs/superpowers/specs/2026-08-30-wall-length-overlay-design.md):
# selecting a wall face draws a Coin overlay above that face's wall run —
# a dimension line along the run, oblique end ticks and a screen-facing
# length label; selecting the whole segment dims every run. No document
# objects are created; the overlay lives in the segment's view provider
# under a tracked node name, like the edit highlight. The geometry and
# selection mapping here work on plain tuples so pytest drives them
# headlessly; FreeCAD and pivy are imported lazily inside functions.

from archplus.tools.walls import model
from archplus.tools.walls import object as walls_object

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


def run_dims(segment, scope=None):
    """Per-run (points, length_mm) summaries for a segment, plain data.
    scope is None for every run, else the set of run indices to include.
    Degenerate runs (fewer than two points, zero length) are skipped."""
    out = []
    for index, (pts, _normal, _height) in enumerate(
            walls_object.segmentEdgeRuns(segment)):
        if scope is not None and index not in scope:
            continue
        length = polyline_length(pts)
        if len(pts) >= 2 and length > 1e-9:
            out.append((pts, length))
    return out


def _dimRuns(segment, scope=None):
    """Per-run overlay geometry for a segment: (line, ticks, label_pt,
    text) with plain tuples, ready for the Coin builder. Runs with no
    direction are skipped."""
    out = []
    for index, (pts, normal, height) in enumerate(
            walls_object.segmentEdgeRuns(segment)):
        if scope is not None and index not in scope:
            continue
        length = polyline_length(pts)
        if len(pts) < 2 or length <= 1e-9:
            continue
        try:
            line, ticks, label_pt = _dimGeometry(pts, normal, height)
        except Exception:
            continue
        out.append((line, ticks, label_pt, format_length(length)))
    return out


def _projectPt(p, seg):
    """The world point projected onto the segment sketch's plane, as a
    plain tuple (the split command's projection). Accepts a plain tuple
    or a Vector."""
    import FreeCAD
    from archplus.tools.walls import gui as walls_gui
    coords = (p.x, p.y, p.z) if hasattr(p, "x") else (p[0], p[1], p[2])
    projected = walls_gui._projectToSketchPlane(FreeCAD.Vector(*coords),
                                                seg.Base)
    return (projected.x, projected.y, projected.z)


def _faceRunScope(seg, face_name):
    """The run indices one picked face belongs to: the face's centroid
    projected onto the sketch plane and matched to the nearest run
    within one effective wall width — the split command's mapping. The
    face centroid is used instead of the click point because FreeCAD
    fabricates PickedPoints for API-driven face selections. Returns a
    (possibly empty) set of run indices."""
    try:
        point = seg.Shape.getElement(face_name).CenterOfGravity
    except Exception:
        return set()
    tol = walls_object.effectiveValues(seg)["Width"]
    projected = [[_projectPt(p, seg) for p in pts]
                 for pts, _normal, _height
                 in walls_object.segmentEdgeRuns(seg)]
    index = model.match_edge(projected, _projectPt(point, seg), tol)
    return set() if index is None else {index}


_nodes = {}      # (doc name, object name) -> (dimmed segment, run scope)
_observer = None


def _key(obj):
    return (getattr(getattr(obj, "Document", None), "Name", ""), obj.Name)


def _buildNode(chains):
    """The Coin overlay node for one segment: a dimension line and end
    ticks per run plus one screen-facing label per run. chains is what
    _dimRuns returns. Labels are wrapped in their own SoSeparator so each
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


def addDim(segment, scope=None):
    """Draw the length dim overlay for the segment's scoped runs on its
    view provider. True when a node was added."""
    try:
        vobj = getattr(segment, "ViewObject", None)
        if vobj is None or getattr(vobj, "RootNode", None) is None:
            return False
        chains = _dimRuns(segment, scope)
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


def _dimScopes():
    """The (segment, scope) pairs the current selection implies dims for,
    in first-appearance order. scope is None for every run of the
    segment, else the set of run indices the selected faces map to. A
    wall root with picked faces resolves each to its owning segment
    (pick-point occurrence counting, like the split command); a tree-
    selected root with no faces implies nothing. gui is imported lazily:
    gui.py imports this module at load time."""
    import FreeCADGui
    from archplus.tools.walls import gui as walls_gui
    scopes = {}
    order = []
    for sel in FreeCADGui.Selection.getSelectionEx():
        obj = getattr(sel, "Object", None)
        if walls_object.is_segment(obj):
            _mergeScope(scopes, order, obj,
                        _selectionScope(obj, sel))
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
                local = resolved[1][0] if resolved[1] else name
                _mergeScope(scopes, order, seg,
                            _faceRunScope(seg, local))
    return [(seg, scopes[_key(seg)]) for seg in order]


def _selectionScope(seg, sel):
    """The run scope one direct segment selection member implies: None
    (every run) when it names no faces, else the union of the runs its
    picked faces map to."""
    names = list(getattr(sel, "SubElementNames", None) or ())
    if not any(n.startswith("Face") for n in names):
        return None
    scope = set()
    for name in names:
        if name.startswith("Face"):
            scope |= _faceRunScope(seg, name)
    return scope


def _mergeScope(scopes, order, seg, scope):
    """Union a member's scope into the segment's entry; None (every run)
    absorbs any scope."""
    key = _key(seg)
    if key not in scopes:
        scopes[key] = scope
        order.append(seg)
    elif scopes[key] is None or scope is None:
        scopes[key] = None
    else:
        scopes[key] = scopes[key] | scope


def sync():
    """Recompute the dimmed set from the current selection and diff it
    against the drawn overlays; a scope change redraws. Never raises:
    selection events must not break the session."""
    try:
        want = {}
        for seg, scope in _dimScopes():
            want[_key(seg)] = (seg, scope)
        for key in list(_nodes):
            if key not in want:
                seg, _scope = _nodes.pop(key)
                removeDim(seg)
                continue
            seg, scope = want[key]
            if _nodes[key][1] != scope:
                removeDim(seg)
                _nodes.pop(key)
        for key, (seg, scope) in want.items():
            if key not in _nodes and addDim(seg, scope):
                _nodes[key] = (seg, scope)
    except Exception:
        pass


def refresh(segment):
    """Redraw the segment's dim overlay after its shape changed, keeping
    its run scope. No-op when the segment is not currently dimmed."""
    try:
        key = _key(segment)
        if key not in _nodes:
            return
        _seg, scope = _nodes[key]
        removeDim(segment)
        if addDim(segment, scope):
            _nodes[key] = (segment, scope)
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
