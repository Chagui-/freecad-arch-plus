# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the Doors tool: geometry generation and the edit round-trip.

import types

import FreeCAD
import Part

from archplus.tools.doors import gui as dg
from archplus.tools.walls import object as walls_object
from conftest import FakeObj, FakeCombo, FakeNum, FakeCheck, quantity, fake_base


def _groups(flat):
    return {flat[i]: flat[i + 2] for i in range(0, len(flat), 5)}


def _modes(flat):
    out = []
    for wires in _groups(flat).values():
        for tok in wires.split(","):
            if tok.startswith("Mode"):
                out.append(int(tok[4:]))
    return out


def _spec(**over):
    spec = dict(
        operation="Single swing", panelStyle="Solid",
        width=900.0, height=2100.0, frameWidth=70.0,
        panelThk=45.0, frameDepth=100.0,
        swingSide="Left", swingDir="Inward", panelPos="Centered",
        knobHeight=1050.0, windowWidth=400.0, windowHeight=900.0,
        windowSill=900.0,
    )
    spec.update(over)
    return spec


def _parts(flat):
    return [flat[i] for i in range(0, len(flat), 5)]


def _types(flat):
    return [flat[i + 1] for i in range(0, len(flat), 5)]


def _rects(sketch):
    """The rectangles a sketcher-drawn sketch holds, as (x0, y0, x1, y1).

    A rectangle arrives as four line segments and a circle as one geometry, so
    the segments group in fours."""
    segs = [g for g in sketch.Geometry if g.TypeId == "Part::GeomLineSegment"]
    out = []
    for i in range(0, len(segs), 4):
        points = [s.p1 for s in segs[i:i + 4]]
        xs = [p.x for p in points]
        ys = [p.y for p in points]
        out.append((min(xs), min(ys), max(xs), max(ys)))
    return out


def _circles(sketch):
    return [g for g in sketch.Geometry if g.TypeId == "Part::GeomCircle"]


def _face(x, y, z):
    """A picked face standing in for a plane at one point — the helper only
    measures distance to it."""
    return types.SimpleNamespace(point=(x, y, z))


class _Vertex:
    def __init__(self, point):
        self.point = (point.x, point.y, point.z)

    def distToShape(self, face):
        dist = sum((a - b) ** 2 for a, b in zip(self.point, face.point)) ** 0.5
        return (dist, [], [])


def _host(*faces):
    return types.SimpleNamespace(
        Shape=types.SimpleNamespace(Faces=[_face(*f) for f in faces]))


def test_placement_point_keeps_a_snap_that_landed_on_the_picked_face(monkeypatch):
    monkeypatch.setattr(Part, "Vertex", _Vertex, raising=False)
    host = _host((0, 0, 0), (150, 150, 1200))
    on_face = FreeCAD.Vector(150, 150, 1200)
    info = {"x": 150.0, "y": 150.0, "z": 1200.0}
    assert walls_object.placementPoint(on_face, (host, 1), info) is on_face


def test_placement_point_falls_back_to_the_pick_when_the_snap_missed(monkeypatch):
    # Draft's Snapper hands over a working-plane point when it cannot snap to
    # the picked object. On an ArchPlus wall it never can: the pick names the
    # shapeless root (or a segment with a cross-child index), so the plane
    # point is metres away and the door used to land on the floor beside it.
    monkeypatch.setattr(Part, "Vertex", _Vertex, raising=False)
    host = _host((150, 150, 1200))
    on_plane = FreeCAD.Vector(5000, 5000, 0)
    info = {"x": 150.0, "y": 150.0, "z": 1200.0}
    picked = walls_object.placementPoint(on_plane, (host, 0), info)
    assert (picked.x, picked.y, picked.z) == (150.0, 150.0, 1200.0)
    # Without a picked face there is nothing to prefer it to.
    assert walls_object.placementPoint(on_plane, None, info) is on_plane


# --- geometry -------------------------------------------------------------
def test_single_swing_is_hinged_arc():
    _, flat = dg._makeDoorGeometry(_spec(operation="Single swing"))
    txt = " ".join(_groups(flat).values())
    assert "Edge" in txt
    assert all(m in (1, 2) for m in _modes(flat)) and _modes(flat)


def test_sliding_door_slides_not_swings():
    _, flat = dg._makeDoorGeometry(_spec(operation="Sliding (single)"))
    modes = _modes(flat)
    assert modes and all(m in (9, 10) for m in modes)


def test_opening_only_has_no_leaf():
    _, flat = dg._makeDoorGeometry(_spec(operation="Opening only"))
    assert not _modes(flat)               # a bare hole, no operable leaf


def test_glass_inherits_its_frames_transform():
    # Glass panels deliberately carry no Edge/Mode: they inherit the moving
    # frame immediately before them (the native FreeCAD convention), so
    # sliding glass travels exactly with its leaf.
    cases = {
        ("Single swing", "Glass (full)"): {"InnerGlass": "Wire3"},
        ("Sliding (single)", "Glass (full)"): {"InnerGlass": "Wire3"},
        ("Double swing", "Glass (full)"): {"LeftGlass": "Wire3",
                                           "RightGlass": "Wire5"},
    }
    for (op, style), glasses in cases.items():
        _, flat = dg._makeDoorGeometry(_spec(operation=op, panelStyle=style))
        g = _groups(flat)
        for name, wires in glasses.items():
            assert g[name] == wires, "%s/%s: %s = %r" % (op, style, name, g[name])


def test_glass_directly_follows_its_frame():
    # The inheritance only holds while the glass entry immediately follows
    # the moving frame it inherits from; a fixed part inserted between them
    # would wrongly inherit the same transform.
    cases = {
        ("Single swing", "Glass (full)"): [("InnerFrame", "InnerGlass")],
        ("Sliding (single)", "Glass (full)"): [("InnerFrame", "InnerGlass")],
        ("Double swing", "Glass (full)"): [("LeftFrame", "LeftGlass"),
                                           ("RightFrame", "RightGlass")],
    }
    for (op, style), pairs in cases.items():
        _, flat = dg._makeDoorGeometry(_spec(operation=op, panelStyle=style))
        names = [flat[i] for i in range(0, len(flat), 5)]
        for frame, glass in pairs:
            assert names.index(glass) == names.index(frame) + 1, \
                "%s/%s: %s must immediately follow %s (order: %r)" \
                % (op, style, glass, frame, names)


# --- knobs ----------------------------------------------------------------
def test_every_leaf_gets_a_knob_that_follows_it():
    # A knob carries no Edge/Mode of its own: it inherits its leaf's opening
    # transform, exactly like the glass does, which only holds while it is the
    # entry right after that leaf. "Opening only" has no leaf, so no knob.
    cases = {
        "Single swing": ["OuterFrame", "Door", "Knob"],
        "Sliding (single)": ["OuterFrame", "Door", "Knob"],
        "Double swing": ["OuterFrame", "LeftDoor", "LeftKnob",
                         "RightDoor", "RightKnob"],
        "Opening only": ["OuterFrame"],
    }
    for op, expected in cases.items():
        _, flat = dg._makeDoorGeometry(_spec(operation=op))
        assert _parts(flat) == expected, "%s: %r" % (op, _parts(flat))
    _, flat = dg._makeDoorGeometry(_spec(panelStyle="Glass (window)"))
    # ... and on a glazed leaf it still follows the moving entry of that leaf.
    assert _parts(flat) == ["OuterFrame", "InnerFrame", "InnerGlass", "Knob"]


def test_a_knob_is_typed_as_hardware_with_no_movement_of_its_own():
    # The part type is the builder's interface to the object: it decides that
    # this part is revolved into a knob and coloured as hardware. A knob must
    # carry no Edge/Mode either - it inherits its leaf's opening transform, so
    # giving it one of its own would leave it behind when the leaf moves. The
    # three types are what keeps the frame, the leaf and the knob in three
    # different greys (object.DOOR_PART_COLORS).
    _, flat = dg._makeDoorGeometry(_spec())
    assert _types(flat) == ["Frame", "Solid panel", "Knob"]
    wires = flat[2 * 5 + 2]
    assert "Edge" not in wires and "Mode" not in wires, wires


def test_knob_circles_place_one_knob_per_leaf_on_its_free_edge():
    # The knob's circle is what places and sizes it, so there is one per leaf,
    # on the edge opposite the hinge, at the height the spec asks for.
    sketch, _ = dg._makeDoorGeometry(
        _spec(operation="Double swing", knobHeight=1000.0))
    circles = _circles(sketch)
    assert len(circles) == 2
    for c in circles:
        assert c.radius == dg.KNOB_RADIUS
        assert (c.center.y, c.center.z) == (1000.0, 0.0)
    # The leaves meet in the middle, so their knobs approach it from either
    # side rather than sitting on top of each other.
    left, right = sorted(c.center.x for c in circles)
    assert left < 450.0 < right and right - left > 2 * dg.KNOB_RADIUS

    # A single leaf's knob hangs on the free edge, so the hinge side moves it.
    for side, below in (("Left", False), ("Right", True)):
        sketch, _ = dg._makeDoorGeometry(
            _spec(operation="Single swing", swingSide=side))
        x = _circles(sketch)[0].center.x
        assert (x < 450.0) == below, "hinge %s put the knob at %g" % (side, x)


# --- a door with a window in it -------------------------------------------
def test_window_style_cuts_a_lite_in_the_leaf():
    sketch, flat = dg._makeDoorGeometry(
        _spec(panelStyle="Glass (window)"))
    assert _parts(flat) == ["OuterFrame", "InnerFrame", "InnerGlass", "Knob"]
    # The leaf runs from the jamb to the jamb, 900 wide with 70 jambs; the
    # window is centred on it, 400 x 900, sitting 900 above the door's base.
    outline = (77.0, 0.0, 823.0, 2023.0)          # leaf, inset by `tol` = jw/10
    lite = (250.0, 900.0, 650.0, 1800.0)
    rects = _rects(sketch)
    assert outline in rects and lite in rects


def test_an_over_large_window_stays_inside_the_leaf():
    # A window bigger than the leaf must not cut the leaf in two: it is
    # clamped to leave a frame (the jamb width) on every side, and one asked
    # to sit higher than that allows drops until it fits.
    sketch, _ = dg._makeDoorGeometry(
        _spec(panelStyle="Glass (window)", windowWidth=5000.0,
              windowHeight=5000.0, windowSill=4000.0))
    # The leaf's own outline is 77..823 x 0..2023; the lite leaves 70 (jw) of
    # frame to either side and at the top.
    assert (140.0, 70.0, 760.0, 1960.0) in _rects(sketch)


# --- edit round-trip ------------------------------------------------------
def _panel(obj):
    p = object.__new__(dg.DoorsPlusTaskPanel)
    p.obj, p.editing, p._building, p._sketch = obj, True, True, None
    p.operation = FakeCombo(); p.panelStyle = FakeCombo()
    p.width = FakeNum(); p.height = FakeNum()
    p.frameWidth = FakeNum(); p.frameDepth = FakeNum(); p.panelThk = FakeNum()
    p.swingSide = FakeCombo(); p.swingDir = FakeCombo(); p.panelPos = FakeCombo()
    p.sill = FakeNum(); p.opening = FakeNum()
    p.knobHeight = FakeNum()
    p.windowWidth = FakeNum(); p.windowHeight = FakeNum(); p.windowSill = FakeNum()
    p.symbolPlan = FakeCheck(); p.symbolElev = FakeCheck()
    return p


def _configured_obj(spec):
    obj = FakeObj()
    obj.Base = fake_base(z=0.0)
    obj.Hosts = []
    obj.Width = quantity(spec["width"])
    obj.Height = quantity(spec["height"])
    obj.Frame = quantity(spec["panelThk"])
    obj.Opening = 0
    obj.SymbolPlan = True
    obj.SymbolElevation = False
    dg.storeSpec(obj, spec)
    return obj


def test_editing_restores_every_field():
    spec = _spec(operation="Double swing", panelStyle="Glass (full)",
                 width=1600.0, height=2200.0, frameWidth=90.0, panelThk=55.0,
                 frameDepth=250.0, swingSide="Right", swingDir="Outward",
                 panelPos="Back")
    p = _panel(_configured_obj(spec))
    p._loadFromObject()
    assert p._collect() == spec


def test_editing_one_field_leaves_the_rest_unchanged():
    spec = _spec(operation="Double swing", panelStyle="Glass (full)",
                 width=1600.0, height=2200.0, frameWidth=90.0, panelThk=55.0,
                 frameDepth=250.0, swingSide="Right", swingDir="Outward",
                 panelPos="Back")
    p = _panel(_configured_obj(spec))
    p._loadFromObject()
    p.frameDepth.setValue(300.0)          # user edits only the frame depth
    assert p._collect() == dict(spec, frameDepth=300.0)


def test_legacy_object_without_spec_falls_back():
    obj = FakeObj()
    obj.Base = fake_base(z=0.0)
    obj.Hosts = []
    obj.Width = quantity(900.0); obj.Height = quantity(2100.0)
    obj.Frame = quantity(45.0); obj.Opening = 0
    p = _panel(obj)
    p._loadFromObject()                   # must not raise without a stored spec
    assert p._collect()["width"] == 900.0


def test_rebuild_hides_the_new_base_sketch():
    # _apply swaps a freshly created sketch in as Base. A new sketch is
    # visible by default, so the panel must hide it — otherwise every live
    # update (and the final accept) leaves the construction sketch visible
    # in the 3D view.
    spec = _spec(operation="Single swing")
    obj = _configured_obj(spec)
    p = _panel(obj)
    p._sketch = fake_base(z=0.0)
    p._apply()
    assert obj.Base.ViewObject.Visibility is False
