# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section view rules - plain data only.
#
# Whether a part's cached plan drawing may stand in for its solid is a
# question about numbers: which way the view projects, how the part is
# rotated, and where the cut plane sits against the part's height. Kept free
# of FreeCAD imports so each rule is testable headlessly, and so a wrong
# answer is caught by a unit test rather than by a drawing that looks subtly
# off. Do not add FreeCAD, Part or PySide dependencies here.

TOLERANCE = 1e-6


def is_plan_direction(direction, tolerance=TOLERANCE):
    """True when a view projects along +Z, i.e. it is a plan cut."""
    x, y, z = direction
    return abs(x) <= tolerance and abs(y) <= tolerance \
        and abs(z - 1.0) <= tolerance


def rotation_is_about_z(axis, angle, tolerance=TOLERANCE):
    """True when a placement's rotation leaves the plan projection alone.

    A part rotated about Z still projects to the same drawing from above; one
    tilted about X or Y does not, and must be drawn as its solid.
    """
    if abs(angle) <= tolerance:
        return True
    return abs(axis[0]) <= tolerance and abs(axis[1]) <= tolerance


def part_is_below_the_cut(z_max, plane_z, tolerance=TOLERANCE):
    """True when the section plane leaves the part whole.

    The cut removes everything above the plane - that is what makes a plan a
    plan - so a part reaching above it is drawn differently: a sliced one
    shows its section, and one wholly above is removed from the drawing
    altogether. Neither is what a cached plan drawing is of, so neither may
    take one. Only a part wholly below the plane is drawn as its plan
    projection.
    """
    return z_max <= plane_z + tolerance


def part_above_the_depth_floor(z_min, plane_z, depth, tolerance=TOLERANCE):
    """True when the part clears the floor a non-zero Depth cuts at.

    A plane with a Depth does not keep everything below it: Arch's
    getCutVolume fuses the volume above the plane with everything below
    `plane_z - depth`, so the cut keeps only the band between the two. A part
    under that floor is removed from the drawing entirely, and one straddling
    it is sliced - neither may take its cached plan drawing. A Depth of zero
    (the default) sets no floor.
    """
    return depth <= tolerance or z_min >= plane_z - depth - tolerance


def use_drawing(z_range, plane_z, direction, axis, angle, depth=0.0):
    """Whether a part's cached plan drawing may stand in for its solid.

    All four conditions must hold: the view is a plan, the part is not
    rotated off plan, the part lies below the cut, and - when the plane has a
    Depth - the part is above the floor that Depth cuts at. Anything else
    draws the solid, which is what the view drew before this feature.
    `depth` is the plane's own Depth, as a number.
    """
    return (is_plan_direction(direction)
            and rotation_is_about_z(axis, angle)
            and part_is_below_the_cut(z_range[1], plane_z)
            and part_above_the_depth_floor(z_range[0], plane_z, depth))
