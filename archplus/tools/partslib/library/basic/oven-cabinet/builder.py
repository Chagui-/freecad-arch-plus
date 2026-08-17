# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh
from .. import _shared


def build(params, assets, ctx):
    """A base unit housing a built-in oven, with a drawer beneath it.

    Params: Width, Depth, Height, WorktopThickness, KickHeight, OvenHeight
    (mm)."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 900))
    worktop = float(params.get("WorktopThickness", 40))
    kick_height = float(params.get("KickHeight", 100))
    oven_height = float(params.get("OvenHeight", 590))

    overhang = min(20.0, depth * 0.04)
    carcass_depth = depth - overhang
    carcass_height = height - worktop
    oven_height = min(oven_height, carcass_height - kick_height - 60.0)

    box = _shared.carcass(width, carcass_depth, carcass_height,
                   kick_height, min(45.0, depth * 0.08))

    # Oven sits at the top of the unit; the drawer takes what is left.
    oven_z = carcass_height - oven_height
    inset = min(18.0, width * 0.03)
    # Recess the whole oven front rather than outlining it: an appliance
    # front is proud of the door line, not flush with it, and the recess is
    # what puts a shadow round all four sides.
    boxes = [
        (inset, -1.0, oven_z + inset,
         width - 2 * inset, 12.0, oven_height - 2 * inset),
        # Control strip across the top of the oven, and its door line.
        (inset, -1.0, carcass_height - inset - 70.0,
         width - 2 * inset, 16.0, 6.0),
    ]
    drawer_zone = oven_z - kick_height
    if drawer_zone > 0:
        margin = min(16.0, width * 0.03)
        boxes.extend(sh.panel_reveal_boxes(
            margin, kick_height + margin,
            width - 2 * margin, drawer_zone - 2 * margin,
            groove=5.0, depth=7.0))
    box = sh.cut_boxes(box, boxes)
    box = sh.place(box, 0, overhang, 0)

    top = sh.rounded_box(width, depth, worktop, radius=6)
    top = sh.roll_top(top, min(worktop * 0.4, 12.0), axis="x")
    top = sh.place(top, 0, 0, carcass_height)

    handles = [
        # Oven door handle.
        sh.place(sh.bar(width * 0.7, 9.0, along="x"),
                 width * 0.15, overhang - 6.0,
                 carcass_height - oven_height * 0.18),
    ]
    if drawer_zone > 0:
        handles.append(sh.place(
            sh.bar(width * 0.4, 7.0, along="x"),
            width * 0.3, overhang, kick_height + drawer_zone * 0.5))
    return sh.fuse_all([box, top] + handles)
