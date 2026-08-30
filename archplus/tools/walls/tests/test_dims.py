# archplus/tools/walls/tests/test_dims.py
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Headless tests for the wall length overlay: dimension geometry, chain
# summaries, selection mapping and overlay bookkeeping. dims.py imports
# FreeCAD/FreeCADGui only inside functions, so the conftest fakes carry the
# whole suite.

import types

import FreeCAD
import FreeCADGui
import pytest

from archplus.tools.walls import dims
from archplus.tools.walls import gui as walls_gui
from archplus.tools.walls import object as walls_object

UP = (0.0, 0.0, 1.0)


# --- dim geometry (Task 1) --------------------------------------------------

def test_polyline_length_sums_segments():
    pts = [(0, 0, 0), (1000, 0, 0), (1000, 500, 0)]
    assert dims.polyline_length(pts) == pytest.approx(1500.0)


def test_dim_lift_clears_the_top_edge():
    # 5 % of the height once that beats the 100 mm floor.
    assert dims.dim_lift(2800.0) == pytest.approx(2940.0)
    # the 100 mm floor for low walls.
    assert dims.dim_lift(1000.0) == pytest.approx(1100.0)


def test_dim_geometry_raises_a_straight_chain():
    line, ticks, label = dims._dimGeometry([(0, 0, 0), (4000, 0, 0)], UP,
                                           2800.0)
    assert line == [(0.0, 0.0, 2940.0), (4000.0, 0.0, 2940.0)]
    assert label == (2000.0, 0.0, 2940.0)
    assert len(ticks) == 2


def test_dim_geometry_ticks_cross_the_ends_at_45_degrees():
    line, ticks, _label = dims._dimGeometry([(0, 0, 0), (4000, 0, 0)], UP,
                                            2800.0)
    for (a, b), end in zip(ticks, line):
        mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)
        assert mid == pytest.approx(end)
        assert dims._dist(a, b) == pytest.approx(60.0)
        assert a[2] == b[2] == end[2]


def test_dim_geometry_follows_an_l_chain():
    line, ticks, label = dims._dimGeometry(
        [(0, 0, 0), (4000, 0, 0), (4000, 3000, 0)], UP, 2800.0)
    assert len(line) == 3
    assert line[2] == (4000.0, 3000.0, 2940.0)
    # total 7000, so the arc-length midpoint sits at 3500 on the first leg.
    assert label == (3500.0, 0.0, 2940.0)
    assert len(ticks) == 2


def test_dim_geometry_rejects_degenerate_chains():
    with pytest.raises(ValueError):
        dims._dimGeometry([(0, 0, 0)], UP, 2800.0)


def test_format_length_falls_back_to_millimetres():
    # The conftest fake Units make Quantity() return None, which forces the
    # plain millimetre fallback — exactly the path this test pins.
    assert dims.format_length(2450.0) == "2450 mm"
