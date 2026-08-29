# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WallsPlus objects: a wall that references a shared sketch (never owns it)
# and builds one segment group per claimed sketch edge. One class plays both
# roles: the Wall root (no shape; defaults + hosted openings) and nestable
# WallSegment children (fused extrusions minus intersecting openings). The
# view provider lives here too, so factories attach it with or without the
# gui module — the stairs precedent.

import os

import FreeCAD
from FreeCAD import Vector

from archplus.tools.walls import model

TYPE_WALL = "Wall"
TYPE_SEGMENT = "WallSegment"

ICON = os.path.join(os.path.dirname(__file__), "resources", "icons",
                    "WallPlus.svg")


class _Wall:
    """Proxy for both roles: the root wall and its segments."""

    def __init__(self, obj, root=False):
        self.Type = TYPE_WALL if root else TYPE_SEGMENT
        obj.Proxy = self
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
                obj.addProperty("App::PropertyLinkListHidden", "Subtractions",
                                "Wall",
                                "Hosted doors/windows; each segment cuts the ones "
                                "intersecting it")
            if "Tag" not in pl:
                obj.addProperty("App::PropertyString", "Tag", "Wall",
                                "Reference code shown in schedules")
        else:
            if "Wall" not in pl:
                obj.addProperty("App::PropertyLinkHidden", "Wall", "Wall",
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
                obj.Align = ["Inherit", "Left", "Right", "Center"]
                obj.Align = "Inherit"

    def onChanged(self, obj, prop):
        if prop == "Base" and obj.Base is not None and self.Type == TYPE_WALL:
            for seg in all_segments(obj):
                seg.Base = obj.Base
        if prop == "Group":
            root = wall_root(obj) or obj
            for seg in all_segments(root):
                seg.touch()
        if prop in ("Edges", "Rest"):
            root = wall_root(obj)
            if root is not None:
                for seg in all_segments(root):
                    seg.touch()
        if self.Type == TYPE_WALL and prop in (
                "Width", "Height", "Align", "Offset", "Subtractions"):
            for seg in all_segments(obj):
                seg.touch()
        if self.Type == TYPE_SEGMENT and prop in (
                "Width", "Height", "Align", "Offset"):
            for seg in all_segments(obj):
                seg.touch()

    def execute(self, obj):
        """Root: clear the placeholder shape, report claims, and re-mark the
        segments when hosted openings exist — Hosts-only windows reach the
        root through no dependency or property change, so without this their
        cuts never reach the segments. Segment: build."""
        import Part
        if self.Type == TYPE_WALL:
            obj.Shape = Part.Shape()
            self._reportClaims(obj)
            if _hostedOpenings(obj):
                for seg in all_segments(obj):
                    seg.touch()
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
        has_rest = any(n.rest for n in nodes)
        if not has_rest:
            unclaimed = [n for n in names if n not in claimed]
            if unclaimed:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: %d sketch edge(s) unclaimed and no rest segment "
                    "to build them\n" % len(unclaimed))
        for win in _hostedOpenings(obj):
            sub = opening_volume(win, obj)
            if sub is None:
                continue
            hit = False
            for seg in all_segments(obj):
                if seg.Shape.isNull() or seg.Shape.Volume == 0:
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
        empty = Part.makeCompound([])
        sketch = obj.Base
        if sketch is None or not hasattr(sketch, "Shape"):
            obj.Shape = empty
            return
        subnames = self._claimedEdges(obj)
        if not subnames:
            obj.Shape = empty
            return
        cfg = effectiveValues(obj)
        height = cfg["Height"]
        if height <= 0:
            obj.Shape = empty
            return
        normal = sketch.getGlobalPlacement().Rotation.multVec(Vector(0, 0, 1))
        edges = []
        for sub in subnames:
            try:
                edges.append(sketch.Shape.getElement(sub))
            except Exception:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: sketch edge '%s' could not be read; skipped\n"
                    % sub)
        if not edges:
            obj.Shape = empty
            return
        try:
            chains = Part.getSortedClusters(edges)
        except Exception:
            chains = [[edge] for edge in edges]
        solids = []
        for chain in chains:
            try:
                face = chainFootprint(chain, cfg["Width"], cfg["Align"],
                                      cfg["Offset"], normal)
            except Exception as exc:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: segment '%s': mitered chain build failed (%s); "
                    "building its edges separately\n" % (obj.Label, exc))
                for edge in chain:
                    face = footprint(edge, cfg["Width"], cfg["Align"],
                                     cfg["Offset"], normal)
                    if face is None:
                        continue
                    solids.append(face.extrude(normal * height))
                continue
            solids.append(face.extrude(normal * height))
        if not solids:
            obj.Shape = empty
            return
        shape = solids.pop(0)
        for s in solids:
            shape = shape.fuse(s)
        root = obj.Wall
        if root is not None:
            for win in _hostedOpenings(root):
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
    return [n for n in sketch.Shape.ElementMap.values()
            if n.startswith("Edge")]


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


def _offset2d(edge, dist, normal):
    """Offset a sketch edge within its plane.

    makeOffset2D refuses bare straight edges (a lone line segment does not
    define a unique plane), so build that case directly: `normal` is the
    sketch plane's global unit normal and the offset runs left of the travel
    direction, matching makeOffset2D's convention.
    """
    if dist == 0:
        return edge.copy()
    try:
        return edge.makeOffset2D(dist, 2, False, True)
    except Exception:
        pass
    p1 = edge.Vertexes[0].Point
    p2 = edge.Vertexes[-1].Point
    d = (p2 - p1).normalize()
    perp = normal.cross(d)
    import Part
    return Part.Edge(Part.LineSegment(p1 + perp * dist, p2 + perp * dist))


def footprint(edge, width, align, offset, normal):
    """The wall footprint face for one sketch edge, in global coords."""
    import Part
    try:
        if align == "Center":
            a = _offset2d(edge, offset - width / 2.0, normal)
            b = _offset2d(edge, offset + width / 2.0, normal)
        else:
            side = -1.0 if align == "Right" else 1.0
            a = _offset2d(edge, side * offset, normal)
            b = _offset2d(edge, side * (offset + width), normal)
        pa1, pa2 = a.Vertexes[0].Point, a.Vertexes[-1].Point
        pb1, pb2 = b.Vertexes[0].Point, b.Vertexes[-1].Point
        if pa1.distanceToPoint(pb1) > pa1.distanceToPoint(pb2):
            pb1, pb2 = pb2, pb1
        wire = Part.Wire([Part.Edge(Part.LineSegment(pa1, pb1)), b,
                          Part.Edge(Part.LineSegment(pb2, pa2)), a])
        return Part.Face(wire)
    except Exception:
        return None


def chainFootprint(edges, width, align, offset, normal):
    """The mitered wall footprint face for one connected chain of sketch
    edges, in global coords. Raises when the chain cannot be offset; the
    caller then falls back to per-edge footprints.

    The chain wire is offset twice within the sketch plane — signed
    distances are positive left of the sketch edges' travel directions,
    the same convention as the per-edge footprints — and the wall band is
    built between the two offset wires, so shared corners come out mitered
    and closed loops build as one ring with a hole."""
    import Part
    wire = _chainWire(edges)
    poly = _chainPolyline(edges)
    d1, d2 = _chainOffsets(width, align, offset)
    a = _offsetChainWire(wire, poly, d1, normal)
    b = _offsetChainWire(wire, poly, d2, normal)
    if wire.isClosed():
        return _ringFace(a, b)
    return _bandFace(a, b)


def _chainWire(edges):
    import Part
    wire = Part.Wire(edges)
    if not wire.isValid() or not wire.Edges:
        raise ValueError("chain edges do not form a wire")
    return wire


def _chainOffsets(width, align, offset):
    if align == "Center":
        return offset - width / 2.0, offset + width / 2.0
    side = -1.0 if align == "Right" else 1.0
    return side * offset, side * (offset + width)


def _edgePoints(edge):
    """The edge's points in its own sketch travel direction."""
    if type(edge.Curve).__name__ in ("Line", "LineSegment"):
        return [v.Point for v in edge.Vertexes]
    pts = edge.discretize(Number=24)
    if edge.isClosed():
        pts.append(pts[0])
    return pts


def _chainPolyline(edges):
    """Discretized points along the chain, each edge taken in its own
    sketch travel direction; raises when the edge directions do not
    traverse the chain head-to-tail, since a doubled-back chain cannot
    take one uniform offset side."""
    remaining = []
    for edge in edges:
        if edge.Length >= 1e-9:
            remaining.append(_edgePoints(edge))
    if not remaining:
        raise ValueError("chain has no usable edges")
    pts = list(remaining.pop(0))
    while remaining:
        for i, ev in enumerate(remaining):
            if ev[0].distanceToPoint(pts[-1]) <= 1e-3:
                pts.extend(ev[1:])
                remaining.pop(i)
                break
        else:
            break
    while remaining:
        for i, ev in enumerate(remaining):
            if ev[-1].distanceToPoint(pts[0]) <= 1e-3:
                pts = ev[:-1] + pts
                remaining.pop(i)
                break
        else:
            raise ValueError("chain edges do not follow one travel direction")
    return pts


def _offsetChainWire(wire, poly, dist, normal):
    """Offset a chain wire inside its sketch plane; positive dist is left
    of the chain's sketch travel direction."""
    import Part
    if dist == 0:
        return wire.copy()
    if all(type(e.Curve).__name__ in ("Line", "LineSegment")
           for e in wire.Edges):
        return _offsetStraightWire(poly, dist, normal)
    if wire.isClosed():
        area = 0.0
        for i in range(len(poly)):
            area += poly[i].cross(poly[(i + 1) % len(poly)]).dot(normal)
        return wire.makeOffset2D(-dist if area > 0 else dist, 2, False, False)
    result = wire.makeOffset2D(-dist, 2, False, True)
    if not _offsetIsLeft(poly, result, dist, normal):
        result = wire.makeOffset2D(dist, 2, False, True)
        if not _offsetIsLeft(poly, result, dist, normal):
            raise ValueError("wire offset landed on the wrong side")
    return result


def _offsetIsLeft(poly, offset_wire, dist, normal):
    """True when offset_wire sits dist left of the poly's travel at its
    start."""
    start = poly[0]
    travel = poly[1] - start if len(poly) > 1 else None
    if travel is None or travel.Length < 1e-9:
        return True
    left = normal.cross(travel.normalize())
    near = min((v.Point for v in offset_wire.Vertexes),
               key=lambda p: p.distanceToPoint(start))
    return near.sub(start).dot(left) * dist > -1e-9


def _offsetStraightWire(pts, dist, normal):
    """Exact in-plane offset of a straight-chain polyline with mitered
    corners.

    makeOffset2D refuses straight-only wires (a straight chain does not
    define a unique plane), so the offset lines are built by hand and
    consecutive lines are intersected for the miters. Positive dist is
    left of the chain's travel direction."""
    import Part
    closed = pts[0].distanceToPoint(pts[-1]) <= 1e-3
    pts = pts[:-1] if closed else list(pts)
    n = len(pts)
    if n < (3 if closed else 2):
        raise ValueError("degenerate chain")
    count = n if closed else n - 1
    dirs = [(pts[(i + 1) % n] - pts[i]).normalize() for i in range(count)]
    perps = [normal.cross(d) for d in dirs]
    q = [] if closed else [pts[0] + perps[0] * dist]
    for i in range(0 if closed else 1, n if closed else n - 1):
        u = dirs[(i - 1) % count]
        v = dirs[i % count]
        denom = u.cross(v).dot(normal)
        if abs(denom) < 1e-9:
            if u.dot(v) < 0:
                raise ValueError("chain doubles back on itself")
            continue
        a1 = pts[(i - 1) % n] + perps[(i - 1) % count] * dist
        a2 = pts[i] + perps[i % count] * dist
        t = (a2 - a1).cross(v).dot(normal) / denom
        q.append(a1 + u * t)
    if not closed:
        q.append(pts[n - 1] + perps[-1] * dist)
    if len(q) < (3 if closed else 2):
        raise ValueError("offset chain degenerated")
    edges = []
    for i in range(len(q) if closed else len(q) - 1):
        p1 = q[i]
        p2 = q[(i + 1) % len(q)]
        if p1.distanceToPoint(p2) < 1e-9:
            raise ValueError("offset chain degenerated")
        edges.append(Part.LineSegment(p1, p2).toShape())
    result = Part.Wire(edges)
    if not result.isValid():
        raise ValueError("offset wire is invalid")
    return result


def _ringFace(a, b):
    """The annular face between two closed offset wires."""
    import Part
    f1 = Part.Face(a)
    f2 = Part.Face(b)
    outer, inner = (f1, f2) if f1.Area >= f2.Area else (f2, f1)
    ring = outer.cut(inner)
    if len(ring.Faces) != 1 or ring.Area <= 1e-9 or not ring.isValid():
        raise ValueError("offset ring did not produce one face")
    return ring


def _bandFace(a, b):
    """The band face between two open offset wires, closed at the free
    ends with connecting lines."""
    import Part
    pa = [v.Point for v in a.Vertexes]
    pb = [v.Point for v in b.Vertexes]
    pa1, pa2 = pa[0], pa[-1]
    pb1, pb2 = pb[0], pb[-1]
    if pa1.distanceToPoint(pb1) > pa1.distanceToPoint(pb2):
        pb1, pb2 = pb2, pb1
    edges = ([Part.LineSegment(pa1, pb1).toShape()] + list(b.Edges)
             + [Part.LineSegment(pb2, pa2).toShape()] + list(a.Edges))
    wires = []
    try:
        wires.append(Part.Wire(Part.__sortEdges__(edges)))
    except Exception:
        pass
    try:
        wires.append(Part.Wire(edges))
    except Exception:
        pass
    for wire in wires:
        try:
            face = Part.Face(wire)
        except Exception:
            continue
        if face.isValid() and len(face.Faces) == 1 and face.Area > 1e-9:
            return face
    raise ValueError("chain band did not produce one face")


def _hostedOpenings(root):
    """The doors/windows cutting this wall: everything listed in
    Subtractions plus anything hosted Arch-style through a Hosts link,
    deduplicated."""
    out = list(getattr(root, "Subtractions", None) or [])
    for obj in root.InList:
        if obj in out:
            continue
        if root in (getattr(obj, "Hosts", None) or []):
            out.append(obj)
    return out


def opening_volume(win, root):
    """The subtraction volume for a hosted door/window (or None).

    Segments recompute before their hosts' windows in one recompute pass, so
    the window's base sketch can still be unbuilt when this runs; recompute it
    on demand or the hole wires are not there yet."""
    proxy = getattr(win, "Proxy", None)
    if proxy is not None and hasattr(proxy, "getSubVolume"):
        try:
            base = getattr(win, "Base", None)
            if base is not None and "Touched" in base.State:
                base.recompute()
            return proxy.getSubVolume(win, host=root)
        except Exception:
            return None
    return getattr(win, "Shape", None)


class _ViewProviderWall:
    """View provider for both roles; defined here (not in gui.py) so every
    factory-built wall and segment carries it, headless imports included.
    GUI-side work is resolved lazily inside the methods."""

    def __init__(self, vobj):
        vobj.Proxy = self
        self.Object = vobj.Object

    def attach(self, vobj):
        self.Object = vobj.Object

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def getIcon(self):
        return ICON

    def claimChildren(self):
        obj = getattr(self, "Object", None)
        return list(getattr(obj, "Group", None) or [])

    def setupContextMenu(self, vobj, menu):
        if not is_segment(vobj.Object):
            return
        try:
            from draftutils.translate import translate
        except Exception:
            def translate(ctxt, txt):
                return txt
        import FreeCADGui
        from PySide import QtGui
        action = QtGui.QAction(translate("Arch", "Split / move segment…"),
                               menu)
        action.triggered.connect(
            lambda: FreeCADGui.runCommand("ArchPlus_WallSplit", 0))
        menu.addAction(action)

    def setEdit(self, vobj, mode=0):
        from archplus.tools.walls import gui
        obj = vobj.Object
        if getattr(getattr(obj, "Proxy", None), "Type", None) == TYPE_WALL:
            gui.showWallPanel(obj)
        else:
            gui.showSegmentPanel(obj)
        return True

    def unsetEdit(self, vobj, mode=0):
        import FreeCADGui
        FreeCADGui.Control.closeDialog()
        return False


def makeWall(doc=None, sketch=None, name="Wall"):
    """Create the wall root plus one rest child. Returns the root."""
    doc = doc or FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    obj.addExtension("App::GroupExtensionPython")
    _Wall(obj, root=True)
    if FreeCAD.GuiUp:
        _ViewProviderWall(obj.ViewObject)
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
    obj.addExtension("App::GroupExtensionPython")
    _Wall(obj, root=False)
    if FreeCAD.GuiUp:
        _ViewProviderWall(obj.ViewObject)
    root = wall_root(parent) if is_segment(parent) else parent
    obj.Wall = root
    obj.Base = parent.Base
    obj.Align = "Inherit"
    parent.addObject(obj)
    return obj


def moveSegmentEdges(source, target, subnames):
    """Move claimed edges from `source` into the existing `target` segment.

    The target gains explicit claims; the source drops them from its own
    claims, except when it is the rest segment — rest claims are dynamic,
    so adding explicit claims to the target is enough (the rest rebuilds
    without those edges on its own)."""
    if target is source:
        return
    edges = []
    claimed = set()
    for link, subs in getattr(target, "Edges", None) or []:
        edges.append((link, tuple(subs)))
        claimed.update(subs)
    fresh = tuple(s for s in subnames if s not in claimed)
    if fresh and target.Base is not None:
        edges.append((target.Base, fresh))
        target.Edges = edges
    if not source.Rest:
        remaining = []
        for link, subs in getattr(source, "Edges", None) or []:
            subs = tuple(s for s in subs if s not in subnames)
            if subs:
                remaining.append((link, subs))
        source.Edges = remaining


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
