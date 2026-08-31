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
