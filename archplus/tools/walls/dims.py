# archplus/tools/walls/dims.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# On-select length dimensions for wall segments
# (docs/superpowers/specs/2026-08-30-wall-length-overlay-design.md):
# selecting a wall face draws a Coin overlay above that face's wall run —
# a dimension line along the run, oblique end ticks and a length label
# reading along the run — with the line cut short of the label so the
# two never share screen space; selecting the whole segment dims every
# run. No document
# objects are created; the overlay lives in the segment's view provider
# under a tracked node name, like the edit highlight. The geometry and
# selection mapping here work on plain tuples so pytest drives them
# headlessly; FreeCAD and pivy are imported lazily inside functions.

from archplus.tools.walls import model
from archplus.tools.walls import object as walls_object

# Node name convention: ArchPlusSegmentHighlight, ArchPlusTargetPreview.
DIM_NODE = "ArchPlusSegmentDim"

_DIM_COLOR = (1.0, 0.85, 0.2)   # warm yellow, distinct from the green highlight
_FONT_SIZE = 160.0              # SoText3 object-space size (mm)
_LINE_WIDTH = 2.0
_GAP_PAD = 0.2 * _FONT_SIZE     # mm of bare line on each side of the label gap
_MIN_STUB = 45.0                # mm of line kept past the gap on short runs
_MIN_SCALE = 0.5                # label never shrinks below half size
_TICK = 60.0                    # mm, oblique end tick
_MARGIN = 20.0                  # mm above the top edge — hugs the wall


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
    top edge plus a small fixed clearance, so the dimension hugs the
    wall."""
    return height + _MARGIN


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


def _arcCut(pts, gap_start, gap_end):
    """The polyline pieces outside the arc-length range
    [gap_start, gap_end]. Cut points are interpolated on their segment;
    pieces that would keep fewer than two points are dropped."""
    out, cur, inside = [], [pts[0]], gap_start <= 0.0
    s = 0.0
    for a, b in zip(pts, pts[1:]):
        seg = _dist(a, b)
        s2 = s + seg
        if seg > 0.0:
            for cut, opens in ((gap_start, True), (gap_end, False)):
                if s < cut < s2:
                    p = _add(a, _mul(_sub(b, a), (cut - s) / seg))
                    if opens:
                        cur.append(p)
                        if len(cur) >= 2:
                            out.append(cur)
                        cur = [p]
                        inside = True
                    else:
                        cur = [p]
                        inside = False
        if not inside:
            cur.append(b)
        s = s2
    if not inside and len(cur) >= 2:
        out.append(cur)
    return out


def _gappedLine(line, half):
    """The dimension line split around the label: the polyline pieces
    outside half the label's rendered width on each side of the
    arc-length midpoint — empty when the gap swallows the whole run.
    Text and line share the dimension plane, so the gap keeps the line
    out of the label's screen footprint from every view."""
    mid = polyline_length(line) / 2.0
    return _arcCut(line, mid - half, mid + half)



def _midTangent(pts):
    """The unit direction of the polyline segment containing the
    arc-length midpoint."""
    half = polyline_length(pts) / 2.0
    acc = 0.0
    for a, b in zip(pts, pts[1:]):
        d = _dist(a, b)
        if d > 1e-12 and acc + d >= half:
            return _norm(_sub(b, a))
        acc += d
    return _norm(_sub(pts[-1], pts[0]))


def _dimGeometry(pts, normal, height, tick=_TICK):
    """Dimension geometry for one run: the axis polyline raised to the
    dimension plane, an oblique tick crossing each end (45 degrees to the
    line, centred on the end), the label anchor at the arc-length
    midpoint and the label frame (direction along the run, up-vector
    across it) so the label reads along the wall. pts and normal are
    plain (x, y, z) tuples; raises ValueError when the run has no
    direction."""
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
    label_dir = _midTangent(line)
    label_up = _norm(_cross(normal, label_dir)) if label_dir else None
    return line, ticks, _midpoint(line), label_dir, label_up


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
            line, ticks, label_pt, label_dir, label_up = _dimGeometry(
                pts, normal, height)
        except Exception:
            continue
        out.append((line, ticks, label_pt, label_dir, label_up,
                    format_length(length)))
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


def _faceRunScope(seg, face_name, runs=None):
    """The run indices one picked face belongs to: the face's centroid
    projected onto the sketch plane and matched to the nearest run
    within one effective wall width — the split command's mapping. The
    face centroid is used instead of the click point because FreeCAD
    fabricates PickedPoints for API-driven face selections. runs is an
    optional memo of segmentEdgeRuns results shared by every face of
    one sync pass. Returns a (possibly empty) set of run indices."""
    try:
        point = seg.Shape.getElement(face_name).CenterOfGravity
    except Exception:
        return set()
    tol = walls_object.effectiveValues(seg)["Width"]
    if runs is None:
        runs = {}
    key = _key(seg)
    if key not in runs:
        runs[key] = walls_object.segmentEdgeRuns(seg)
    projected = [[_projectPt(p, seg) for p in pts]
                 for pts, _normal, _height in runs[key]]
    index = model.match_edge(projected, _projectPt(point, seg), tol)
    return set() if index is None else {index}


_nodes = {}      # (doc name, object name) -> (dimmed segment, run scope)
_observer = None


def _key(obj):
    return (getattr(getattr(obj, "Document", None), "Name", ""), obj.Name)


def _labelHalf(text, scale=1.0):
    """Half the label's rendered width at the given font scale plus a
    pad — the room the line leaves on each side of the label anchor.
    Coin's bounding-box action on SoText3 is unreliable in this build
    (and has wedged the GUI), so the width is estimated from the
    character count against the sans face's ~0.6 em average glyph
    advance."""
    return scale * 0.34 * len(text) * _FONT_SIZE + _GAP_PAD


def _labelScale(length, text):
    """Font scale for a label on a run of `length`: 1.0 while the full-
    size gap leaves visible line stubs, else shrunk — clamped to
    _MIN_SCALE — so a short wall keeps its line instead of the gap
    swallowing it."""
    text_half = _labelHalf(text) - _GAP_PAD
    room = length / 2.0 - _MIN_STUB - _GAP_PAD
    if room >= text_half:
        return 1.0
    return max(_MIN_SCALE, room / text_half)


def _labelNode(coin, text, scale):
    """One label separator on an identity frame: per-label SoFont,
    identity SoMatrixTransform, centred SoText3. Returns the separator
    and its transform so _buildNode can place it after measuring."""
    label = coin.SoSeparator()
    font = coin.SoFont()
    font.name.setValue("Sans")
    font.size.setValue(_FONT_SIZE * scale)
    mt = coin.SoMatrixTransform()
    ident = coin.SbMatrix()
    ident.setValue(((1.0, 0.0, 0.0, 0.0),
                    (0.0, 1.0, 0.0, 0.0),
                    (0.0, 0.0, 1.0, 0.0),
                    (0.0, 0.0, 0.0, 1.0)))
    mt.matrix.setValue(ident)
    t3 = coin.SoText3()
    t3.string.setValue(text)
    t3.justification.setValue(coin.SoText3.CENTER)
    t3.parts.setValue(coin.SoText3.FRONT | coin.SoText3.BACK)
    label.addChild(font)
    label.addChild(mt)
    label.addChild(t3)
    return label, mt


def _labelBox(coin, sep, label):
    """The label's ink box on its identity frame — (xmin, xmax, ymin,
    ymax), measured, not assumed: this Coin build hangs glyphs below
    the baseline for some frame orientations and above it for others,
    so no constant describes where the ink sits relative to the
    anchor."""
    path = coin.SoPath()
    path.setHead(sep)
    path.append(label)
    act = coin.SoGetBoundingBoxAction(coin.SbViewportRegion(8, 8))
    act.apply(path)
    bb = act.getBoundingBox()
    mn, mx = bb.getMin(), bb.getMax()
    return mn[0], mx[0], mn[1], mx[1]


def _labelCacheKey(text, scale):
    return (text, round(scale, 4))


_LABEL_BOXES = {}


def _labelExtents(coin, sep, label, text, scale):
    """(along_centre, across_centre, along_half) of the label's ink on
    its identity frame, cached per text and scale."""
    key = _labelCacheKey(text, scale)
    if key not in _LABEL_BOXES:
        xmin, xmax, ymin, ymax = _labelBox(coin, sep, label)
        _LABEL_BOXES[key] = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0,
                             (xmax - xmin) / 2.0)
    return _LABEL_BOXES[key]


def _buildNode(chains):
    """The Coin overlay node for one segment: a dimension line and end
    ticks per run plus one run-aligned label per run. chains is what
    _dimRuns returns. The line is cut short of the label's measured
    half width — text and line share the dimension plane, so the gap
    keeps the line out of the label's screen footprint from every
    view. Each label is built on an identity frame, its ink box is
    measured, and it is placed so the measured ink centre lands exactly
    on the run's midpoint: this Coin build hangs glyphs below the
    baseline for some frame orientations and above it for others, so
    placement follows measurement, never constants. Runs too short for
    a full-size label shrink it (to _MIN_SCALE) so the line keeps
    visible stubs."""
    from pivy import coin
    sep = coin.SoSeparator()
    sep.setName(DIM_NODE)
    style = coin.SoDrawStyle()
    style.lineWidth.setValue(_LINE_WIDTH)
    mat = coin.SoMaterial()
    mat.diffuseColor.setValue(*_DIM_COLOR)
    coords = coin.SoCoordinate3()

    # Labels first: the line gap needs each label's measured width, and
    # the measurement runs on an identity frame inside the live graph.
    placed = []
    halfs = []
    vp = coin.SbViewportRegion(8, 8)
    for _line, _ticks, anchor, d, up, text in chains:
        scale = _labelScale(polyline_length(_line), text)
        label, mt = _labelNode(coin, text, scale)
        sep.addChild(label)
        along_c, across_c, along_half = _labelExtents(
            coin, sep, label, text, scale)
        halfs.append(along_half + _GAP_PAD)
        placed.append((label, mt, anchor, d, up, along_c, across_c))

    points = []
    index = []

    def segment(a, b):
        i = len(points)
        points.append(a)
        points.append(b)
        index.extend([i, i + 1, -1])

    for (line, ticks, _pt, _dir, _up, _text), half in zip(chains, halfs):
        for piece in _gappedLine(line, half):
            for a, b in zip(piece, piece[1:]):
                segment(a, b)
        for tick in ticks:
            segment(tick[0], tick[1])
    coords.point.setValues(0, len(points), points)
    lineset = coin.SoIndexedLineSet()
    lineset.coordIndex.setValues(0, len(index), index)
    sep.addChild(coords)
    sep.addChild(lineset)

    # First guess: compensate the identity-frame ink centre. This Coin
    # build then hangs the glyphs on the opposite side of the baseline
    # once the label's matrix rotates it, so re-measure every placed
    # label in world space and shift the exact residual — the ink
    # centre lands on the anchor whatever the glyph convention is.

    def _frame(d, up):
        yv = up if up is not None else (0.0, 1.0, 0.0)
        dv = d if d is not None else (1.0, 0.0, 0.0)
        return dv, yv, _cross(dv, yv)

    def _matrix(dv, yv, nv, base):
        m = coin.SbMatrix()
        m.setValue(((dv[0], yv[0], nv[0], 0.0),
                    (dv[1], yv[1], nv[1], 0.0),
                    (dv[2], yv[2], nv[2], 0.0),
                    (base[0], base[1], base[2], 1.0)))
        return m

    vp = coin.SbViewportRegion(8, 8)
    for i, (label, mt, anchor, d, up, along_c, across_c) in enumerate(placed):
        dv, yv, nv = _frame(d, up)
        base = _sub(anchor, _add(_mul(dv, along_c), _mul(yv, across_c)))
        mt.matrix.setValue(_matrix(dv, yv, nv, base))
        placed[i] = (label, mt, anchor, dv, yv, nv, base)

    for i, (label, mt, anchor, dv, yv, nv, base) in enumerate(placed):
        path = coin.SoPath()
        path.setHead(sep)
        path.append(label)
        for _attempt in range(4):
            act = coin.SoGetBoundingBoxAction(vp)
            act.apply(path)
            cx, cy, cz = act.getBoundingBox().getCenter().getValue()
            dx, dy, dz = anchor[0] - cx, anchor[1] - cy, anchor[2] - cz
            if dx * dx + dy * dy + dz * dz < 1.0:
                break
            base = (base[0] + dx, base[1] + dy, base[2] + dz)
            mt.matrix.setValue(_matrix(dv, yv, nv, base))
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
    runs = {}    # segmentEdgeRuns memo, shared by one sync pass
    for sel in FreeCADGui.Selection.getSelectionEx():
        obj = getattr(sel, "Object", None)
        if walls_object.is_segment(obj):
            _mergeScope(scopes, order, obj,
                        _selectionScope(obj, sel, runs))
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
                            _faceRunScope(seg, local, runs))
    return [(seg, scopes[_key(seg)]) for seg in order]


def _selectionScope(seg, sel, runs=None):
    """The run scope one direct segment selection member implies: None
    (every run) when it names no faces, else the union of the runs its
    picked faces map to. runs is the pass's segmentEdgeRuns memo."""
    names = list(getattr(sel, "SubElementNames", None) or ())
    if not any(n.startswith("Face") for n in names):
        return None
    scope = set()
    for name in names:
        if name.startswith("Face"):
            scope |= _faceRunScope(seg, name, runs)
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


_sync_timer = None


def _scheduleSync():
    """Coalesce a burst of selection events into one sync. Expanding a
    tree selection to its faces fires addSelection once per face, and a
    full resync per event stalled segment clicks for seconds on large
    plans; the 0 ms single shot restarts per event, so the resync runs
    once after the burst settles."""
    global _sync_timer
    if _sync_timer is not None:
        _sync_timer.start()
        return
    try:
        from PySide import QtCore
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(sync)
        timer.start()
        _sync_timer = timer
    except Exception:
        sync()


class _SelectionDims:
    """Selection observer scheduling the length-dim resync on every
    selection change (coalesced — see _scheduleSync)."""

    def addSelection(self, *_args):
        _scheduleSync()

    def removeSelection(self, *_args):
        _scheduleSync()

    def clearSelection(self, *_args):
        _scheduleSync()

    def setSelection(self, *_args):
        _scheduleSync()

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
