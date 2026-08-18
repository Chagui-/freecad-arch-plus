# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


# These are the parts that are neither case goods nor sanitaryware: thin,
# mostly flat, and read almost entirely from their silhouette. The massing
# rules that serve the cabinets do not all transfer. In particular a screen
# or a mirror is a plane, so what makes it legible is the FRAME around it
# and the recess inside - not rounded corners, which at 20mm thickness are
# invisible anyway.
def build(params, assets, ctx):
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
