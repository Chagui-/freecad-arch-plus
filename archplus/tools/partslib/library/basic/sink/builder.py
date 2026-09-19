# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A drop-in sink. Placed as its own part rather than cut into `base_cabinet`
# for the same reason the gas hob is: on a plan the sink is its own schedule
# item, and it rarely sits on the unit whose width matches it.

from archplus.tools.partslib import shapes as sh

# The size each bowl count ships at, straight from the catalogues: a 600mm
# single-bowl sink and a 1000mm double, both 500mm front to back - the depth
# of the worktop they drop into.
_DEFAULT_SIZES = {
    1: (600.0, 500.0),
    2: (1000.0, 500.0),
}

# The rim is the worktop thickness it sits in, so the manifest's offset can
# drop the rim's top face onto the worktop's. Everything below it is bowl:
# the pressed bowl hangs the distance into the carcass a real one does, which
# is what makes this read as a sink rather than a tray.
_RIM_THICKNESS = 40.0
_BOWL_DEPTH = 190.0
_BOWL_FLOOR = 12.0
# The bowl's margin at the sides and front, and the wider deck left along
# the back: a sink's back rim is the ledge the tap is mounted on, and a bowl
# inset evenly all round would leave the tap standing over the bowl with
# nothing under it.
_BOWL_INSET = 30.0
_BOWL_BACK_LEDGE = 90.0
# The divider between two bowls, wide enough for the tap to sit behind it.
_BOWL_GAP = 60.0

_TAP_RADIUS = 16.0
_TAP_HEIGHT = 220.0
# How far the tap's body sits in from the back edge.
_TAP_BACK_INSET = 55.0


def _default_size(count):
    """(width, depth) in mm for a sink with `count` bowls."""
    return _DEFAULT_SIZES.get(count, _DEFAULT_SIZES[1])


def _bowl_cutters(count, width, depth, height):
    """One (x, y, z, length, width, height) cavity per bowl."""
    gap = _BOWL_GAP if count > 1 else 0.0
    bowl_width = (width - 2 * _BOWL_INSET - gap * (count - 1)) / count
    bowl_depth = depth - _BOWL_INSET - _BOWL_BACK_LEDGE
    return [
        (_BOWL_INSET + i * (bowl_width + gap), _BOWL_INSET, _BOWL_FLOOR,
         bowl_width, bowl_depth, height - _BOWL_FLOOR + 1.0)
        for i in range(count)
    ]


def build(params, assets, ctx):
    """A sink to drop into a worktop: bowl(s) pressed below a rim, with a
    mixer tap on the back deck.

    Params: BowlCount (Choice of 1 or 2), Width and Depth (both derived from
    the count unless pinned; editing the count discards pinned sizes - two
    bowls at the single-bowl width would overlap).

    The bowls are cut as boxes, not ovals: `oval()` runs a shape through
    transformGeometry and leaves a BSpline surface the tessellator charges
    seconds for, and at sink scale the corner radii do not read."""
    import Part

    bowl_count = int(params.get("BowlCount") or 1)
    if bowl_count not in _DEFAULT_SIZES:
        bowl_count = 1
    width = params.get("Width")
    if width is None:
        width = _default_size(bowl_count)[0]
    width = float(width)
    depth = params.get("Depth")
    if depth is None:
        depth = _default_size(bowl_count)[1]
    depth = float(depth)

    height = _BOWL_DEPTH + _RIM_THICKNESS
    body = sh.rounded_box(width, depth, height, radius=8)
    body = sh.cut_boxes(body, _bowl_cutters(bowl_count, width, depth, height))

    # The tap stands on the back deck with its spout reaching over the bowls.
    # Everything about it stays inside the declared Width and Depth: a spout
    # overhanging the front edge would make the catalogue lie about the
    # footprint. Its riser starts a millimetre below the rim's face so the
    # fuse has material to join - two solids meeting on a coincident face
    # fuse to a compound of two, which is a part that reads as one object and
    # behaves as two.
    tap_x = width / 2.0
    tap_y = max(_TAP_RADIUS, min(depth - _TAP_BACK_INSET, depth - _TAP_RADIUS))
    bowl_depth = depth - _BOWL_INSET - _BOWL_BACK_LEDGE
    spout_length = max(min(_TAP_BACK_INSET, bowl_depth / 2.0), 0.0)
    riser = sh.place(Part.makeCylinder(_TAP_RADIUS, _TAP_HEIGHT + 1.0),
                     tap_x, tap_y, height - 1.0)
    spout = sh.place(sh.bar(spout_length, _TAP_RADIUS * 0.7, along="y"),
                     tap_x, tap_y - spout_length,
                     height + _TAP_HEIGHT - _TAP_RADIUS * 0.7)

    return sh.fuse_all([body, riser, spout])
