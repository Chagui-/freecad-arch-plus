# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Loose fittings and furnishings - television, mirror, floor lamp, curtain.
#
# These are the parts that are neither case goods nor sanitaryware: thin,
# mostly flat, and read almost entirely from their silhouette. The massing
# rules that serve the cabinets do not all transfer. In particular a screen
# or a mirror is a plane, so what makes it legible is the FRAME around it
# and the recess inside - not rounded corners, which at 20mm thickness are
# invisible anyway.
#
# The curtain is the one shape here that a primitive really cannot describe.
# Rather than attempt drapery, it is a slab with vertical grooves cut into
# it at a regular pitch - the same seam trick the sofa uses for its cushion
# divisions. At blueprint scale that reads as gathered fabric, and it costs
# a handful of box subtractions instead of a lofted surface.

from . import _shapes as sh


def television(params, assets, ctx):
    """A flat-screen TV, on a pedestal stand or wall-mounted.

    Params: Width, Height, PanelThickness, BezelWidth, StandHeight (mm),
    Mounted (0 for a stand, 1 for a wall bracket).

    `Height` is the panel alone; a stand adds `StandHeight` below it, so the
    two variants measure differently on purpose - a wall-mounted set has no
    floor footprint to schedule."""
    width = float(params.get("Width", 1230))
    height = float(params.get("Height", 710))
    panel = float(params.get("PanelThickness", 60))
    bezel = float(params.get("BezelWidth", 18))
    stand_height = float(params.get("StandHeight", 90))
    mounted = int(params.get("Mounted", 0))

    base_z = 0.0 if mounted else stand_height
    # A stand's foot is far deeper than the panel, so the panel sits in the
    # MIDDLE of that footprint and everything is measured from y=0. Laying
    # it out this way keeps the part's origin at its true minimum corner -
    # placement puts the origin on the picked point, so geometry reaching
    # back behind y=0 would land behind where the user clicked.
    foot_depth = panel * 3.2 if not mounted else panel
    panel_y = (foot_depth - panel) / 2.0 if not mounted else 0.0

    body = sh.rounded_box(width, panel, height, radius=6)
    # Screen recess in the front face: a screen is darker and set back
    # behind its bezel, and the recess is the only thing distinguishing a
    # television from a plain panel at this size.
    if width > 2 * bezel and height > 2 * bezel:
        body = sh.cut_box(body, bezel, -1.0, bezel,
                          width - 2 * bezel, panel * 0.45 + 1.0,
                          height - 2 * bezel)
    body = sh.place(body, 0, panel_y, base_z)

    parts = [body]
    if mounted:
        # Slim wall bracket behind the panel.
        parts.append(sh.place(
            sh.rounded_box(width * 0.3, 30.0, height * 0.4, radius=4),
            width * 0.35, panel, height * 0.3))
    else:
        # Pedestal: a neck on a wide foot plate.
        parts.append(sh.place(
            sh.rounded_box(width * 0.12, panel * 1.6, stand_height, radius=8),
            width * 0.44, (foot_depth - panel * 1.6) / 2.0, 0))
        parts.append(sh.place(
            sh.rounded_box(width * 0.34, foot_depth, 18.0, radius=12),
            width * 0.33, 0, 0))
    return sh.fuse_all(parts)


def mirror(params, assets, ctx):
    """A framed wall mirror. Wall-hosted.

    Params: Width, Height, Depth, FrameWidth (mm)."""
    width = float(params.get("Width", 600))
    height = float(params.get("Height", 800))
    depth = float(params.get("Depth", 30))
    frame = float(params.get("FrameWidth", 35))

    body = sh.rounded_box(width, depth, height, radius=6)
    # Glass set back inside the frame. Cut from the FRONT (-Y) face, which
    # is the face a wall-hosted part presents to the room.
    if width > 2 * frame and height > 2 * frame:
        body = sh.cut_box(body, frame, -1.0, frame,
                          width - 2 * frame, depth * 0.4 + 1.0,
                          height - 2 * frame)
    return body


def floor_lamp(params, assets, ctx):
    """A floor lamp: weighted base, slim stem, conical shade.

    Params: Height, BaseDiameter, StemDiameter, ShadeHeight, ShadeTopDiameter,
    ShadeBottomDiameter (mm)."""
    import Part

    height = float(params.get("Height", 1600))
    base_diameter = float(params.get("BaseDiameter", 300))
    stem_diameter = float(params.get("StemDiameter", 30))
    shade_height = float(params.get("ShadeHeight", 320))
    shade_top = float(params.get("ShadeTopDiameter", 260))
    shade_bottom = float(params.get("ShadeBottomDiameter", 380))

    radius = max(base_diameter, shade_bottom) / 2.0
    base_height = 25.0

    base = Part.makeCylinder(base_diameter / 2.0, base_height)
    base = sh.soften_top(base, base_height * 0.4)
    base = sh.place(base, radius, radius, 0)

    stem_height = max(height - shade_height, 10.0)
    stem = Part.makeCylinder(stem_diameter / 2.0, stem_height)
    stem = sh.place(stem, radius, radius, 0)

    # A cone frustum, wider at the bottom - the one place in this library
    # where a turned profile is the right answer rather than a square one.
    shade = Part.makeCone(shade_bottom / 2.0, shade_top / 2.0, shade_height)
    shade = sh.place(shade, radius, radius, stem_height)

    return sh.fuse_all([base, stem, shade])


def curtain(params, assets, ctx):
    """A curtain on a rail, gathered into folds. Wall-hosted.

    Params: Width, Height, Fullness, RailDiameter, HeaderHeight (mm),
    FoldCount (integer).

    The folds are grooves cut into a slab rather than modelled drapery - see
    the module notes. `Fullness` sets how far the fabric stands off the
    wall, which is what gives the folds something to cut into."""
    width = float(params.get("Width", 1600))
    height = float(params.get("Height", 2200))
    fullness = float(params.get("Fullness", 110))
    rail_diameter = float(params.get("RailDiameter", 28))
    header_height = float(params.get("HeaderHeight", 60))
    fold_count = max(int(params.get("FoldCount", 12)), 0)

    import Part

    fabric_height = max(height - header_height, 10.0)
    fabric = sh.rounded_box(width, fullness, fabric_height, radius=8)

    # Folds: alternating grooves front and back, so the slab reads as
    # gathered rather than as a fluted panel with one flat side.
    if fold_count > 0:
        pitch = width / float(fold_count)
        groove = min(pitch * 0.35, fullness * 0.45)
        for i in range(fold_count):
            x = i * pitch + (pitch - groove) / 2.0
            front = (i % 2 == 0)
            sh_y = -1.0 if front else fullness - fullness * 0.4
            fabric = sh.cut_box(fabric, x, sh_y, -1.0,
                                groove, fullness * 0.4 + 1.0,
                                fabric_height + 2.0)

    fabric = sh.place(fabric, 0, 0, 0)

    # Rail runs a little past the fabric at each end, as a real one does.
    overrun = min(80.0, width * 0.05)
    rail = Part.makeCylinder(rail_diameter / 2.0, width + 2 * overrun,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    rail = sh.place(rail, -overrun, fullness / 2.0,
                     fabric_height + header_height / 2.0)

    finials = [
        sh.place(Part.makeCylinder(rail_diameter * 0.75, rail_diameter * 0.9,
                                   sh.vector(0, 0, 0), sh.vector(1, 0, 0)),
                  x, fullness / 2.0, fabric_height + header_height / 2.0)
        for x in (-overrun - rail_diameter * 0.9, width + overrun)
    ]

    return sh.fuse_all([fabric, rail] + finials)
