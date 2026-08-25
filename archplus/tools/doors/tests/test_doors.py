# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the Doors tool: geometry generation and the edit round-trip.

from archplus.tools.doors import gui as dg
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
    )
    spec.update(over)
    return spec


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


# --- edit round-trip ------------------------------------------------------
def _panel(obj):
    p = object.__new__(dg.DoorsPlusTaskPanel)
    p.obj, p.editing, p._building, p._sketch = obj, True, True, None
    p.operation = FakeCombo(); p.panelStyle = FakeCombo()
    p.width = FakeNum(); p.height = FakeNum()
    p.frameWidth = FakeNum(); p.frameDepth = FakeNum(); p.panelThk = FakeNum()
    p.swingSide = FakeCombo(); p.swingDir = FakeCombo(); p.panelPos = FakeCombo()
    p.sill = FakeNum(); p.opening = FakeNum()
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
