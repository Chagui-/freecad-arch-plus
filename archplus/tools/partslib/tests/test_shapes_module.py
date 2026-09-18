# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Guards the public surface of the shared geometry vocabulary. Every part
# builder and every family's _shared.py imports this module by its absolute
# path, so losing a name here breaks parts that never mention it directly.

from archplus.tools.partslib import shapes

import types


def test_shapes_is_importable_without_freecad():
    # Imported at module scope above: the assertion is that the import
    # itself did not raise under the fake Part in conftest.py.
    assert shapes.__name__ == "archplus.tools.partslib.shapes"


def test_the_public_massing_vocabulary_is_present():
    expected = [
        "rounded_box", "soften_top", "square_leg", "roll_top", "tapered_leg",
        "cut_box", "cut_boxes", "cushion", "bar", "panel_reveal_boxes",
        "panel_reveal", "toe_kick", "door_seam", "oval", "rotate",
        "tube_elbow", "vector", "place", "fuse_all", "soften_edges",
    ]
    missing = [name for name in expected
               if not callable(getattr(shapes, name, None))]
    assert missing == []


class _FakeShape:
    """Records which easing the helper reached for, and can refuse either.

    The policy under test is which of chamfer/fillet a shape gets, and what
    happens when the kernel refuses - a fake answers both without an OCC
    kernel, which the pytest run has none of."""

    def __init__(self, chamfer_ok=True, fillet_ok=True):
        self.chamfer_ok = chamfer_ok
        self.fillet_ok = fillet_ok
        self.calls = []

    def makeChamfer(self, size, edges):
        self.calls.append(("chamfer", size, edges))
        if not self.chamfer_ok:
            raise RuntimeError("chamfer refused")
        return self

    def makeFillet(self, radius, edges):
        self.calls.append(("fillet", radius, edges))
        if not self.fillet_ok:
            raise RuntimeError("fillet refused")
        return self


def test_easing_chamfers_at_a_size_matching_the_fillet_it_replaces():
    shape = _FakeShape()
    assert shapes.soften_edges(shape, 10.0, ["e1"]) is shape
    # a chamfer removes 0.5*s^2 of the corner per unit length where a fillet
    # of radius r removes 0.215*r^2, so 0.6r is the size that keeps the
    # part's mass: test the mapping, not the number's provenance
    assert shape.calls == [("chamfer", 6.0, ["e1"])]


def test_easing_falls_back_to_a_fillet_when_the_chamfer_will_not_build():
    shape = _FakeShape(chamfer_ok=False)
    assert shapes.soften_edges(shape, 10.0, ["e1"]) is shape
    assert [c[0] for c in shape.calls] == ["chamfer", "fillet"]
    assert shape.calls[1] == ("fillet", 10.0, ["e1"])


def test_easing_degrades_to_a_sharp_corner_when_neither_will_build():
    shape = _FakeShape(chamfer_ok=False, fillet_ok=False)
    assert shapes.soften_edges(shape, 10.0, ["e1"]) is shape
    assert [c[0] for c in shape.calls] == ["chamfer", "fillet"]


def test_easing_is_skipped_without_edges_or_a_size():
    for radius, edges in ((0.0, ["e1"]), (None, ["e1"]), (10.0, [])):
        shape = _FakeShape()
        assert shapes.soften_edges(shape, radius, edges) is shape
        assert shape.calls == []


def test_soften_top_and_roll_top_route_through_the_same_easing():
    # The three entry points that ease an existing shape must not bypass the
    # chamfer policy - a helper that filleted directly would quietly put the
    # round faces back on every part that calls it.
    for helper, kwargs in ((shapes.soften_top, {}), (shapes.roll_top, {})):
        shape = _FakeShape()
        shape.BoundBox = types.SimpleNamespace(ZMax=100.0)
        shape.Edges = []
        helper(shape, 10.0, **kwargs)
        assert shape.calls == [] or shape.calls[0][0] == "chamfer"
