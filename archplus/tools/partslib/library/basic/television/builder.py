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

    Params: ScreenSize (diagonal inches), Mounting ("stand" or "wall"),
    Width, Height, PanelThickness, BezelWidth, StandHeight (mm). Width and
    Height are derived from ScreenSize unless pinned.

    `Height` is the panel alone; a stand adds `StandHeight` below it, so the
    two mountings measure differently on purpose - a wall-mounted set has no
    floor footprint to schedule."""
    bezel = float(params.get("BezelWidth", 18))
    screen_size = max(int(params.get("ScreenSize", 55)), 1)
    # A screen is sold by its diagonal in inches at 16:9, so the panel's
    # outside dimensions are that diagonal split into sides plus a bezel on
    # each edge. 55 gives 1254 x 721, 65 gives 1475 x 845.
    diagonal = screen_size * 25.4
    width = params.get("Width")
    if width is None:
        width = diagonal * 16.0 / 18.357560 + 2.0 * bezel
    width = float(width)
    height = params.get("Height")
    if height is None:
        height = diagonal * 9.0 / 18.357560 + 2.0 * bezel
    height = float(height)
    panel = float(params.get("PanelThickness", 60))
    stand_height = float(params.get("StandHeight", 90))
    mounted = 1 if params.get("Mounting") == "wall" else 0

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
