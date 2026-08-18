# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A wall towel hook: a backplate and a single rod that runs out from
    the wall and curves upward at the tip. Wall-hosted.

    Params: PlateWidth, PlateHeight, PlateDepth, Projection, ArmDiameter,
    BendRadius (mm).

    The rod is one continuous piece - a straight length plus a real
    quarter-bend - not two cylinders butted at a right angle. A mitred
    corner reads as two pipes touching, which is what the first version
    looked like."""
    import Part

    plate_width = float(params.get("PlateWidth", 55))
    plate_height = float(params.get("PlateHeight", 55))
    plate_depth = float(params.get("PlateDepth", 12))
    projection = float(params.get("Projection", 65))
    arm_diameter = float(params.get("ArmDiameter", 14))
    bend_radius = float(params.get("BendRadius", 18))

    tube = arm_diameter / 2.0
    bend_radius = max(bend_radius, tube * 1.2)
    cx = plate_width / 2.0
    # The bend's centre of curvature sits directly above where the straight
    # arm ends, so the arc enters heading -Y and leaves heading +Z. Offset
    # by the tube radius as well as the bend radius, so the OUTSIDE of the
    # curve lands on y=0 rather than reaching behind the part's origin.
    arm_z = plate_height / 2.0
    centre_y = bend_radius + tube
    centre_z = arm_z + bend_radius

    plate = sh.rounded_box(plate_width, plate_depth, plate_height, radius=8)
    plate = sh.place(plate, 0, projection - plate_depth, 0)

    arm_length = max(projection - plate_depth - centre_y, tube)
    arm = Part.makeCylinder(tube, arm_length, sh.vector(0, 0, 0),
                            sh.vector(0, -1, 0))
    arm = sh.place(arm, cx, projection - plate_depth, arm_z)

    parts = [plate, arm]
    elbow = sh.tube_elbow(tube, bend_radius)
    if elbow is not None:
        # The quarter-bend is built in the XY plane running +X to +Y. One
        # 180-degree turn about (1, 0, -1) maps X to -Z and Y to -Y, which
        # lands the arc's ends exactly on the arm end and the upturned tip.
        elbow = sh.rotate(elbow, (1.0, 0.0, -1.0), 180.0)
        parts.append(sh.place(elbow, cx, centre_y, centre_z))
        # Short upturned tip continuing out of the bend.
        tip_length = tube * 2.2
        parts.append(sh.place(Part.makeCylinder(tube, tip_length),
                              cx, centre_y - bend_radius, centre_z))
    else:
        # No torus available: a straight peg still hangs a towel.
        parts.append(sh.place(Part.makeCylinder(tube, bend_radius * 1.6),
                              cx, centre_y, arm_z))

    return sh.fuse_all(parts)
