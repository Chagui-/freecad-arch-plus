# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


# These are the parts that are neither case goods nor sanitaryware: thin,
# mostly flat, and read almost entirely from their silhouette. The massing
# rules that serve the cabinets do not all transfer. In particular a screen
# or a mirror is a plane, so what makes it legible is the FRAME around it
# and the recess inside - not rounded corners, which at 20mm thickness are
# invisible anyway.
def build(params, assets, ctx):
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
