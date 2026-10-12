# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The rules that decide whether a part's cached outline may stand in for its
# solid. Pure data, so they are testable without FreeCAD - which matters,
# because each one is a way a drawing could come out wrong: a view that is not
# a plan, a part rotated off plan, and a part the cut plane passes through.

from archplus.tools.sections import model


def test_plan_direction_is_z():
    assert model.is_plan_direction((0.0, 0.0, 1.0))
    assert not model.is_plan_direction((0.0, 1.0, 0.0))
    assert not model.is_plan_direction((0.0, 0.0, -1.0))


def test_a_z_rotation_keeps_the_plan_projection():
    assert model.rotation_is_about_z((0.0, 0.0, 1.0), 1.5707963)
    assert model.rotation_is_about_z((0.0, 0.0, 1.0), 0.0)


def test_an_off_axis_rotation_does_not():
    assert not model.rotation_is_about_z((1.0, 0.0, 0.0), 0.5)
    assert not model.rotation_is_about_z((0.0, 1.0, 0.0), 0.5)


def test_only_a_part_below_the_cut_is_whole():
    # Through the part: the solid would be sliced.
    assert not model.part_is_below_the_cut(2400.0, 1400.0)
    # Wholly above: the cut removes it from the drawing entirely, so a
    # footprint there would be a part the drawing does not have.
    assert not model.part_is_below_the_cut(3900.0, 1400.0)
    # Wholly below: untouched, and drawn as its plan silhouette.
    assert model.part_is_below_the_cut(3900.0, 4200.0)
    # Top exactly at the plane: the cut takes only what is above it.
    assert model.part_is_below_the_cut(3900.0, 3900.0)


def test_a_plan_cut_through_a_part_refuses_its_outline():
    # A floor-standing wardrobe under a 1400mm plan cut: the solid is sliced,
    # a flat outline at its base would not be.
    assert not model.use_outline((0.0, 2400.0), 1400.0,
                                 (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 0.0)
    # A wall cabinet above the same cut: the cut removes its solid outright,
    # so a footprint would be a part the drawing does not have.
    assert not model.use_outline((1500.0, 2100.0), 1400.0,
                                 (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 0.0)


def test_a_part_below_the_cut_uses_its_outline():
    assert model.use_outline((3000.0, 3900.0), 4200.0,
                             (0.0, 0.0, 1.0), (0.0, 0.0, 1.0), 0.0)


def test_an_off_axis_rotation_refuses_the_outline():
    assert not model.use_outline((3000.0, 3900.0), 4200.0,
                                 (0.0, 0.0, 1.0), (1.0, 0.0, 0.0), 0.5)


def test_an_elevation_refuses_the_outline():
    assert not model.use_outline((3000.0, 3900.0), 4200.0,
                                 (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), 0.0)
