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
# The body's floor is narrower than its shoulder. A straight-sided drum
# reads as a pipe at any size; the taper is what says bin.
_BODY_TAPER = 0.88
# How far the cap falls away from its rim, and how round its edge is.
_CAP_FALL = 6.0
_CAP_EASE = 10.0


def build(params, assets, ctx):
    """A pedal bin: a round body under a domed, overhanging cap, with a foot
    pedal at the front of the floor.

    Params: Width, Height (mm), and Depth, which is derived from Width - a
    round plan has one dimension, so the manifest declares it auto and the
    two always measure the same.

    The body is a frustum rather than a cylinder: the taper is what makes it
    read as a bin instead of a pipe, and it is what lets the pedal reach
    under the body's shoulder while still stopping short of the advertised
    depth."""
    import Part

    width = float(params.get("Width", 300))
    depth = params.get("Depth")
    if depth is None:
        depth = width
    # A round plan is one dimension, so the smaller of the two declared ones
    # is the circle's: a pinned Depth can only make the bin smaller than
    # what the manifest advertises, never wider than it. Same rule as the
    # worktops - build the overhang inwards.
    diameter = min(width, float(depth))
    height = float(params.get("Height", 700))

    overhang = min(_LID_OVERHANG, diameter * 0.05)
    lid_height = max(height * _LID_SHARE, 20.0)
    body_height = max(height - lid_height, 1.0)
    shoulder = diameter / 2.0 - overhang

    body = sh.tapered_leg(body_height, shoulder * _BODY_TAPER, shoulder)
    body = sh.place(body, diameter / 2.0, diameter / 2.0, 0.0)

    cap = sh.tapered_leg(lid_height, diameter / 2.0,
                         diameter / 2.0 - _CAP_FALL)
    cap = sh.place(cap, diameter / 2.0, diameter / 2.0, body_height)
    cap = sh.soften_top(cap, _CAP_EASE)

    # The pedal tucks under the lid's overhang, flush with its front edge:
    # it reads as a pedal from the side, and because it never reaches past
    # y=0 the part is still exactly as deep as the manifest advertises.
    pedal = sh.rounded_box(max(_PEDAL_LENGTH, 0.0),
                           overhang + _PEDAL_REACH, _PEDAL_HEIGHT, radius=6)
    pedal = sh.place(pedal, (diameter - _PEDAL_LENGTH) / 2.0, 0.0, 0.0)

    return sh.fuse_all([body, cap, pedal])
