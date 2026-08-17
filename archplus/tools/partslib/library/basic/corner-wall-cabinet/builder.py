# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """An L-shaped wall-hung corner unit. Wall-hosted.

    Params: Width, Depth, Height, ReturnWidth, ReturnDepth (mm)."""
    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 720))
    return_width = float(params.get("ReturnWidth", 350))
    return_depth = float(params.get("ReturnDepth", 350))

    return_width = min(return_width, width - 50.0)
    return_depth = min(return_depth, depth - 50.0)

    box = sh.rounded_box(width, depth, height, radius=6)
    box = sh.cut_box(box, -1.0, -1.0, -1.0,
                     width - return_width + 1.0, depth - return_depth + 1.0,
                     height + 2.0)
    inset = 35.0
    box = sh.panel_reveal(box, width - return_width + inset, inset,
                          return_width - 2 * inset, height - 2 * inset,
                          groove=6.0, depth=8.0,
                          face_depth=depth - return_depth)
    pull = sh.place(sh.bar(height * 0.22, 7.0, along="z"),
                     width - 40.0, depth - return_depth, height * 0.12)
    return sh.fuse_all([box, pull])
