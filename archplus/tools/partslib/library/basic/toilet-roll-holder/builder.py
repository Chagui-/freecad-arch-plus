# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A wall toilet-roll holder: backplate, an arm out from the wall, and
    the roll on a spindle running PARALLEL to the wall. Wall-hosted.

    Params: PlateWidth, PlateHeight, PlateDepth, ArmLength, RollDiameter,
    RollWidth, CoreDiameter (mm).

    The spindle direction is the whole point. The first version ran the arm
    and the spindle along the same axis, so the roll hung off the end of a
    stick like a paint roller. On a real holder the arm projects from the
    wall and the roll turns on an axis across it."""
    import Part

    plate_width = float(params.get("PlateWidth", 50))
    plate_height = float(params.get("PlateHeight", 50))
    plate_depth = float(params.get("PlateDepth", 12))
    arm_length = float(params.get("ArmLength", 70))
    roll_diameter = float(params.get("RollDiameter", 115))
    roll_width = float(params.get("RollWidth", 100))
    core_diameter = float(params.get("CoreDiameter", 45))

    roll_radius = roll_diameter / 2.0
    spindle_radius = max(core_diameter * 0.28, 6.0)

    # Lay the part out so its minimum corner is the origin: the roll is the
    # widest thing in Y and Z, so those extents set the envelope.
    depth = roll_radius + arm_length + plate_depth
    axis_y = roll_radius
    axis_z = roll_radius

    plate = sh.rounded_box(plate_width, plate_depth, plate_height, radius=6)
    plate = sh.place(plate, 0, depth - plate_depth,
                      axis_z - plate_height / 2.0)

    arm = Part.makeCylinder(spindle_radius * 1.3, arm_length,
                            sh.vector(0, 0, 0), sh.vector(0, -1, 0))
    arm = sh.place(arm, plate_width / 2.0, depth - plate_depth, axis_z)

    # Spindle runs across the arm, cantilevered so a roll can slide on.
    spindle_length = roll_width + 14.0
    spindle = Part.makeCylinder(spindle_radius, spindle_length,
                                sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    spindle = sh.place(spindle, plate_width / 2.0, axis_y, axis_z)

    roll = Part.makeCylinder(roll_radius, roll_width,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    roll = sh.place(roll, plate_width / 2.0 + 7.0, axis_y, axis_z)
    core = Part.makeCylinder(core_diameter / 2.0, roll_width + 4.0,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    core = sh.place(core, plate_width / 2.0 + 5.0, axis_y, axis_z)
    try:
        roll = roll.cut(core)
    except Exception:
        pass

    return sh.fuse_all([plate, arm, spindle, roll])
