# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section-view checks. Run inside a FreeCAD GUI session.
#
# A section view draws library parts as their cached plan outline instead of
# their solid. The outline is an optimisation, never a wrong drawing: it is
# the shape's filled outer boundary, used when the solid's own drawing stays
# inside it, and this module is where that claim is tested - on a real part, a
# part the cut passes through, a part rotated off-plan, and against Draft's
# own view, which must keep drawing the walls identically.

import FreeCAD
import Part

from archplus.common import geometry as common_geometry
from archplus.freecad_tests import _harness as h


def _a_part():
    """One placed library part with a real shape."""
    from archplus.tools.partslib import object as pobj

    doc = FreeCAD.ActiveDocument
    obj = doc.addObject("Part::FeaturePython", "OutlinePart")
    pobj._LibraryPart(obj)
    obj.Shape = Part.makeBox(600, 400, 700)
    return obj


def _visible_edges(shape, direction=None):
    """The edges Draft's getProjected keeps, as comparable tuples."""
    import TechDraw

    direction = direction or FreeCAD.Vector(0, 0, 1)
    groups = TechDraw.projectEx(shape, direction)
    out = []
    for group in groups[0:5]:
        if group.isNull():
            continue
        for edge in group.Edges:
            a, b = edge.Vertexes[0].Point, edge.Vertexes[-1].Point
            out.append(tuple(sorted(((round(a.x, 3), round(a.y, 3), round(a.z, 3)),
                                     (round(b.x, 3), round(b.y, 3), round(b.z, 3))))))
    return set(out)


def _appearance(view):
    """The view's display properties, captured before it is removed.

    The converted view is a bare Part::FeaturePython with no view provider of
    its own, so a conversion has to carry these across or the drawing changes
    colour and line style in the 3D view. Captured, not compared afterwards:
    a removed view's handle is dead. A headless run has no ViewObject at all,
    which is why this is allowed to be empty."""
    vobj = getattr(view, "ViewObject", None)
    if vobj is None:
        return {}
    return {name: getattr(vobj, name)
            for name in ("LineColor", "LineWidth", "DrawStyle", "ShapeColor")
            if hasattr(vobj, name)}


def _walls_and_plane(doc):
    """A wall on a sketch, and a section plane through it - the smallest
    document whose section view has real geometry."""
    import Sketcher

    sketch = doc.addObject("Sketcher::SketchObject", "Sketch")
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(0, 0, 0),
                                        FreeCAD.Vector(4000, 0, 0)), False)
    sketch.addGeometry(Part.LineSegment(FreeCAD.Vector(4000, 0, 0),
                                        FreeCAD.Vector(4000, 3000, 0)), False)

    from archplus.tools.walls import object as wobj

    wall = wobj.makeWall(doc, sketch=sketch)
    plane = doc.addObject("App::FeaturePython", "Section")
    import ArchSectionPlane

    ArchSectionPlane._SectionPlane(plane)
    # The wall root has no shape of its own - its segments carry the geometry
    # - and Draft's gather does not descend into an ArchPlus wall root: the
    # root is not a Draft group, so `walls=True` does not make it one. A
    # section plane therefore has to reference the segments, which is what the
    # real documents do. Referencing the root alone leaves Draft's own view
    # raising IndexError on its empty material bucket, and this fixture would
    # compare two empty drawings.
    plane.Objects = list(wall.Group)
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    doc.recompute()
    return wall, plane


def _door_in(doc, wall, plane):
    """Host a door in `wall` and add it to the plane - a real opening.

    The spec's acceptance is about walls *and* openings: without a door the
    two drawings below would agree about a wall with no opening in it. Made
    from the repo's own door builders, and placed the way a real door sits -
    the sketch is drawn in the door's elevation plane, so the placement is
    what stands it up in the wall."""
    from archplus.tools.doors import gui as dgui
    from archplus.tools.doors import object as dobj

    spec = dict(operation="Single swing", panelStyle="Solid", width=900.0,
                height=2100.0, frameWidth=70.0, panelThk=45.0,
                frameDepth=100.0, swingSide="Left", swingDir="Inward",
                panelPos="Centered")
    dsketch, parts = dgui._makeDoorGeometry(spec)
    door = dobj.makeWindow(dsketch, 900.0, 2100.0, parts, name="SectionDoor")
    dsketch.Placement = FreeCAD.Placement(
        FreeCAD.Vector(1500, 0, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 90))
    door.Hosts = [wall]
    wall.Subtractions = [door]
    doc.recompute()
    plane.Objects = list(plane.Objects or []) + [door]
    doc.recompute()
    return door


def _part_view(doc, plane):
    """Add a placed library part to `plane`, and return it.

    The caller builds the views it compares; this only sets up the part the
    substitution is about."""
    from archplus.tools.partslib import object as pobj

    part = doc.addObject("Part::FeaturePython", "PlacedPart")
    pobj._LibraryPart(part)
    part.Shape = Part.makeBox(600, 400, 700)
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 0),
                                       FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [part]
    doc.recompute()
    return part


def _convert(doc, plane):
    """A Draft view to convert, plus a TechDraw view reading it."""
    draft = doc.addObject("Part::Part2DObjectPython", "ToConvert")
    import draftobjects.shape2dview as s2v

    s2v.Shape2DView(draft)
    draft.Base = plane
    draft.FuseArch = True
    draft.ProjectionMode = "Solid"
    draft.Placement = FreeCAD.Placement(FreeCAD.Vector(9000, 0, 0),
                                        FreeCAD.Rotation())
    doc.recompute()

    reader = doc.addObject("TechDraw::DrawProjGroupItem", "Reader")
    reader.Source = [draft]
    doc.recompute()
    return draft, reader


def run():
    doc = h.fresh_doc("ArchPlusSections")
    part = _a_part()

    outline = common_geometry.plan_outline(part.Shape)
    h.check("a box gets an outline", outline is not None)
    h.check("the outline is a 1mm slab", outline is not None
            and abs(outline.BoundBox.ZLength - 1.0) < 1e-6
            and outline.Volume > 0)
    # Counted on the *drawing*, not the raw shapes: the slab's own edges are
    # three times its silhouette's (top loop, bottom loop, 1mm verticals), so
    # a raw count would say nothing about what a view has to draw.
    h.check("the outline draws no more edges than the solid",
            len(_visible_edges(outline)) <= len(_visible_edges(part.Shape)))

    # The outline is the filled outer boundary: a loop nested inside it (a
    # smaller block on top of a bigger one) is dropped on purpose, not
    # refused. Reproducing it was measured bigger than the solid's own
    # drawing, which is the thing this feature exists to shrink.
    nested = Part.makeCompound([Part.makeBox(600, 400, 300),
                                Part.makeBox(300, 200, 300,
                                             FreeCAD.Vector(150, 100, 300))])
    nested_outline = common_geometry.plan_outline(nested)
    h.check("a nested loop is dropped, not refused",
            nested_outline is not None
            and len(_visible_edges(nested_outline)) == 4)

    # A projection too small to be a usable outline is refused.
    h.check("a hairline projection gets no outline",
            common_geometry.plan_outline(Part.makeBox(0.5, 0.5, 10)) is None)

    # A shape with two separate outlines: the outer wire is one of them, so
    # the other reaches outside the outline and it must be refused.
    two = Part.makeCompound([Part.makeBox(400, 400, 300),
                             Part.makeBox(400, 400, 300,
                                          FreeCAD.Vector(2000, 0, 0))])
    h.check("a two-outline shape gets no outline",
            common_geometry.plan_outline(two) is None)

    # An empty shape is refused rather than raising.
    h.check("an empty shape gets no outline",
            common_geometry.plan_outline(Part.Shape()) is None)

    from archplus.tools.partslib import object as pobj

    proxy = part.Proxy
    first = proxy.planOutline(part)
    h.check("a placed part answers with an outline", first is not None)
    h.check("the outline is cached, not rebuilt",
            proxy.planOutline(part) is first)
    before = proxy._outline_key
    part.Shape = Part.makeBox(900, 400, 700)
    h.check("a rebuild drops the cache", proxy.planOutline(part) is not first)
    h.check("the new outline is cached too",
            proxy.planOutline(part) is proxy.planOutline(part))
    h.check("the key followed the rebuild", proxy._outline_key != before)

    empty = pobj._LibraryPart.__new__(pobj._LibraryPart)
    h.check("a part with no shape answers None",
            empty.planOutline(Part.Shape()) is None)

    wall, plane = _walls_and_plane(doc)

    # The opening has to be real: without this the Draft comparison below
    # could pass while comparing two drawings that both have no opening in
    # them, and the acceptance criterion names walls *and* openings.
    wall_volume = sum(s.Shape.Volume for s in wall.Group)
    door = _door_in(doc, wall, plane)
    h.check("the door cuts an opening in the wall",
            sum(s.Shape.Volume for s in wall.Group) < wall_volume - 1.0)

    # Draft's own view, as the reference behaviour.
    reference = doc.addObject("Part::Part2DObjectPython", "Reference")
    import draftobjects.shape2dview as s2v

    s2v.Shape2DView(reference)
    reference.Base = plane
    reference.ProjectionMode = "Solid"
    doc.recompute()

    from archplus.tools.sections import object as sobj

    # Compared with the same settings set explicitly on both, rather than by
    # relying on the two objects defaulting alike.
    view = sobj.makeSectionView(doc, base=plane)
    view.FuseArch = True
    reference.FuseArch = True
    doc.recompute()

    h.check("the new view draws something", len(view.Shape.Edges) > 0)
    h.check("the new view draws exactly what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    h.check("the view keeps its own placement",
            view.Placement.Base == FreeCAD.Vector(0, 0, 0))

    # A fresh view must default to what a fresh Draft view defaults to, or
    # converting a view would change its drawing by the act of converting.
    fresh_reference = doc.addObject("Part::Part2DObjectPython", "FreshReference")
    s2v.Shape2DView(fresh_reference)
    fresh = sobj.makeSectionView(doc)
    h.check("a fresh view defaults like Draft's",
            fresh.FuseArch == fresh_reference.FuseArch
            and fresh.OnlySolids == fresh_reference.OnlySolids
            and fresh.VisibleOnly == fresh_reference.VisibleOnly
            and fresh.ProjectionMode == fresh_reference.ProjectionMode)

    # A clipping plane does not clip here either: Draft declares Clip on the
    # view itself (default False), so its Base.Clip branch is dead code.
    plane.Clip = True
    doc.recompute()
    h.check("a clipping plane draws what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    plane.Clip = False
    doc.recompute()

    # With the fuse off, still exactly what Draft draws with it off: this is
    # the only path that ever runs that branch on a converted view whose
    # FuseArch is false.
    view.FuseArch = False
    reference.FuseArch = False
    doc.recompute()
    h.check("with FuseArch off, still what Draft draws",
            _visible_edges(view.Shape) == _visible_edges(reference.Shape))
    view.FuseArch = True
    reference.FuseArch = True
    doc.recompute()

    # Emptying a plane that had geometry must leave an empty shape, not the
    # last one it drew.
    kept = list(plane.Objects or [])
    plane.Objects = []
    doc.recompute()
    h.check("emptying a plane leaves an empty shape",
            view.Shape.isNull() or len(view.Shape.Edges) == 0)
    plane.Objects = kept
    doc.recompute()

    # A plane with nothing to draw leaves an empty shape, not a stale one.
    import ArchSectionPlane

    empty_plane = doc.addObject("App::FeaturePython", "EmptyPlane")
    ArchSectionPlane._SectionPlane(empty_plane)
    bare = sobj.makeSectionView(doc, base=empty_plane)
    doc.recompute()
    h.check("an empty plane draws nothing", bare.Shape.isNull()
            or len(bare.Shape.Edges) == 0)

    # No base at all must not raise into the recompute.
    nothing = sobj.makeSectionView(doc, base=None)
    doc.recompute()
    h.check("no base draws nothing", nothing.Shape.isNull()
            or len(nothing.Shape.Edges) == 0)

    part = _part_view(doc, plane)
    view.PartOutlines = True
    doc.recompute()
    solid_view = sobj.makeSectionView(doc, base=plane)
    solid_view.PartOutlines = False
    # Same flags as `view` apart from the one under test, so the difference
    # between the two drawings is attributable to that one alone.
    solid_view.FuseArch = view.FuseArch
    doc.recompute()

    # With the part out of the plane, outlines on and off must draw the walls
    # identically: the substitution may only ever change the parts.
    with_part = list(plane.Objects or [])
    plane.Objects = [o for o in with_part if o is not part]
    doc.recompute()
    h.check("with the part out, outlines change nothing",
            _visible_edges(view.Shape) == _visible_edges(solid_view.Shape))
    plane.Objects = with_part
    doc.recompute()

    # Not "smaller": for a plain box the outline's silhouette is the same
    # rectangle the solid draws, so equal is the honest expectation here.
    # The real parts (many visible edges) are where the drawing shrinks, and
    # Task 7 measures that on the real document.
    h.check("outlines on: the drawing did not grow",
            len(view.Shape.Edges) <= len(solid_view.Shape.Edges))
    h.check("outlines on: the part's outline is what got drawn",
            _visible_edges(part.Proxy.planOutline(part))
            <= _visible_edges(view.Shape))

    # The outline is already in world coordinates, so the view must not place
    # it again: on a plane holding only this part, the drawing must sit
    # exactly on the part. Placing it twice would put it at (1000, 1000).
    alone = doc.addObject("App::FeaturePython", "PartOnlyPlane")
    ArchSectionPlane._SectionPlane(alone)
    alone.Objects = [part]
    alone.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    alone_view = sobj.makeSectionView(doc, base=alone)
    doc.recompute()
    box = alone_view.Shape.BoundBox
    h.check("the outline sits where the part is",
            abs(box.XMin - 500) < 1e-3 and abs(box.YMin - 500) < 1e-3
            and abs(box.XMax - 1100) < 1e-3 and abs(box.YMax - 900) < 1e-3)

    # A part with its base exactly on the plane is above the cut, so the cut
    # removes it from both drawings: this pins that no outline is added at the
    # boundary (a dropped tolerance would add the part's four edges).
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 1200),
                                       FreeCAD.Rotation())
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    doc.recompute()
    h.check("a part at the cut's own height adds no outline",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))

    # A part wholly above the cut: the cut removes its solid, so the drawing
    # has nothing of it. A footprint here would be a part the cut deleted -
    # this is the check that fails if only a *straddling* part is refused.
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 1500),
                                       FreeCAD.Rotation())
    doc.recompute()
    h.check("a part above the cut adds no footprint",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))

    # A part tilted about X keeps its solid too.
    plane.Placement.Base = FreeCAD.Vector(0, 0, 5000)
    part.Placement = FreeCAD.Placement(
        FreeCAD.Vector(500, 500, 0),
        FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 30))
    doc.recompute()
    h.check("a part rotated off plan keeps its solid",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))

    # A view that is not a plan (the plane tilted) keeps solids as well.
    plane.Placement.Base = FreeCAD.Vector(0, 0, 1200)
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 0),
                                       FreeCAD.Rotation())
    plane.Placement.Rotation = FreeCAD.Rotation(FreeCAD.Vector(1, 0, 0), 30)
    doc.recompute()
    h.check("an elevation keeps the solid",
            len(view.Shape.Edges) == len(solid_view.Shape.Edges))
    plane.Placement.Rotation = FreeCAD.Rotation()
    doc.recompute()

    # A part whose own drawing has two separate outlines gets no outline (the
    # waste-bin case), so the view falls back to its solid.
    bin_part = doc.addObject("Part::FeaturePython", "TwoOutlinePart")
    pobj._LibraryPart(bin_part)
    bin_part.Shape = Part.makeCompound([Part.makeBox(400, 400, 300),
                                        Part.makeBox(400, 400, 300,
                                                     FreeCAD.Vector(2000, 0, 0))])
    # Clear of the wall band: the check is that the fallback draws this part's
    # solid, and a part buried in the wall has its edges hidden, so they would
    # not be in the drawing at all.
    bin_part.Placement = FreeCAD.Placement(FreeCAD.Vector(3000, 2000, 0),
                                           FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [bin_part]
    doc.recompute()
    h.check("a part with no trustworthy outline keeps its solid",
            bin_part.Proxy.planOutline(bin_part) is None
            and bin_part.Proxy._outline_key is not None  # the None is cached
            and _visible_edges(bin_part.Shape) <= _visible_edges(view.Shape))

    # The substitution is only visible on a part whose outline differs from its
    # own drawing: a block on a bigger block draws 8 edges as a solid and 4 as
    # an outline (its outer boundary). This is the check that fails when the
    # substitution does not happen at all - a plain box draws the same
    # rectangle either way.
    nested_part = doc.addObject("Part::FeaturePython", "NestedPart")
    pobj._LibraryPart(nested_part)
    nested_part.Shape = Part.makeCompound([Part.makeBox(600, 400, 300),
                                           Part.makeBox(300, 200, 300,
                                                        FreeCAD.Vector(150, 100, 300))])
    nested_part.Placement = FreeCAD.Placement(FreeCAD.Vector(6000, 2000, 0),
                                              FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [nested_part]
    doc.recompute()
    nested_solid_view = sobj.makeSectionView(doc, base=plane)
    nested_solid_view.PartOutlines = False
    nested_solid_view.FuseArch = view.FuseArch
    doc.recompute()
    h.check("the substituted drawing is the outline, not the solid",
            len(view.Shape.Edges) < len(nested_solid_view.Shape.Edges))
    h.check("and what it drops is the nested loop",
            len(_visible_edges(nested_part.Shape) - _visible_edges(view.Shape))
            == 4)

    # A part the wall hides must stay hidden when its outline is what is
    # drawn. The outline rides in the same compound as the wall, so
    # hidden-line removal drops it exactly as it drops the solid: adding the
    # part must change neither drawing. This is the check that fails when the
    # slabs are projected separately and their edges appended, which draws
    # the part through the wall - the substituted view would gain the part's
    # outline edges while the solid view, whose part really is hidden, does
    # not.
    hidden = doc.addObject("Part::FeaturePython", "WalledIn")
    pobj._LibraryPart(hidden)
    hidden.Shape = Part.makeBox(600, 200, 700)
    # Inside the wall's 300mm band, and clear of the door's opening.
    hidden.Placement = FreeCAD.Placement(FreeCAD.Vector(2600, -100, 0),
                                         FreeCAD.Rotation())
    showing = _visible_edges(view.Shape)
    solid_showing = _visible_edges(solid_view.Shape)
    plane.Objects = list(plane.Objects or []) + [hidden]
    doc.recompute()
    h.check("a part the wall hides draws nothing in either view",
            hidden.Proxy.planOutline(hidden) is not None
            and _visible_edges(view.Shape) == showing
            and _visible_edges(solid_view.Shape) == solid_showing,
            detail="outlines: %d -> %d edges, solid: %d -> %d"
                   % (len(showing), len(_visible_edges(view.Shape)),
                      len(solid_showing), len(_visible_edges(solid_view.Shape))))

    # A plane with a Depth cuts a band, not everything below it: the cut
    # removes what is under `plane_z - depth` too, so a part down there is in
    # neither drawing and must not take an outline. With Depth set every part
    # of this plane is under the floor, so the substituted view draws no
    # footprint at all and the two drawings agree - compared as drawings, not
    # as edge counts, because a footprint kept here and a footprint dropped
    # there would cancel out in a count.
    deeper = doc.addObject("Part::FeaturePython", "UnderTheFloor")
    pobj._LibraryPart(deeper)
    deeper.Shape = Part.makeBox(600, 400, 150)
    deeper.Placement = FreeCAD.Placement(FreeCAD.Vector(6000, -1000, 0),
                                         FreeCAD.Rotation())
    plane.Objects = list(plane.Objects or []) + [deeper]
    plane.Depth = 1000      # the 1200 plane now keeps only 200..1200
    doc.recompute()
    h.check("a part under the depth band adds no outline",
            deeper.Proxy.planOutline(deeper) is not None
            and _visible_edges(view.Shape) == _visible_edges(solid_view.Shape),
            detail="outlines drew %d edges, solids %d; the part's outline is %s"
                   % (len(view.Shape.Edges), len(solid_view.Shape.Edges),
                      deeper.Proxy.planOutline(deeper) is not None))
    plane.Depth = 0
    doc.recompute()

    # Turning the flag off draws the solid again.
    part.Placement = FreeCAD.Placement(FreeCAD.Vector(500, 500, 0),
                                       FreeCAD.Rotation())
    view.PartOutlines = False
    doc.recompute()
    h.check("PartOutlines off draws the solid again",
            _visible_edges(view.Shape) == _visible_edges(solid_view.Shape))

    draft, reader = _convert(doc, plane)
    old_bbox = draft.Shape.BoundBox
    # Given an appearance of its own, so the copy below has something to
    # carry across that Part's default does not already give.
    if draft.ViewObject is not None:
        draft.ViewObject.LineColor = (0.9, 0.1, 0.1)
        draft.ViewObject.LineWidth = 3.0
        draft.ViewObject.ShapeColor = (0.1, 0.2, 0.9)
        draft.ViewObject.DrawStyle = "Dashed"
    appearance = _appearance(draft)

    from archplus.tools.sections import gui as sgu

    h.check("the conversion reports success", sgu.convertSectionView(draft))
    h.check("the old view is gone", doc.getObject("ToConvert") is None)
    converted = next((o for o in doc.Objects if o.Label == "ToConvert"), None)
    # Found by label on purpose: the converted view keeps the label of the
    # view it replaced, which is what makes it read as the same view.
    h.check("the converted view keeps the label", converted is not None)
    h.check("the reader points at the new view",
            converted is not None and converted in list(reader.Source or []))
    h.check("the placement came across",
            converted is not None
            and abs(converted.Placement.Base.x - 9000) < 1e-6)
    h.check("the drawing did not jump",
            converted is not None
            and abs(converted.Shape.BoundBox.XMin - old_bbox.XMin) < 1e-3)
    h.check("the converted view keeps the Draft view's appearance",
            bool(appearance) and converted is not None
            and all(getattr(converted.ViewObject, name) == value
                    for name, value in appearance.items()))

    # A frozen view stays frozen, and keeps a drawing: the fixture draws
    # first, so a conversion that froze the view before it ever built would
    # come out blank and fail the second check.
    frozen = doc.addObject("Part::Part2DObjectPython", "Frozen")
    s2v.Shape2DView(frozen)
    frozen.Base = plane
    doc.recompute()
    frozen.AutoUpdate = False
    doc.recompute()
    h.check("a frozen view converts", sgu.convertSectionView(frozen))
    converted_frozen = next((o for o in doc.Objects if o.Label == "Frozen"),
                            None)
    h.check("and stays frozen",
            converted_frozen is not None and not converted_frozen.AutoUpdate)
    h.check("with the drawing it was frozen with",
            converted_frozen is not None
            and len(converted_frozen.Shape.Edges) > 0)

    # A view using a setting the new object does not reproduce is refused.
    other = doc.addObject("Part::Part2DObjectPython", "HiddenLines")
    s2v.Shape2DView(other)
    other.Base = plane
    other.HiddenLines = True
    doc.recompute()
    h.check("an unsupported setting is refused",
            sgu.convertSectionView(other) is False)
    h.check("the refused view is still there", doc.getObject("HiddenLines") is not None)

    # A view that is not on a section plane is refused too: this view only
    # gathers a section plane's objects, so converting one would draw blank.
    base_less = doc.addObject("Part::Part2DObjectPython", "NoBase")
    s2v.Shape2DView(base_less)
    doc.recompute()
    h.check("a view with no section plane is refused",
            sgu.convertSectionView(base_less) is False)
    h.check("the base-less view is still there",
            doc.getObject("NoBase") is not None)

    # A default Draft view must not be refused: every entry in the refusal
    # table is a value that means "not used", so a view nobody has touched
    # converts.
    h.check("a default Draft view is not refused",
            sgu.unsupported_settings(reference) == [])

    # And neither must a view with InPlace off. All four of the user's real
    # views carry InPlace = False, and it is inert in Solid mode - the only
    # mode this view has - so refusing it would refuse every view there is.
    off_place = doc.addObject("Part::Part2DObjectPython", "NotInPlace")
    s2v.Shape2DView(off_place)
    off_place.Base = plane
    off_place.InPlace = False
    doc.recompute()
    h.check("a view with InPlace off converts",
            sgu.convertSectionView(off_place) is True)

    # A TechDraw view that cannot be re-pointed aborts the conversion: the
    # old view has to still be there afterwards. `Immutable` is the one
    # property status that refuses assignment from Python, which is how a
    # reader that refuses is staged.
    stubborn = doc.addObject("Part::Part2DObjectPython", "Stubborn")
    s2v.Shape2DView(stubborn)
    stubborn.Base = plane
    doc.recompute()
    blocker = doc.addObject("Part::FeaturePython", "StubbornReader")
    blocker.addProperty("App::PropertyLinkList", "Source", "Checks")
    blocker.Source = [stubborn]
    blocker.setPropertyStatus("Source", "Immutable")
    doc.recompute()
    h.check("a view whose reader refuses re-pointing is not converted",
            sgu.convertSectionView(stubborn) is False)
    h.check("the original view survives the abort",
            doc.getObject("Stubborn") is not None)

    # A view that is not a Draft section view at all is refused, by name.
    plain = doc.addObject("Part::Feature", "PlainFeature")
    h.check("a plain feature is refused",
            sgu.convertSectionView(plain) is False)

    FreeCAD.closeDocument(doc.Name)
    return h.failures()
