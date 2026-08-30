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
