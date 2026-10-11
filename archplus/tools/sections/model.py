# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Section view rules - plain data only.
#
# Whether a part's cached plan outline may stand in for its solid is a
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

    A part rotated about Z still projects to the same outline from above; one
    tilted about X or Y does not, and must be drawn as its solid.
    """
    if abs(angle) <= tolerance:
        return True
    return abs(axis[0]) <= tolerance and abs(axis[1]) <= tolerance


def cut_straddles(z_min, z_max, plane_z, tolerance=TOLERANCE):
    """True when a section plane's cut passes through a part's height.

    Then the solid is sliced and shows a section, while an outline (flat at
    the part's base) would show the whole footprint - a different drawing.
    """
    return (z_min - tolerance) < plane_z < (z_max + tolerance)


def use_outline(z_range, plane_z, direction, axis, angle):
    """Whether a part's cached outline may stand in for its solid.

    All three conditions must hold: the view is a plan, the part is not
    rotated off plan, and the cut does not pass through it. Anything else
    draws the solid, which is what the view drew before this feature.
    """
    return (is_plan_direction(direction)
            and rotation_is_about_z(axis, angle)
            and not cut_straddles(z_range[0], z_range[1], plane_z))
