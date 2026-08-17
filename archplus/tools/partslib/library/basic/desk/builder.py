# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """An office desk: a top carried by a drawer pedestal at one end and a
    panel end at the other, closed at the back by a modesty panel.

    Params: Width, Depth, Height, TopThickness, PedestalWidth,
    PanelThickness (mm), DrawerCount (integer).

    Deliberately NOT `table()` with different numbers. A desk you sit at to
    work is a different object from a dining table: it has a knee hole with
    something solid either side of it, storage on one side, and a screen
    across the back. Four legs and an apron is the one arrangement it never
    has."""
    width = float(params.get("Width", 1400))
    depth = float(params.get("Depth", 700))
    height = float(params.get("Height", 750))
    top_thickness = min(float(params.get("TopThickness", 30)), height - 10)
    pedestal_width = float(params.get("PedestalWidth", 400))
    panel_thickness = float(params.get("PanelThickness", 30))
    drawer_count = max(int(params.get("DrawerCount", 3)), 0)

    under_height = max(height - top_thickness, 10.0)
    pedestal_width = min(pedestal_width, width * 0.4)
    # Both supports are set back from the front edge, so the top overhangs
    # them and the desk does not read as a solid block.
    setback = min(30.0, depth * 0.05)
    support_depth = depth - setback
    kick = min(60.0, under_height * 0.09)

    top = sh.rounded_box(width, depth, top_thickness, radius=12)
    top = sh.soften_top(top, 5)
    top = sh.soften_top(top, 4, z=0)
    top = sh.place(top, 0, 0, under_height)

    # Panel end (left): a solid gable, the way a desk actually stands.
    panel = sh.rounded_box(panel_thickness, support_depth, under_height,
                           radius=4)
    panel = sh.toe_kick(panel, panel_thickness, support_depth,
                         kick_height=kick, kick_depth=min(20.0, depth * 0.03),
                         margin=0.0)
    panel = sh.place(panel, 0, setback, 0)

    # Pedestal (right): a carcass of drawers.
    pedestal = sh.rounded_box(pedestal_width, support_depth, under_height,
                              radius=6)
    pedestal = sh.toe_kick(pedestal, pedestal_width, support_depth,
                            kick_height=kick,
                            kick_depth=min(25.0, depth * 0.04),
                            margin=min(15.0, pedestal_width * 0.05))
    pulls = []
    if drawer_count > 0:
        zone = under_height - kick
        drawer_height = zone / drawer_count
        margin = min(16.0, pedestal_width * 0.05)
        pull_length = pedestal_width * 0.42
        grooves = []
        for i in range(drawer_count):
            z = kick + i * drawer_height
            grooves.extend(sh.panel_reveal_boxes(
                margin, z + margin * 0.4,
                pedestal_width - 2 * margin, drawer_height - margin * 0.8,
                groove=5.0, depth=7.0))
            pulls.append(sh.place(
                sh.bar(pull_length, 6.0, along="x"),
                width - pedestal_width + (pedestal_width - pull_length) / 2.0,
                setback, kick + (i + 0.5) * drawer_height))
        pedestal = sh.cut_boxes(pedestal, grooves)
    pedestal = sh.place(pedestal, width - pedestal_width, setback, 0)

    # Modesty panel across the knee hole, set well back from the front.
    knee_width = width - panel_thickness - pedestal_width
    modesty = []
    if knee_width > 0:
        modesty_height = under_height * 0.55
        modesty.append(sh.place(
            sh.rounded_box(knee_width, panel_thickness * 0.6,
                           modesty_height, radius=3),
            panel_thickness, depth - panel_thickness * 0.6,
            under_height - modesty_height))

    return sh.fuse_all([top, panel, pedestal] + modesty + pulls)
