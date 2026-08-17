# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the shared sketch-building helpers, extracted from the identical
# closures that lived inside the Doors and Windows geometry builders.

import FreeCAD

from archplus.common import geometry
from conftest import _FakeSketch

V = FreeCAD.Vector
CORNERS = (V(0, 0, 0), V(10, 0, 0), V(10, 10, 0), V(0, 10, 0))
INNER = (V(1, 1, 0), V(9, 1, 0), V(9, 9, 0), V(1, 9, 0))


def test_add_rect_adds_four_lines():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    assert s.GeometryCount == 4


def test_add_rect_adds_four_coincidences_and_four_alignments():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    kinds = [c.args[0] for c in s.Constraints]
    assert kinds.count("Coincident") == 4
    assert kinds.count("Horizontal") == 2
    assert kinds.count("Vertical") == 2


def test_add_rect_closes_the_loop_back_to_the_first_edge():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    assert s.Constraints[3].args == ("Coincident", 3, 2, 0, 1)


def test_add_rect_offsets_indices_from_existing_geometry():
    s = _FakeSketch()
    geometry.add_rect(s, *CORNERS)
    geometry.add_rect(s, *INNER)
    # The second rectangle's first coincidence must start at index 4, not 0.
    assert s.Constraints[8].args == ("Coincident", 4, 2, 5, 1)


def test_add_frame_adds_an_outer_and_an_inner_rectangle():
    s = _FakeSketch()
    geometry.add_frame(s, *CORNERS, *INNER)
    assert s.GeometryCount == 8
    assert s.ConstraintCount == 16
