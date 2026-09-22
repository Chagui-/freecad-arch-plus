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
    import Part

    width = float(params.get("Width", 600))
    height = float(params.get("Height", 800))
    depth = float(params.get("Depth", 30))
    frame = float(params.get("FrameWidth", 35))

    # Where the glass sits: the recess still stops at `floor`, 0.4 of the
    # Depth as it always has, and the pane is the slice of the 0.6 the
    # recess leaves behind that plane. The rest of it stays frame.
    floor = depth * 0.4
    pane_depth = depth * 0.2

    body = sh.rounded_box(width, depth, height, radius=6)
    glass = []
    # Glass set back inside the frame. Cut from the FRONT (-Y) face, which
    # is the face a wall-hosted part presents to the room.
    if width > 2 * frame and height > 2 * frame:
        body = sh.cut_box(body, frame, -1.0, frame,
                          width - 2 * frame, floor + 1.0,
                          height - 2 * frame)
        # The slab comes out of the frame on the recess's own footprint and
        # is fused back as the glass, so the recess stays exactly as open as
        # it was and frame + glass is the solid built before.
        slab = Part.makeBox(width - 2 * frame, pane_depth, height - 2 * frame)
        slab.translate(sh.vector(frame, floor, frame))
        glass.append(slab)
        body = sh.cut_box(body, frame, floor, frame,
                          width - 2 * frame, pane_depth, height - 2 * frame)
    # Two roles, and so two colours: the moulding around the glass is a
    # fitting, the glass the recess sits against is the glazing.
    return sh.fuse_all({
        "fitting": [body],
        "glass": glass,
    }, ctx)
