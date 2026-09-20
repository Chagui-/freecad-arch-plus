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
# the pressed bowl hangs the distance into the cabinet a real one does -
# through the opening a worktopless unit leaves - which is what makes this
# read as a sink rather than a tray.
_RIM_THICKNESS = 40.0
_BOWL_DEPTH = 190.0
_BOWL_FLOOR = 12.0
# The bowl's wall. Steel is thinner than this, but the wall is the face you
# see hanging in a cabinet's interior when the sink drops into an open-topped
# unit, and a bowl with no wall is a sliver OCC still has to tessellate.
# It also sets how wide the rim reads: the bowl's margin plus this.
_BOWL_WALL = 10.0
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


def _bowl_prisms(count, width, depth):
    """One (x, y, length, width) per bowl: the footprint it hangs on."""
    gap = _BOWL_GAP if count > 1 else 0.0
    bowl_width = (width - 2 * _BOWL_INSET - gap * (count - 1)) / count
    bowl_depth = depth - _BOWL_INSET - _BOWL_BACK_LEDGE
    return [
        (_BOWL_INSET + i * (bowl_width + gap), _BOWL_INSET,
         bowl_width, bowl_depth)
        for i in range(count)
    ]


def _bowl_cutters(count, width, depth, height):
    """One (x, y, z, length, width, height) cavity per bowl.

    Inset from the bowl's prism by the wall thickness, so the bowl comes out
    with a wall for the cabinet's interior to show."""
    return [
        (x + _BOWL_WALL, y + _BOWL_WALL, _BOWL_FLOOR,
         bw - 2.0 * _BOWL_WALL, bd - 2.0 * _BOWL_WALL,
         height - _BOWL_FLOOR + 1.0)
        for x, y, bw, bd in _bowl_prisms(count, width, depth)
    ]


def _around_bowls(count, width, depth):
    """Boxes stripping everything below the rim that is not a bowl.

    The body is the rim with the bowls hanging off it, not a slab: a slab
    would be a solid the size of the whole unit's interior, so the sink would
    be buried in the cabinet rather than hanging in its void. The strips run
    the full depth on either side of each bowl, and stop at the bowl's own
    edges above and below it, so the prisms keep their material."""
    boxes = []
    edge = 0.0
    for x, y, bw, bd in _bowl_prisms(count, width, depth):
        if x > edge:
            boxes.append((edge, -1.0, 0.0, x - edge, depth + 2.0,
                          _BOWL_DEPTH))
        boxes.append((x, -1.0, 0.0, bw, y + 1.0, _BOWL_DEPTH))
        boxes.append((x, y + bd, 0.0, bw, depth - y - bd + 1.0,
                      _BOWL_DEPTH))
        edge = x + bw
    if edge < width:
        boxes.append((edge, -1.0, 0.0, width - edge, depth + 2.0,
                      _BOWL_DEPTH))
    return boxes


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
    body = sh.cut_boxes(body, _bowl_cutters(bowl_count, width, depth, height)
                        + _around_bowls(bowl_count, width, depth))

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
