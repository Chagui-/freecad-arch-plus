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
                obj.Align = ["Inherit", "Center", "Left", "Right"]
                obj.Align = "Inherit"

    def onChanged(self, obj, prop):
        if prop == "Base" and obj.Base is not None and self.Type == TYPE_WALL:
            for seg in all_segments(obj):
                seg.Base = obj.Base
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
        has_rest = any(getattr(n, "Rest", False) for n in nodes)
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


def _offset2d(edge, dist):
    """Offset a sketch edge within its plane.

    makeOffset2D refuses bare straight edges (a lone line segment does not
    define a unique plane), so build that case directly: the offset runs
    left of the travel direction, matching makeOffset2D's convention.
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
    perp = Vector(0, 0, 1).cross(d)
    import Part
    return Part.Edge(Part.LineSegment(p1 + perp * dist, p2 + perp * dist))


def footprint(edge, width, align, offset):
    """The wall footprint face for one sketch edge, in global coords."""
    import Part
    try:
        if align == "Center":
            a = _offset2d(edge, offset - width / 2.0)
            b = _offset2d(edge, offset + width / 2.0)
        else:
            side = 1.0 if align == "Right" else -1.0
            a = _offset2d(edge, side * offset)
            b = _offset2d(edge, side * (offset + width))
        pa1, pa2 = a.Vertexes[0].Point, a.Vertexes[-1].Point
        pb1, pb2 = b.Vertexes[0].Point, b.Vertexes[-1].Point
        if pa1.distanceToPoint(pb1) > pa1.distanceToPoint(pb2):
            pb1, pb2 = pb2, pb1
        wire = Part.Wire([Part.Edge(Part.LineSegment(pa1, pb1)), b,
                          Part.Edge(Part.LineSegment(pb2, pa2)), a])
        return Part.Face(wire)
    except Exception:
        return None


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


def makeWall(doc=None, sketch=None, name="Wall"):
    """Create the wall root plus one rest child. Returns the root."""
    doc = doc or FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", name)
    obj.addExtension("App::GroupExtensionPython")
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
    obj.addExtension("App::GroupExtensionPython")
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
