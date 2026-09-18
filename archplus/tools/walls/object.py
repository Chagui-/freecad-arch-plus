# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WallsPlus objects: a wall that references a shared sketch (never owns it)
# and builds one segment group per claimed sketch edge. One class plays both
# roles: the Wall root (no shape; defaults + hosted openings) and nestable
# WallSegment children (fused extrusions minus intersecting openings). The
# view provider lives here too, so factories attach it with or without the
# gui module — the stairs precedent.
#
# Both roles report Proxy.Type "Wall" (the role lives in the proxy's Segment
# flag): FreeCAD's section/SVG fuse paths only fuse objects whose Draft type
# is "Wall" or "Structure" (Shape2DView.FuseArch, ArchSectionPlane joinArch),
# so a "WallSegment" type makes segments invisible to them and they cut
# through the section individually, unfused.

import os

import FreeCAD
from FreeCAD import Vector

from archplus.tools.walls import model

TYPE_WALL = "Wall"
# Legacy role marker kept only for the onDocumentRestored migration of
# documents saved before segments reported Type "Wall".
TYPE_SEGMENT = "WallSegment"

ICON = os.path.join(os.path.dirname(__file__), "resources", "icons",
                    "WallPlus.svg")


class _Wall:
    def _is_segment_role(self):
        """Role discriminator tolerant of pre-retype proxies: a legacy
        segment instance carries Type 'WallSegment' and no Segment flag,
        and restore-time callbacks (onChanged/execute) can fire before
        onDocumentRestored migrates it — read the role through here."""
        seg = getattr(self, "Segment", None)
        if seg is None:
            return self.Type == TYPE_SEGMENT
        return seg

    # An Arch wall reports Type "Wall" as well — its proxy class is even called
    # _Wall — so the type alone cannot say whether an object is one of ours.
    # It matters: an Arch wall owns the faces a pick reports, while a root here
    # has none and claims its segments'. is_root() checks this marker.
    WALLS_PLUS = True

    def __init__(self, obj, root=False):
        self.Type = TYPE_WALL
        self.Segment = not root
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
                                "Claimed sketch edges; empty with Fallback=true "
                                "claims everything unclaimed")
            if "Fallback" not in pl:
                obj.addProperty("App::PropertyBool", "Fallback", "Wall",
                                "Claim every sketch edge no other segment claims "
                                "(one per wall)")
            if "Width" not in pl:
                obj.addProperty("App::PropertyLength", "Width", "Wall",
                                "0 = inherit from the wall/group")
            if "Height" not in pl:
                obj.addProperty("App::PropertyLength", "Height", "Wall",
                                "0 = inherit from the wall/group")
            if "Subtractions" not in pl:
                obj.addProperty("App::PropertyLinkListHidden", "Subtractions",
                                "Wall",
                                "Hosted doors/windows cutting this segment")
            if "Align" not in pl:
                obj.addProperty("App::PropertyEnumeration", "Align", "Wall",
                                "Inherit = use the wall/group alignment")
                obj.Align = ["Inherit", "Left", "Right", "Center"]
                obj.Align = "Inherit"

    def onChanged(self, obj, prop):
        if prop == "Base" and obj.Base is not None and not self._is_segment_role():
            for seg in all_segments(obj):
                seg.Base = obj.Base
        if prop == "Group":
            root = wall_root(obj) or obj
            for seg in all_segments(root):
                seg.touch()
        if prop in ("Edges", "Fallback"):
            root = wall_root(obj)
            if root is not None:
                for seg in all_segments(root):
                    seg.touch()
        if not self._is_segment_role() and prop in (
                "Width", "Height", "Align", "Offset", "Subtractions"):
            # Subtractions too: the segments cut the root's hosted openings,
            # so unhooking one there (or from a Hosts link, which the opening
            # side syncs through this property) must re-run them or the old
            # opening stays cut out of the wall.
            for seg in all_segments(obj):
                seg.touch()
        if self._is_segment_role() and prop in (
                "Width", "Height", "Align", "Offset"):
            root = wall_root(obj)
            for seg in all_segments(root or obj):
                seg.touch()

    def onDocumentRestored(self, obj):
        # Documents saved before the retype carry the role in Type
        # ("Wall"/"WallSegment") and lack the Segment flag.
        if not hasattr(self, "Segment"):
            self.Segment = (self.Type == TYPE_SEGMENT)
            self.Type = TYPE_WALL
            # Rebuild: restore-time callbacks may have run the root path
            # while the legacy proxy still carried the old role marker.
            obj.touch()
        self.setProperties(obj, not self.Segment)
        if self.Segment and "Rest" in obj.PropertiesList:
            obj.Fallback = obj.Rest
            obj.removeProperty("Rest")
        if not self.Segment and not obj.Placement.isIdentity():
            # Roots have no shape; a non-identity placement would displace
            # every claimed child's scene node (segments and hosted
            # openings) by that offset — a phantom extra storey. Position
            # walls through the sketch placement instead.
            obj.Placement = FreeCAD.Placement()

    def execute(self, obj):
        """Root: clear the placeholder shape and report claims. Segment:
        build. The openings reach the segments through the segments' own
        Subtractions links (kept in sync by the Hosts onChanged below), so
        no touch cascade runs here — a root touch loop re-enters through
        the group-touched chain and left everything 'still touched after
        recompute', rebuilding every opening cut on every pass (the
        multi-second UI freeze after closing a task panel)."""
        import Part
        if not self._is_segment_role():
            obj.Shape = Part.Shape()
            self._reportClaims(obj)
            return
        self._buildSegment(obj)

    def syncSegmentSubtractions(self, obj):
        """Mirror the hosted openings into every segment's Subtractions so
        the dependency graph re-runs the segments when an opening changes.
        Called from the opening side (Hosts link set/removed) via the wall
        root, and once at wall creation."""
        openings = _hostedOpenings(obj)
        changed = False
        for seg in all_segments(obj):
            if list(getattr(seg, "Subtractions", None) or []) != list(openings):
                seg.Subtractions = openings
                changed = True
        return changed

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
        has_fallback = any(n.fallback for n in nodes)
        if not has_fallback:
            unclaimed = [n for n in names if n not in claimed]
            if unclaimed:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: %d sketch edge(s) unclaimed and no fallback "
                    "segment to build them\n" % len(unclaimed))
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
        # Build in the sketch's GLOBAL frame: edges come from the sketch
        # shape (which carries the sketch placement), the wall rises along
        # the sketch plane normal, and the segment keeps an identity
        # placement. With identity-placed wall roots (required — see
        # makeWall) the rendered position is exactly the built position;
        # level placements stay at zero for this file's absolute authoring.
        normal = sketch.Placement.Rotation.multVec(Vector(0, 0, 1))
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
        # A claim set can branch (partitions joining a ring), and the
        # offset band needs one simple traversal to produce one face, so
        # split at every vertex where more than two endpoints meet; each
        # simple chain offsets cleanly and junction ends butt into the
        # crossing band.
        usable = [edge for edge in edges if edge.Length >= 1e-9]
        chains = [[usable[i] for i in group]
                  for group in model.chain_splits(_chainLinks(usable))]
        root = obj.Wall
        owners = _edgeOwners(root) if root is not None else {}
        sk_edges = []
        if owners:
            for name in _sketchEdgeNames(sketch):
                try:
                    sk_edges.append((name, sketch.Shape.getElement(name)))
                except Exception:
                    continue
        solids = []
        for chain in chains:
            miters = None
            if owners:
                try:
                    miters = _miterEnds(obj, normal, chain,
                                        sk_edges, owners, cfg)
                except Exception:
                    miters = None
            try:
                face = chainFootprint(chain, cfg["Width"], cfg["Align"],
                                      cfg["Offset"], normal, miters)
            except Exception as exc:
                if miters and (miters[0] or miters[1]):
                    try:
                        face = chainFootprint(chain, cfg["Width"],
                                              cfg["Align"], cfg["Offset"],
                                              normal)
                        FreeCAD.Console.PrintWarning(
                            "ArchPlus: segment '%s': seam miter fell back "
                            "to a butt joint\n" % obj.Label)
                        solids.append(face.extrude(normal * height))
                        continue
                    except Exception:
                        pass
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
        try:
            # Fusing same-height bands leaves the coplanar top and bottom
            # faces split along the old overlap boundaries, which reads as
            # seams at every junction; the merge is purely cosmetic, so a
            # failure must not lose the fused shape (partslib precedent).
            shape = shape.removeSplitter()
        except Exception:
            pass
        if root is not None:
            for win in _hostedOpenings(root):
                sub = opening_volume(win, root)
                if sub is None or sub.Volume == 0:
                    continue
                if not shape.BoundBox.intersect(sub.BoundBox):
                    continue
                # No "does it really intersect?" probe before the cut: the
                # probe (shape.common(sub)) costs as much as the cut itself
                # (measured ~4 ms each on a 4 m run), so it bought nothing —
                # overlapping boxes now pay one boolean instead of two, and
                # a tool that turns out to be disjoint leaves the geometry
                # untouched (same volume, same solid count) for that one
                # boolean.
                try:
                    shape = shape.cut(sub)
                except Exception:
                    pass
        obj.Shape = shape
        obj.Placement = FreeCAD.Placement()

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
    node = model.ClaimNode(obj, subs, bool(getattr(obj, "Fallback", False)))
    node.children = [_claimNode(c) for c in getattr(obj, "Group", [])
                     if is_segment(c)]
    return node


def _sketchEdgeNames(sketch):
    return [n for n in sketch.Shape.ElementMap.values()
            if n.startswith("Edge")]


def is_segment(obj):
    proxy = getattr(obj, "Proxy", None)
    return (getattr(proxy, "Type", None) == TYPE_WALL
            and bool(getattr(proxy, "Segment", False)))


def is_root(obj):
    proxy = getattr(obj, "Proxy", None)
    return (getattr(proxy, "Type", None) == TYPE_WALL
            and getattr(proxy, "WALLS_PLUS", False)
            and not getattr(proxy, "Segment", False))


def wall_root(segment):
    return getattr(segment, "Wall", None)


def all_segments(root):
    out = []
    for o in getattr(root, "Group", []) or []:
        if is_segment(o):
            out.append(o)
            out.extend(all_segments(o))
    return out


def _pointBoxDistance(box, point):
    """Distance from `point` to a bounding box (0 inside).

    The OCC distance in resolveRootFace dominates a wall-wide face scan — a
    wall with two segments is ~70 faces, tens of ms per mouse move from the
    placement tools' hover path. A face whose box is further than the
    tolerance cannot hold the point, so the cheap test rules it out first."""
    dx = max(box.XMin - point.x, 0.0, point.x - box.XMax)
    dy = max(box.YMin - point.y, 0.0, point.y - box.YMax)
    dz = max(box.ZMin - point.z, 0.0, point.z - box.ZMax)
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def resolveRootFace(root, subname, point):
    """The segment owning a root face selection, as (segment, [localsub]).

    FreeCAD attributes a 3D pick of a claimed child's face to the top claim
    parent and indexes the face across the faces of ALL claimed children,
    so the reported subname does not exist in any one segment. The pick
    point therefore decides: the segment whose shape has a face within
    1 mm of it wins, and that face's own local subname is returned.
    Without a pick point the subname is matched per segment, where a
    unique candidate wins and several are ambiguous."""
    import Part
    segments = [s for s in all_segments(root)
                if _usableShape(s)]
    if not segments:
        return None
    if point is None:
        candidates = []
        for seg in segments:
            try:
                seg.Shape.getElement(subname)
            except Exception:
                continue
            candidates.append(seg)
        if len(candidates) == 1:
            return (candidates[0], [subname])
        return None
    try:
        vertex = Part.Vertex(point)
    except Exception:
        return None
    best = None
    best_dist = None
    best_name = None
    for seg in segments:
        faces = seg.Shape.Faces
        for i, face in enumerate(faces):
            if _pointBoxDistance(face.BoundBox, point) > 1.0:
                continue
            try:
                dist = vertex.distToShape(face)[0]
            except Exception:
                continue
            if dist > 1.0:
                continue
            if best_dist is None or dist < best_dist:
                best, best_dist = seg, dist
                best_name = "Face%d" % (i + 1)
    if best is None:
        return None
    return (best, [best_name])


def resolvePickedFace(obj, index, x=None, y=None, z=None):
    """(object, face index) to use for a 0-based face index from a 3D pick.

    A pick usually carries the face it hit, so callers index Shape directly.
    A wall pick does not: FreeCAD attributes the face to the wall's claim
    parent — the root or, for a nested pick, a segment — and counts the
    index across the faces of EVERY object the wall claims, not just the one
    named. So for a wall the index is meaningless twice over: the root has
    no faces at all, and a segment's own faces do not line up with it. Map
    such a pick onto the segment that owns the face at the pick point.

    Returns None when no shape holds the face, so callers fall back to the
    working plane instead of indexing a shape that lacks it. Picks on
    anything outside a wall come back unchanged when their shape can carry
    the index, which covers Arch walls, stairs, doors and library parts."""
    if obj is None:
        return None
    if not (is_root(obj) or is_segment(obj)):
        faces = getattr(getattr(obj, "Shape", None), "Faces", None)
        if faces is not None and 0 <= index < len(faces):
            return (obj, index)
        return None
    root = obj if is_root(obj) else (wall_root(obj) or obj)
    point = None
    if all(v is not None for v in (x, y, z)):
        try:
            point = FreeCAD.Vector(float(x), float(y), float(z))
        except (TypeError, ValueError):
            point = None
    hit = resolveRootFace(root, "Face%d" % (index + 1), point)
    if hit is None:
        return None
    segment, subnames = hit
    try:
        return (segment, int(subnames[0][4:]) - 1)
    except (IndexError, ValueError):
        return None


def followHostVisibility(obj):
    """Keep a hosted opening's visibility in step with its host walls:
    when every host is hidden the opening hides; when any host shows,
    the opening shows. Called from the opening's own view provider
    updateData on each visibility change of a host, because the wall's
    onChanged proves unreliable for the show direction."""
    hosts = getattr(obj, "Hosts", None) or []
    if not hosts:
        return
    vo = obj.ViewObject
    if vo is None:
        return
    if all(not h.ViewObject.Visibility for h in hosts
           if h.ViewObject is not None):
        vo.Visibility = False
    else:
        vo.Visibility = True


def placementPoint(point, baseFace, info):
    """Where to place: the Snapper's snap if it landed on the picked face,
    else the picked surface point.

    Draft's Snapper resolves its snap through the shape of the object the pick
    names, then falls back to the working plane when that fails. An ArchPlus
    wall's root has no shape of its own — it claims its segments' — and a
    segment pick carries an index counted across every claimed child, so no
    snap setting can land on an ArchPlus wall: the plane point is metres away
    in an angled view and the door would sit on the floor beside it. The pick
    point is on the picked face by construction, so it is where the user is
    aiming."""
    if baseFace is None or not info:
        return point
    import Part
    try:
        face = baseFace[0].Shape.Faces[baseFace[1]]
        if Part.Vertex(point).distToShape(face)[0] <= 1.0:
            return point
    except Exception:
        return point
    try:
        return FreeCAD.Vector(float(info["x"]), float(info["y"]),
                              float(info["z"]))
    except (KeyError, TypeError, ValueError):
        return point


def claimedEdges(obj):
    """The sketch subnames the segment effectively builds: its claims minus
    its descendants'. Public wrapper over the proxy's claim resolution so
    sibling modules (the dim overlay) need no proxy internals."""
    proxy = getattr(obj, "Proxy", None)
    if not hasattr(proxy, "_claimedEdges"):
        return []
    return proxy._claimedEdges(obj)


def segmentEdgeRuns(obj):
    """The segment's wall runs as plain data — one run per maximal
    straight sequence of claimed sketch edges, curved edges solo — the
    unit the built wall's side faces show. Returns [(points, normal,
    height)]: points are (x, y, z) tuples along the run in world
    coordinates, normal the sketch's global normal as a tuple, height
    the effective wall height in mm. Chains that cannot be traversed
    (doubled back) are skipped."""
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
            for pts in model.chain_runs(_chainLinks(chain)):
                out.append((pts, (normal.x, normal.y, normal.z),
                            cfg["Height"]))
        except Exception:
            continue
    return out


def _usableShape(obj):
    shape = getattr(obj, "Shape", None)
    try:
        return shape is not None and not shape.isNull() and bool(shape.Faces)
    except Exception:
        return False


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


def chainFootprint(edges, width, align, offset, normal, miters=None):
    """The mitered wall footprint face for one connected chain of sketch
    edges, in global coords. Raises when the chain cannot be offset; the
    caller then falls back to per-edge footprints.

    The chain wire is offset twice within the sketch plane — signed
    distances are positive left of the sketch edges' travel directions,
    the same convention as the per-edge footprints — and the wall band is
    built between the two offset wires, so shared corners come out mitered
    and closed loops build as one ring with a hole.

    miters is an optional (start_pair, end_pair); each pair is None for a
    butt end or (point_d1, point_d2) — the endpoints the two offset wires
    take at that chain end so that abutting segments share one seam line."""
    import Part
    wire = _chainWire(edges)
    poly = _chainPolyline(edges)
    d1, d2 = _chainOffsets(width, align, offset)
    start_m, end_m = miters if miters else (None, None)
    a = _offsetChainWire(wire, poly, d1, normal,
                         start_pt=start_m[0] if start_m else None,
                         end_pt=end_m[0] if end_m else None)
    b = _offsetChainWire(wire, poly, d2, normal,
                         start_pt=start_m[1] if start_m else None,
                         end_pt=end_m[1] if end_m else None)
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


def _lineIntersect(p1, u, p2, v, normal):
    """Intersection of two in-plane lines (point + direction Vectors), or
    None when they are parallel."""
    denom = u.cross(v).dot(normal)
    if abs(denom) < 1e-12:
        return None
    t = (p2 - p1).cross(v).dot(normal) / denom
    return p1 + u * t


def _edgeOwners(root):
    """Map each sketch edge name to the segment that effectively builds
    it, using the same claim resolution as the root's report."""
    sketch = getattr(root, "Base", None)
    if sketch is None or not hasattr(sketch, "Shape"):
        return {}
    names = _sketchEdgeNames(sketch)
    nodes = [_claimNode(n) for n in getattr(root, "Group", []) or []
             if is_segment(n)]
    if not nodes:
        return {}
    built, _warnings = model.resolve_claims(nodes, names)
    owners = {}
    for seg, claimed in built.items():
        for name in claimed:
            owners[name] = seg
    return owners


def _miterEnds(obj, normal, chain, sk_edges, owners, cfg):
    """(start_pair, end_pair) miter seam points for a chain that abuts
    other segments of the same wall; a pair is None for a butt end. Only
    all-straight chains take miters, since arcs offset through
    makeOffset2D cannot take replacement endpoints."""
    if not all(type(e.Curve).__name__ in ("Line", "LineSegment")
               for e in chain):
        return None, None
    try:
        poly = _chainPolyline(chain)
    except Exception:
        return None, None
    if poly[0].distanceToPoint(poly[-1]) <= 1e-3:
        return None, None
    return (_miterAt(obj, normal, chain, poly, True, sk_edges,
                     owners, cfg),
            _miterAt(obj, normal, chain, poly, False, sk_edges,
                     owners, cfg))


def _miterAt(obj, normal, chain, poly, at_start, sk_edges, owners,
             cfg):
    """The (point_d1, point_d2) seam pair for one open chain end, or None
    for a butt end. Both abutting segments run the same construction from
    their own side, so each pair of face lines meets in one shared point
    and the union tiles the corner without gap or overlap."""
    if at_start:
        v = poly[0]
        travel = (poly[1] - poly[0]).normalize()
        a_in = Vector(travel)
    else:
        v = poly[-1]
        travel = (poly[-1] - poly[-2]).normalize()
        a_in = travel * -1
    d1, d2 = _chainOffsets(cfg["Width"], cfg["Align"], cfg["Offset"])
    if not d1 < 0 < d2:
        return None
    candidates = []
    for name, edge in sk_edges:
        if any(edge.isSame(c) for c in chain):
            continue
        if min(v.distanceToPoint(vx.Point)
               for vx in edge.Vertexes) > 1e-7:
            continue
        candidates.append((name, edge))
    if not candidates:
        return None
    others = {owners.get(name) for name, _e in candidates}
    others.discard(None)
    others.discard(obj)
    if len(others) != 1:
        return None
    neighbor = others.pop()
    neighbor_edges = [e for name, e in candidates
                      if owners.get(name) is neighbor]
    if len(neighbor_edges) != 1:
        return None
    edge = neighbor_edges[0]
    dir_e = (edge.Vertexes[-1].Point - edge.Vertexes[0].Point).normalize()
    import Part
    edges_n = [e for name, e in sk_edges if owners.get(name) is neighbor]
    try:
        clusters = Part.getSortedClusters(edges_n)
    except Exception:
        return None
    cluster = None
    for cl in clusters:
        if any(edge.isSame(c) for c in cl):
            if cluster is not None:
                return None
            cluster = cl
    if cluster is None:
        return None
    if not all(type(e.Curve).__name__ in ("Line", "LineSegment")
               for e in cluster):
        return None
    try:
        poly_n = _chainPolyline(cluster)
    except Exception:
        return None
    if poly_n[0].distanceToPoint(poly_n[-1]) <= 1e-3:
        return None
    if (poly_n[0] - v).Length < 1e-7:
        a_in_n = (poly_n[1] - poly_n[0]).normalize()
    elif (poly_n[-1] - v).Length < 1e-7:
        a_in_n = (poly_n[-2] - poly_n[-1]).normalize()
    else:
        return None
    m = a_in + a_in_n
    if m.Length < 1e-9:
        return None
    m.normalize()
    ncfg = effectiveValues(neighbor)
    e1, e2 = _chainOffsets(ncfg["Width"], ncfg["Align"], ncfg["Offset"])
    if not e1 < 0 < e2:
        return None
    perp_m = normal.cross(travel)
    perp_n = normal.cross(dir_e)
    d_cm = d2 if perp_m.dot(m) > 0 else d1
    d_cn = e2 if perp_n.dot(m) > 0 else e1
    p_concave = _lineIntersect(v + perp_m * d_cm, travel,
                               v + perp_n * d_cn, dir_e, normal)
    d_cx_m = d1 if d_cm == d2 else d2
    d_cx_n = e1 if d_cn == e2 else e2
    p_convex = _lineIntersect(v + perp_m * d_cx_m, travel,
                              v + perp_n * d_cx_n, dir_e, normal)
    if p_concave is None or p_convex is None:
        return None
    if p_concave.distanceToPoint(p_convex) < 1e-9:
        return None
    p_d1 = p_concave if d_cm == d1 else p_convex
    p_d2 = p_concave if d_cm == d2 else p_convex
    return (p_d1, p_d2)


def _edgePoints(edge):
    """The edge's points in its own sketch travel direction."""
    if type(edge.Curve).__name__ in ("Line", "LineSegment"):
        return [v.Point for v in edge.Vertexes]
    pts = edge.discretize(Number=24)
    if edge.isClosed():
        pts.append(pts[0])
    return pts


def _chainLinks(edges):
    """[(points, is_line)] plain-data links for one chain's usable edges,
    points as (x, y, z) tuples in the edge's own travel direction."""
    links = []
    for edge in edges:
        if edge.Length >= 1e-9:
            links.append(([(p.x, p.y, p.z) for p in _edgePoints(edge)],
                          type(edge.Curve).__name__ in ("Line",
                                                        "LineSegment")))
    return links


def _chainPolyline(edges):
    """Discretized points along the chain in one consistent traversal —
    model.chain_runs reverses individual links as needed, so sketch
    edges stored in mixed directions still yield one polyline. Raises
    only when the edges do not form one connected chain, since a
    disconnected chain cannot take one uniform offset side."""
    pts = []
    for run in model.chain_runs(_chainLinks(edges)):
        if pts:
            run = run[1:]  # drop the duplicated joint between runs
        pts.extend(run)
    return [FreeCAD.Vector(x, y, z) for x, y, z in pts]


def _offsetChainWire(wire, poly, dist, normal, start_pt=None, end_pt=None):
    """Offset a chain wire inside its sketch plane; positive dist is left
    of the chain's sketch travel direction. start_pt/end_pt replace the
    open ends' offset points when the chain abuts another segment (the
    shared miter seam); they are only honored on the straight path."""
    import Part
    if dist == 0:
        return wire.copy()
    if all(type(e.Curve).__name__ in ("Line", "LineSegment")
           for e in wire.Edges):
        return _offsetStraightWire(poly, dist, normal,
                                   start_pt=start_pt, end_pt=end_pt)
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


def _offsetStraightWire(pts, dist, normal, start_pt=None, end_pt=None):
    """Exact in-plane offset of a straight-chain polyline with mitered
    corners.

    makeOffset2D refuses straight-only wires (a straight chain does not
    define a unique plane), so the offset lines are built by hand and
    consecutive lines are intersected for the miters. Positive dist is
    left of the chain's travel direction. start_pt/end_pt replace the
    first/last offset point (shared seam with an abutting segment); the
    point must lie on the end offset line, which trims or extends the
    end segment."""
    import Part
    closed = pts[0].distanceToPoint(pts[-1]) <= 1e-3
    pts = pts[:-1] if closed else list(pts)
    n = len(pts)
    if n < (3 if closed else 2):
        raise ValueError("degenerate chain")
    count = n if closed else n - 1
    dirs = [(pts[(i + 1) % n] - pts[i]).normalize() for i in range(count)]
    perps = [normal.cross(d) for d in dirs]
    q = [] if closed else [start_pt if start_pt is not None
                           else pts[0] + perps[0] * dist]
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
        q.append(end_pt if end_pt is not None
                 else pts[n - 1] + perps[-1] * dist)
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


FACE_HIGHLIGHT = "ArchPlusSegmentHighlight"
PREVIEW_HIGHLIGHT = "ArchPlusTargetPreview"


def addFaceHighlight(vobj, name=FACE_HIGHLIGHT, color=(0.15, 0.80, 0.35),
                     transparency=0.45, subs=None):
    """A translucent overlay of the object's tessellated faces on its view
    provider, tracked by node name so several overlays can coexist. With
    `subs`, only those Face subelements are drawn. Added to the scene
    graph only: never saved, never touches display properties. Returns
    True when the overlay was built."""
    removeFaceHighlight(vobj, name)
    obj = getattr(vobj, "Object", None)
    shape = getattr(obj, "Shape", None)
    if shape is None or shape.isNull() or not shape.Faces:
        return False
    if subs is not None:
        import Part
        parts = []
        for sub in subs:
            if not sub.startswith("Face"):
                continue
            try:
                part = shape.getElement(sub)
            except Exception:
                continue
            if not part.isNull() and part.Faces:
                parts.append(part)
        if not parts:
            return False
        shape = Part.makeCompound(parts) if len(parts) > 1 else parts[0]
    try:
        from pivy import coin
        verts, faces = shape.tessellate(0.5)
        if not faces:
            return False
        sep = coin.SoSeparator()
        sep.setName(name)
        offset = coin.SoPolygonOffset()
        offset.factor.setValue(1.0)
        offset.units.setValue(1.0)
        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(*color)
        mat.transparency.setValue(transparency)
        coords = coin.SoCoordinate3()
        coords.point.setValues(0, len(verts),
                               [(p.x, p.y, p.z) for p in verts])
        index = []
        for f in faces:
            index.extend([f[0], f[1], f[2], -1])
        faceset = coin.SoIndexedFaceSet()
        faceset.coordIndex.setValues(0, len(index), index)
        sep.addChild(offset)
        sep.addChild(mat)
        sep.addChild(coords)
        sep.addChild(faceset)
        vobj.RootNode.addChild(sep)
        return True
    except Exception:
        return False


def removeFaceHighlight(vobj, name=FACE_HIGHLIGHT):
    """Drop the named face overlay from a view provider, if present."""
    try:
        root = vobj.RootNode
        for child in list(root.getChildren() or []):
            if child.getName() == name:
                root.removeChild(child)
    except Exception:
        pass


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
        """Tree children of a wall root: its segments plus the doors and
        windows hosted on it (Hosts links plus Subtractions). Claiming
        the openings matters for more than tree tidiness — the tree eye
        toggle cascades to claimed children natively, and the wall root
        has no shape of its own, so without the claim the openings sit
        unattached and keep floating when the wall or its level is
        hidden."""
        obj = getattr(self, "Object", None)
        if obj is None:
            return []
        children = list(getattr(obj, "Group", None) or [])
        for opening in _hostedOpenings(obj):
            if opening not in children:
                children.append(opening)
        return children

    def onChanged(self, vobj, prop):
        """Cascade visibility to the claimed segments and the hosted
        openings: the wall root itself has no shape, so hiding it must
        hide the segments or the wall would still read as visible. Arch
        levels hide their direct children, and this closes the chain down
        to the segments — and through it to the doors/windows hosted via
        Hosts, whose tree parent is the wall root; without this they
        would stay visible when a level hides the wall, reading as a
        phantom storey. claimChildren alone can't do this: the root has
        no shape, so the GUI only routes the eye-toggle through here
        unreliably (hide may fire, show often doesn't) — the openings'
        own updateData hook below is what makes the follow deterministic
        in both directions."""
        if prop == "Visibility":
            obj = getattr(self, "Object", None) or vobj.Object
            for seg in all_segments(obj):
                if seg.ViewObject is not None:
                    seg.ViewObject.Visibility = vobj.Visibility
            for opening in _hostedOpenings(obj):
                if opening.ViewObject is not None:
                    opening.ViewObject.Visibility = vobj.Visibility

    def onDelete(self, vobj, subelements):
        """GUI deletes cascade: FreeCAD's own delete never removes
        children, so the wall's segments — and each nested segment's
        children — are removed here first, or they would be orphaned
        with dangling Wall links. The sketch is shared with other tools
        and never follows. Programmatic doc.removeObject bypasses the
        view provider and keeps the orphan behaviour."""
        obj = vobj.Object
        for seg in all_segments(obj):
            obj.Document.removeObject(seg.Name)
        return True

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

    def setEdit(self, vobj, mode=0):
        from archplus.tools.walls import gui
        obj = vobj.Object
        if is_segment(obj):
            gui.showSegmentPanel(obj)
        else:
            gui.showWallPanel(obj)
        return True

    def unsetEdit(self, vobj, mode=0):
        import FreeCADGui
        FreeCADGui.Control.closeDialog()
        return False


def makeWall(doc=None, sketch=None, name="Wall"):
    """Create the wall root plus one fallback child. Returns the root.

    The root keeps an identity Placement: it has no shape of its own, but
    FreeCAD parents claimed children's scene nodes under the root's node
    carrying the root transform — a non-identity placement here would lift
    every segment and hosted opening by that offset (a phantom extra
    storey). Position walls by their sketch placement instead."""
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
    seg.Fallback = True
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
    claims, except when it is the fallback segment — fallback claims are
    dynamic, so adding explicit claims to the target is enough (the
    fallback rebuilds without those edges on its own)."""
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
    if not source.Fallback:
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
    if not segment.Fallback:
        remaining = []
        for link, subs in getattr(segment, "Edges", None) or []:
            subs = tuple(s for s in subs if s not in subnames)
            if subs:
                remaining.append((link, subs))
        segment.Edges = remaining
    return new
