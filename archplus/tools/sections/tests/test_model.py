# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The rules that decide whether a part's cached outline may stand in for its
# solid. Pure data, so they are testable without FreeCAD - which matters,
# because each one is a way a drawing could come out wrong: a view that is not
# a plan, a part rotated off plan, and a part the cut does not leave whole.

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


def test_a_depth_floor_refuses_the_parts_it_cuts_away():
    # A 4200 plan with Depth 1000 keeps only the 3200..4200 band. A ground
    # floor part at 0..700 is cut away entirely, so an outline there would be
    # a part the drawing does not have.
    assert not model.part_above_the_depth_floor(0.0, 4200.0, 1000.0)
    assert not model.use_outline((0.0, 700.0), 4200.0, (0.0, 0.0, 1.0),
                                 (0.0, 0.0, 1.0), 0.0, 1000.0)
    # Straddling the floor at 3200: the solid is sliced rather than whole, so
    # its footprint is not the shape the cut keeps either.
    assert not model.part_above_the_depth_floor(3000.0, 4200.0, 1000.0)
    assert not model.use_outline((3000.0, 3900.0), 4200.0, (0.0, 0.0, 1.0),
                                 (0.0, 0.0, 1.0), 0.0, 1000.0)


def test_a_part_inside_the_depth_band_uses_its_outline():
    # 3300..3900 lies inside the 3200..4200 band, so the cut leaves it whole.
    assert model.part_above_the_depth_floor(3300.0, 4200.0, 1000.0)
    assert model.use_outline((3300.0, 3900.0), 4200.0, (0.0, 0.0, 1.0),
                             (0.0, 0.0, 1.0), 0.0, 1000.0)
    # A Depth of zero (the default) sets no floor at all.
    assert model.part_above_the_depth_floor(0.0, 4200.0, 0.0)
    assert model.use_outline((0.0, 700.0), 4200.0, (0.0, 0.0, 1.0),
                             (0.0, 0.0, 1.0), 0.0)
