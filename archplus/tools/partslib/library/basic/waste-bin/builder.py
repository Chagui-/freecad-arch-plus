# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh

# The lid overhangs the body on every side, so the advertised Width and
# Depth are the lid's - the same "build the overhang inwards" rule the
# cabinets' worktops follow. The pedal reaches back under that overhang.
_LID_OVERHANG = 15.0
_LID_SHARE = 0.07
_PEDAL_LENGTH = 90.0
_PEDAL_HEIGHT = 22.0
_PEDAL_REACH = 20.0


def build(params, assets, ctx):
    """A pedal bin: a body under an overhanging lid, with a foot pedal at
    the front of the floor.

    Params: Width, Depth, Height (mm).

    Square rather than round section: a kitchen bin is as often a slim
    rectangle as a cylinder, a square body is honest at any Width and Depth
    a user types, and nothing in this family eases a solid round."""
    import Part

    width = float(params.get("Width", 300))
    depth = float(params.get("Depth", 300))
    height = float(params.get("Height", 700))
    overhang = min(_LID_OVERHANG, width * 0.05, depth * 0.05)
    lid_height = max(height * _LID_SHARE, 20.0)
    body_height = max(height - lid_height, 1.0)

    body = sh.rounded_box(width - 2 * overhang, depth - 2 * overhang,
                          body_height, radius=10)
    body = sh.place(body, overhang, overhang, 0)

    lid = sh.rounded_box(width, depth, lid_height, radius=10)
    lid = sh.roll_top(lid, min(8.0, lid_height * 0.3), axis="x")
    lid = sh.place(lid, 0, 0, body_height)

    # The pedal tucks under the lid's overhang, flush with its front edge:
    # it reads as a pedal from the side, and because it never reaches past
    # y=0 the part is still exactly as deep as the manifest advertises.
    pedal = Part.makeBox(max(_PEDAL_LENGTH, 0.0),
                         overhang + _PEDAL_REACH, _PEDAL_HEIGHT)
    pedal = sh.place(pedal, (width - _PEDAL_LENGTH) / 2.0, 0.0, 0.0)

    return sh.fuse_all([body, lid, pedal])
