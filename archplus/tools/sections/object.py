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

        # Draft's getProjected: the visible edge groups of the projection.
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
