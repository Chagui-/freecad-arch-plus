# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the Windows tool: WindowParts geometry generation and the
# load/collect round-trip used when editing.

import types

import windowsplus_gui as wg
from conftest import FakeObj, FakeCombo, FakeNum, FakeCheck, quantity, fake_base


def _groups(flat):
    """Split the flat WindowParts list into {name: wire-string}."""
    return {flat[i]: flat[i + 2] for i in range(0, len(flat), 5)}


def _modes(flat):
    """Opening-mode integers across all parts (a part may carry none)."""
    out = []
    for wires in _groups(flat).values():
        for tok in wires.split(","):
            if tok.startswith("Mode"):
                out.append(int(tok[4:]))
    return out


def _spec(**over):
    spec = dict(
        shape="Rectangular", operation="Fixed",
        width=1200.0, height=1200.0, frameWidth=50.0,
        sashThk=45.0, frameDepth=100.0,
        swingSide="Left", swingDir="Inward", panelPos="Front",
    )
    spec.update(over)
    return spec


# --- geometry -------------------------------------------------------------
def test_fixed_is_frame_plus_glass():
    _, flat = wg._makeWindowGeometry(_spec(operation="Fixed"))
    g = _groups(flat)
    assert set(g) == {"OuterFrame", "Glass"}
    assert g["Glass"] == "Wire1"          # glass fills the inner opening
    assert not _modes(flat)               # fixed: nothing operable


def test_single_casement_is_hinged_arc():
    _, flat = wg._makeWindowGeometry(_spec(operation="Single casement"))
    g = _groups(flat)
    assert set(g) == {"OuterFrame", "Sash", "Glass"}
    assert "Edge" in g["Sash"]            # hinged about an edge
    assert all(m in (1, 2) for m in _modes(flat))   # arc (swing) modes


def test_single_sliding_slides_not_swings():
    # A sliding window must use a slide mode (9/10), not an arc mode (1/2).
    _, flat = wg._makeWindowGeometry(_spec(operation="Single sliding"))
    modes = _modes(flat)
    assert modes and all(m in (9, 10) for m in modes)


def test_double_casement_has_two_sashes():
    _, flat = wg._makeWindowGeometry(_spec(operation="Double casement"))
    g = _groups(flat)
    assert {"LeftSash", "RightSash"} <= set(g)
    assert all(m in (1, 2) for m in _modes(flat))


def test_swing_side_flips_the_mode():
    _, left = wg._makeWindowGeometry(_spec(operation="Single casement", swingSide="Left"))
    _, right = wg._makeWindowGeometry(_spec(operation="Single casement", swingSide="Right"))
    assert _modes(left) != _modes(right)


def test_round_is_two_concentric_circles():
    sketch, flat = wg._makeWindowGeometry(_spec(shape="Round"))
    g = _groups(flat)
    assert set(g) == {"OuterFrame", "Glass"}
    assert g["OuterFrame"] == "Wire0,Wire1"     # ring = outer minus inner
    circles = [geo for geo in sketch.Geometry if geo.TypeId == "Part::GeomCircle"]
    assert len(circles) == 2
    assert not _modes(flat)                       # round windows are fixed


# --- edit round-trip ------------------------------------------------------
def _panel(obj):
    """A WindowsPlusTaskPanel wired with fake widgets, skipping Qt setup, so the
    real _loadFromObject()/_collect() can run."""
    p = object.__new__(wg.WindowsPlusTaskPanel)
    p.obj, p.editing, p._building, p._sketch = obj, True, True, None
    p.shape = FakeCombo()
    p.operation = FakeCombo()
    p.width = FakeNum(); p.height = FakeNum()
    p.frameWidth = FakeNum(); p.frameDepth = FakeNum(); p.sashThk = FakeNum()
    p.swingSide = FakeCombo(); p.swingDir = FakeCombo(); p.panelPos = FakeCombo()
    p.sill = FakeNum(); p.opening = FakeNum()
    p.symbolPlan = FakeCheck(); p.symbolElev = FakeCheck()
    return p


def _configured_obj(spec):
    obj = FakeObj()
    obj.Base = fake_base(z=950.0)
    obj.Hosts = []
    obj.Width = quantity(spec["width"])
    obj.Height = quantity(spec["height"])
    obj.Frame = quantity(spec["sashThk"])
    obj.Opening = 0
    obj.SymbolPlan = True
    obj.SymbolElevation = False
    wg.storeSpec(obj, spec)
    return obj


def test_editing_restores_every_field():
    # Open a fully non-default window for edit: the panel must reproduce the
    # exact configuration, not fall back to any defaults.
    spec = _spec(operation="Single casement", width=1500.0, height=1800.0,
                 frameWidth=80.0, sashThk=60.0, frameDepth=200.0,
                 swingSide="Right", swingDir="Outward", panelPos="Back")
    p = _panel(_configured_obj(spec))
    p._loadFromObject()
    assert p._collect() == spec


def test_editing_one_field_leaves_the_rest_unchanged():
    spec = _spec(operation="Single casement", width=1500.0, height=1800.0,
                 frameWidth=80.0, sashThk=60.0, frameDepth=200.0,
                 swingSide="Right", swingDir="Outward", panelPos="Back")
    p = _panel(_configured_obj(spec))
    p._loadFromObject()
    p.width.setValue(2000.0)              # user edits only the width
    assert p._collect() == dict(spec, width=2000.0)


def test_legacy_object_without_spec_infers_round_shape():
    # Objects created before spec persistence have no stored spec; the panel
    # must still open, falling back to native props and inferring the shape.
    obj = FakeObj()
    circle = types.SimpleNamespace(TypeId="Part::GeomCircle")
    obj.Base = fake_base(z=0.0, geometry=[circle])
    obj.Hosts = []
    obj.Width = quantity(800.0); obj.Height = quantity(800.0)
    obj.Frame = quantity(45.0); obj.Opening = 0
    p = _panel(obj)
    p._loadFromObject()
    assert p.shape.currentText() == "Round"
    assert p._collect()["width"] == 800.0
