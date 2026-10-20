# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A drop-in sink. Placed as its own part rather than cut into `base_cabinet`
# for the same reason the gas hob is: on a plan the sink is its own schedule
# item, and it rarely sits on the unit whose width matches it.

from archplus.tools.partslib import shapes as sh

# The size each bowl-count default derives from: a 600mm single-bowl sink
# and a 1000mm double, both 500mm front to back - the depth of the worktop
# they drop into. BowlLength is declared at the single-bowl 600, so a
# double-bowl sink keeps that section unless the user sets 1000: the count
# splits the bowl section, it does not add a second one to it.
_DEFAULT_SIZES = {
    1: (600.0, 500.0),
    2: (1000.0, 500.0),
}

# The tray length an auto Width adds to BowlLength. Pinning Width instead
# makes BowlLength authoritative and the tray the remainder, which is the
# split the panel exposes.
_DEFAULT_DRAINER = 300.0

# The pressed drainer: a shallow recess in the rim deck, with parallel
# channels running towards the bowl. Steel is thinner than this, but the
# recess and channels are what make the tray read on a plan and in a
# thumbnail; a flat deck at rim height just looks like more sink.
_TRAY_RECESS = 6.0
_TRAY_EDGE_INSET = 20.0
_TRAY_GROOVE_COUNT = 5
_TRAY_GROOVE_WIDTH = 10.0
_TRAY_GROOVE_DEPTH = 4.0

# The smallest bowl section that still leaves every bowl a usable cavity.
# A pinned Width and BowlLength that conflict are clamped up to this, so a
# drainer can never eat the bowls it is meant to drain into.
_MIN_BOWL_SECTION = {
    1: 240.0,
    2: 420.0,
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


def _drainer_side(drainer):
    """The drainer side, or "none" for an unknown/absent value."""
    return drainer if drainer in ("left", "right") else "none"


def _overall_width(bowl_length, drainer):
    """The width an auto Width resolves to for a bowl section."""
    if _drainer_side(drainer) == "none":
        return bowl_length
    return bowl_length + _DEFAULT_DRAINER


def _split(count, width, bowl_length, drainer):
    """(bowl_x, bowl_length, tray_x, tray_length) for the plan.

    With no drainer the bowls take the full width: a sink with no tray has
    nowhere else for the deck to go. With one, BowlLength is what the user
    asked for and the tray is the remainder; it is clamped only when the
    pair would leave a bowl too narrow to be a bowl."""
    if _drainer_side(drainer) == "none":
        return 0.0, width, 0.0, 0.0
    floor = min(_MIN_BOWL_SECTION.get(count, _MIN_BOWL_SECTION[1]), width)
    bowl_length = max(min(float(bowl_length), width), floor)
    tray_length = max(width - bowl_length, 0.0)
    if _drainer_side(drainer) == "left":
        return tray_length, bowl_length, 0.0, tray_length
    return 0.0, bowl_length, bowl_length, tray_length


def _bowl_prisms(count, zone_length, depth, x_offset=0.0):
    """One (x, y, length, width) per bowl: the footprint it hangs on.

    `zone_length` is the whole bowl section, not one bowl: two bowls split
    it with a divider between them, so the pair still occupies the length
    the user asked for."""
    gap = _BOWL_GAP if count > 1 else 0.0
    bowl_width = max(
        (zone_length - 2 * _BOWL_INSET - gap * (count - 1)) / count, 1.0)
    bowl_depth = depth - _BOWL_INSET - _BOWL_BACK_LEDGE
    return [
        (x_offset + _BOWL_INSET + i * (bowl_width + gap), _BOWL_INSET,
         bowl_width, bowl_depth)
        for i in range(count)
    ]


def _bowl_cutters(count, zone_length, depth, height, x_offset=0.0):
    """One (x, y, z, length, width, height) cavity per bowl.

    Inset from the bowl's prism by the wall thickness, so the bowl comes out
    with a wall for the cabinet's interior to show."""
    return [
        (x + _BOWL_WALL, y + _BOWL_WALL, _BOWL_FLOOR,
         bw - 2.0 * _BOWL_WALL, bd - 2.0 * _BOWL_WALL,
         height - _BOWL_FLOOR + 1.0)
        for x, y, bw, bd in _bowl_prisms(count, zone_length, depth, x_offset)
    ]


def _around_bowls(width, depth, prisms):
    """Boxes stripping everything below the rim that is not a bowl.

    The body is the rim with the bowls hanging off it, not a slab: a slab
    would be a solid the size of the whole unit's interior, so the sink would
    be buried in the cabinet rather than hanging in its void. The strips run
    the full depth on either side of each bowl, and stop at the bowl's own
    edges above and below it, so the prisms keep their material. The same
    strips leave the drainer zone open beneath its shallow pressed floor."""
    boxes = []
    edge = 0.0
    for x, y, bw, bd in prisms:
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


def _tray_boxes(width, depth, height, prisms, drainer):
    """Boxes pressing the drainer into the rim deck, or [] without one.

    The recess opens into the bowl on its inner edge, so the tray reads as
    draining into the bowl rather than as a second, sealed basin. The
    channels are cut deeper than the recess floor and stop short of every
    wall, because a groove that reaches a wall turns into a notch through
    the rim."""
    side = _drainer_side(drainer)
    if side == "none" or not prisms:
        return []
    first, last = prisms[0], prisms[-1]
    if side == "left":
        tray_length = first[0] - _BOWL_INSET
        x0 = _TRAY_EDGE_INSET
        # 1mm into the bowl cavity: a cutter that stops exactly on the
        # cavity's face leaves a coincident face for the boolean to fight.
        x1 = first[0] + _BOWL_WALL + 1.0
    else:
        tray_length = width - (last[0] + last[2] + _BOWL_INSET)
        x0 = last[0] + last[2] - _BOWL_WALL - 1.0
        x1 = width - _TRAY_EDGE_INSET
    if tray_length <= _TRAY_EDGE_INSET:
        return []
    y0 = _BOWL_INSET
    y1 = depth - _BOWL_BACK_LEDGE
    if x1 <= x0 or y1 <= y0:
        return []

    length = x1 - x0
    span = y1 - y0
    boxes = [(x0, y0, height - _TRAY_RECESS,
              length, span, _TRAY_RECESS + 1.0)]

    margin = min(20.0, span / 4.0, length / 4.0)
    groove_length = max(length - 2.0 * margin, 1.0)
    groove_span = max(span - 2.0 * margin, 0.0)
    if groove_span <= 0:
        return boxes
    step = groove_span / max(_TRAY_GROOVE_COUNT - 1, 1)
    for i in range(_TRAY_GROOVE_COUNT):
        gy = y0 + margin + i * step - _TRAY_GROOVE_WIDTH / 2.0
        gy = min(max(gy, y0 + 1.0), y1 - _TRAY_GROOVE_WIDTH - 1.0)
        boxes.append((x0 + margin, gy,
                      height - _TRAY_RECESS - _TRAY_GROOVE_DEPTH,
                      groove_length, _TRAY_GROOVE_WIDTH,
                      _TRAY_RECESS + _TRAY_GROOVE_DEPTH + 1.0))
    return boxes


def build(params, assets, ctx):
    """A sink to drop into a worktop: bowl(s) pressed below a rim, with a
    mixer tap on the back deck and an optional left or right drainer.

    Params: BowlCount (Choice of 1 or 2), Drainer (none, left or right),
    Width (overall), BowlLength (the combined bowl section) and Depth (all
    mm). Width and Depth are derived unless pinned. With a drainer the tray
    is whatever Width leaves outside BowlLength; without one the bowls take
    the full Width, since there is no tray to spend the difference on.
    Editing BowlCount discards pinned sizes, as before.

    The bowls are cut as boxes, not ovals: `oval()` runs a shape through
    transformGeometry and leaves a BSpline surface the tessellator charges
    seconds for, and at sink scale the corner radii do not read."""
    import Part

    bowl_count = int(params.get("BowlCount") or 1)
    if bowl_count not in _DEFAULT_SIZES:
        bowl_count = 1
    drainer = _drainer_side(params.get("Drainer"))
    bowl_length = params.get("BowlLength")
    if bowl_length is None:
        bowl_length = _default_size(bowl_count)[0]
    bowl_length = float(bowl_length)
    width = params.get("Width")
    if width is None:
        width = _overall_width(bowl_length, drainer)
    width = float(width)
    depth = params.get("Depth")
    if depth is None:
        depth = _default_size(bowl_count)[1]
    depth = float(depth)

    bowl_x, bowl_length, _tray_x, _tray_length = _split(
        bowl_count, width, bowl_length, drainer)
    prisms = _bowl_prisms(bowl_count, bowl_length, depth, bowl_x)

    height = _BOWL_DEPTH + _RIM_THICKNESS
    body = sh.rounded_box(width, depth, height, radius=8)
    body = sh.cut_boxes(
        body,
        _bowl_cutters(bowl_count, bowl_length, depth, height, bowl_x)
        + _around_bowls(width, depth, prisms)
        + _tray_boxes(width, depth, height, prisms, drainer))

    # The tap stands on the back deck with its spout reaching over the bowls.
    # It follows the bowl section, not the overall width: centring it on a
    # sink with a drainer would stand it over the tray instead. Everything
    # about it stays inside the declared Width and Depth: a spout
    # overhanging the front edge would make the catalogue lie about the
    # footprint. Its riser starts a millimetre below the rim's face so the
    # fuse has material to join - two solids meeting on a coincident face
    # fuse to a compound of two, which is a part that reads as one object and
    # behaves as two.
    tap_x = bowl_x + bowl_length / 2.0
    tap_y = max(_TAP_RADIUS, min(depth - _TAP_BACK_INSET, depth - _TAP_RADIUS))
    bowl_depth = depth - _BOWL_INSET - _BOWL_BACK_LEDGE
    spout_length = max(min(_TAP_BACK_INSET, bowl_depth / 2.0), 0.0)
    riser = sh.place(Part.makeCylinder(_TAP_RADIUS, _TAP_HEIGHT + 1.0),
                     tap_x, tap_y, height - 1.0)
    spout = sh.place(sh.bar(spout_length, _TAP_RADIUS * 0.7, along="y"),
                     tap_x, tap_y - spout_length,
                     height + _TAP_HEIGHT - _TAP_RADIUS * 0.7)

    # The pressed pan is the sink's own moulded mass; the tap's riser and
    # spout are the hardware standing on its back deck.
    return sh.fuse_all({
        "shell": [body],
        "fitting": [riser, spout],
    }, ctx)
