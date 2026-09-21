# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Door hardware, the window in a leaf, and the door's part colours. Run inside
# a FreeCAD GUI session; everything here is measured from the real kernel.
#
# A door leaf carries a knob (a solid of revolution, see object.makeKnobShape)
# and the frame, the leaf and the knob are drawn in three greys that have to
# read apart from each other. The knob is the part that has to travel with its
# leaf while the frame stands still, so it is measured against the leaf it
# hangs on rather than by its own coordinates.

from archplus.freecad_tests import _harness as h

import FreeCAD

from archplus.tools.doors import gui as dg
from archplus.tools.doors import object as do

SPEC = dict(operation="Single swing", panelStyle="Solid", width=900.0,
            height=2100.0, frameWidth=70.0, panelThk=45.0, frameDepth=100.0,
            swingSide="Left", swingDir="Inward", panelPos="Centered",
            knobHeight=1050.0, windowWidth=400.0, windowHeight=900.0,
            windowSill=900.0)


def _door(spec=None, name="Door"):
    """Build a door from `spec` (the defaults above, overridden by `spec`)."""
    spec = dict(SPEC, **(spec or {}))
    doc = FreeCAD.ActiveDocument
    sketch, parts = dg._makeDoorGeometry(spec)
    doc.recompute()
    obj = do.makeWindow(sketch, spec["width"], spec["height"], parts, name=name)
    obj.Frame = spec["panelThk"]
    obj.Offset = 0
    doc.recompute()
    return obj, parts


def _names(parts):
    return [parts[i] for i in range(0, len(parts), 5)]


def _solids(obj, parts, label):
    """{part name: solid}, one solid per part.

    That mapping is what colorize colours by, so a part building more than one
    solid (a knob left as a compound, say) would not merely mis-colour itself:
    it would push every following part's colour down one."""
    names = _names(parts)
    h.check("%s: each part builds exactly one solid" % label,
            len(obj.Shape.Solids) == len(names),
            detail="%d solids for %d parts" % (len(obj.Shape.Solids), len(names)))
    return dict(zip(names, obj.Shape.Solids))


def _solid_colors(obj):
    """The shape appearance of each solid, as (RGB, transparency)."""
    out = []
    face = 0
    for solid in obj.Shape.Solids:
        mat = obj.ViewObject.ShapeAppearance[face]
        out.append((tuple(mat.DiffuseColor[:3]), mat.Transparency))
        face += len(solid.Faces)
    return out


def _color_of(obj, parts, name):
    """(RGB, transparency) of the solid that part `name` builds."""
    colors = _solid_colors(obj)
    return colors[_names(parts).index(name)]


def _luminance(rgb):
    return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]


def _knob_checks(label, spec, leaf_name):
    obj, parts = _door(spec, name=label.replace(" ", "") + "Door")
    spec = dict(SPEC, **spec)
    solids = _solids(obj, parts, label)
    knob, leaf = solids["Knob"], solids[leaf_name]
    kb, lb = knob.BoundBox, leaf.BoundBox
    centre = knob.CenterOfMass

    h.check("%s: the knob sits on the leaf, clear of its edges" % label,
            lb.XMin < kb.XMin and kb.XMax < lb.XMax
            and lb.YMin < kb.YMin and kb.YMax < lb.YMax,
            detail="knob %s on leaf %s" % (kb, lb))
    h.check("%s: the knob is at the height it was asked for" % label,
            abs(centre.y - spec["knobHeight"]) < 1.0,
            detail="centre y=%.1f, asked for %.1f" % (centre.y, spec["knobHeight"]))
    # ... on the leaf's free edge: the hinge is on the left, so the knob is at
    # the right, one KNOB_FROM_EDGE in from where the leaf ends.
    want = spec["width"] - spec["frameWidth"] - dg.KNOB_FROM_EDGE
    h.check("%s: the knob is on the leaf's free edge, not its hinge" % label,
            abs(centre.x - want) < 1.0,
            detail="centre x=%.1f, expected %.1f" % (centre.x, want))
    # It grips the leaf from both sides: a knob is the one part of a door that
    # reaches out of the wall.
    front = kb.ZMax - lb.ZMax
    back = lb.ZMin - kb.ZMin
    h.check("%s: the knob protrudes from both faces of the leaf" % label,
            front > 2 * dg.KNOB_RADIUS and abs(front - back) < 1.0,
            detail="out the front %.1f, out the back %.1f" % (front, back))

    # Opening the door must carry the knob with the leaf. Measured as the
    # distance between the two centres, which a rigid motion preserves and a
    # knob left behind does not.
    closed_knob, closed_leaf, volume = (knob.CenterOfMass, leaf.CenterOfMass,
                                        knob.Volume)
    obj.Opening = 100
    doc = obj.Document
    doc.recompute()
    solids = _solids(obj, parts, label + " open")
    knob, leaf = solids["Knob"], solids[leaf_name]
    closed_gap = (closed_knob - closed_leaf).Length
    open_gap = (knob.CenterOfMass - leaf.CenterOfMass).Length
    moved = (knob.CenterOfMass - closed_knob).Length
    h.check("%s: the knob swings with its leaf" % label,
            abs(closed_gap - open_gap) < 0.01 and moved > spec["panelThk"]
            and abs(knob.Volume - volume) < 1.0,
            detail="knob-to-leaf %.3f closed, %.3f open; knob moved %.1f mm"
            % (closed_gap, open_gap, moved))


def _color_checks():
    obj, parts = _door(name="ColorDoor")
    frame, _ = _color_of(obj, parts, "OuterFrame")
    leaf, _ = _color_of(obj, parts, "Door")
    knob, _ = _color_of(obj, parts, "Knob")
    h.check("the door's frame, leaf and knob are three different greys",
            len({frame, leaf, knob}) == 3
            and all(max(c) - min(c) < 0.05 for c in (frame, leaf, knob)),
            detail="frame %s leaf %s knob %s" % (frame, leaf, knob))
    h.check("the frame is lighter and the knob darker than the leaf",
            _luminance(frame) > _luminance(leaf) + 0.2
            and _luminance(leaf) > _luminance(knob) + 0.2,
            detail="luminance frame %.3f leaf %.3f knob %.3f"
            % (_luminance(frame), _luminance(leaf), _luminance(knob)))

    # A glazed leaf is the leaf as well: it must not take the frame's grey, or
    # a door with a window in it reads as one flat colour.
    glazed, gparts = _door({"panelStyle": "Glass (window)"}, name="GlazedColor")
    gframe, _ = _color_of(glazed, gparts, "OuterFrame")
    gleaf, _ = _color_of(glazed, gparts, "InnerFrame")
    h.check("a glazed leaf still reads apart from the frame",
            abs(_luminance(gframe) - _luminance(gleaf)) > 0.2,
            detail="frame %s leaf %s" % (gframe, gleaf))


def _window_checks():
    obj, parts = _door({"panelStyle": "Glass (window)"}, name="WindowDoor")
    solids = _solids(obj, parts, "window door")
    leaf, glass = solids["InnerFrame"], solids["InnerGlass"]
    lb, gb = leaf.BoundBox, glass.BoundBox
    h.check("the window is cut into the leaf, a frame left all round",
            gb.XMin > lb.XMin + 1 and gb.XMax < lb.XMax - 1
            and gb.YMin > lb.YMin + 1 and gb.YMax < lb.YMax - 1,
            detail="window %s in leaf %s" % (gb, lb))
    h.check("the window is where it was asked for (400 x 900, 900 up)",
            abs(gb.XLength - 400.0) < 1.0 and abs(gb.YLength - 900.0) < 1.0
            and abs(gb.YMin - 900.0) < 1.0,
            detail="%s" % gb)

    # The leaf is solid where there is no window and open where there is one:
    # measured on the leaf's centre line, below the window and in it. What is
    # in the window is glass, not leaf.
    mid_z = (lb.ZMin + lb.ZMax) / 2.0
    centre_x = (lb.XMin + lb.XMax) / 2.0
    below = FreeCAD.Vector(centre_x, 450.0, mid_z)
    in_window = FreeCAD.Vector(centre_x, gb.YMin + gb.YLength / 2.0, mid_z)
    solid_below = leaf.isInside(below, 1e-6, False)
    solid_in_window = leaf.isInside(in_window, 1e-6, False)
    h.check("the leaf is solid below the window and open in it",
            solid_below and not solid_in_window,
            detail="below %s, in the window %s" % (solid_below, solid_in_window))
    _, transparency = _color_of(obj, parts, "InnerGlass")
    h.check("the window is glazed with transparent glass",
            glass.Volume > 0 and transparency > 0.5,
            detail="volume %.1f, transparency %.2f" % (glass.Volume, transparency))

    bare, bparts = _door({"operation": "Opening only"}, name="BareDoor")
    h.check("an opening with no leaf has nothing to hang a knob on",
            "Knob" not in _names(bparts),
            detail="parts %r" % _names(bparts))


def run():
    h.fresh_doc()
    _knob_checks("single swing", {}, "Door")
    _knob_checks("sliding door", {"operation": "Sliding (single)"}, "Door")
    _knob_checks("glazed leaf", {"panelStyle": "Glass (window)"}, "InnerFrame")
    _color_checks()
    _window_checks()
    return h.failures()
