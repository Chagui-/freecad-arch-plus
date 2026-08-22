# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh

# The size each burner count ships at, straight from the catalogues: a
# 300mm domino for one or two burners, 600mm for four, 750mm for five.
_DEFAULT_SIZES = {
    1: (300.0, 510.0),
    2: (300.0, 510.0),
    4: (600.0, 520.0),
    5: (750.0, 520.0),
}


def _default_size(count):
    """(width, depth) in mm for a hob with `count` burners."""
    return _DEFAULT_SIZES.get(count, _DEFAULT_SIZES[4])


def _grid_rows(rows):
    """Y fractions of the rows, the 4-burner rhythm kept for parity.

    Two rows land at 0.3667 and 0.6733 of the depth - slightly toward the
    front, where the knobs live."""
    return [(row + 1) / float(rows + 1) * 0.92 + 0.06 for row in range(rows)]


def _burner_layout(count, width, depth):
    """((x, y) plate fractions for each burner, one radius for all).

    Pure math so the layout rules are testable without Part: 1 centred,
    2 front and back on the centreline (a domino is a column, never a
    row), 4 in the classic two-by-two grid, 5 with the fifth in the
    middle of four corner burners. The radius is the largest that keeps
    every burner inside the plate and clear of its neighbours."""
    if count == 1:
        return [(0.5, 0.5)], min(width, depth) * 0.2
    if count == 2:
        return [(0.5, y) for y in _grid_rows(2)], \
            min(width * 0.25, depth * 0.15)
    if count == 5:
        return [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75),
                (0.5, 0.5)], min(width / 5.2, depth / 5.2)
    # Four burners in two columns; anything unrecognised gets this too.
    rows = _grid_rows(2)
    return [(x, y) for y in rows for x in (1.0 / 3.0, 2.0 / 3.0)], \
        min(width / 5.2, depth / 5.2)


def _knob_radius(width):
    """A knob sized to the hob: full-size up to a cap, smaller on a domino."""
    return min(14.0, width * 0.04)


def build(params, assets, ctx):
    """A gas hob to drop into a worktop: a plate with burners and knobs.

    Params: BurnerCount (Choice of 1, 2, 4 or 5), Width and Depth (both
    derived from the count unless pinned; editing the count discards
    pinned sizes - a 5-burner hob at the 4-burner width would overlap).

    Placed as its own part rather than modelled into `base_cabinet` because
    on a plan the hob is a separate schedule item, and it rarely sits on the
    unit whose width matches it."""
    import Part

    burner_count = int(params.get("BurnerCount") or 4)
    if burner_count not in _DEFAULT_SIZES:
        burner_count = 4
    width = params.get("Width")
    if width is None:
        width = _default_size(burner_count)[0]
    width = float(width)
    depth = params.get("Depth")
    if depth is None:
        depth = _default_size(burner_count)[1]
    depth = float(depth)
    plate = float(params.get("PlateThickness", 40))
    burner_height = float(params.get("BurnerHeight", 25))
    body = sh.rounded_box(width, depth, plate, radius=10)
    body = sh.roll_top(body, min(plate * 0.3, 8.0), axis="x")

    positions, burner_radius = _burner_layout(burner_count, width, depth)
    burners = []
    for x_frac, y_frac in positions:
        x = width * x_frac
        y = depth * y_frac
        burners.append(sh.place(
            Part.makeCylinder(burner_radius, burner_height), x, y, plate))
        burners.append(sh.place(
            Part.makeCylinder(burner_radius * 0.42, burner_height * 1.5),
            x, y, plate))

    # Control knobs on the plate near the front edge. Deliberately standing
    # UP rather than projecting forward: a forward-facing knob would push
    # the part past its declared Depth, and on a hob dropped into a worktop
    # the controls are on the top surface anyway.
    knobs = []
    knob_radius = _knob_radius(width)
    for i in range(burner_count):
        x = width * (i + 1) / (burner_count + 1.0)
        knobs.append(sh.place(Part.makeCylinder(knob_radius, 12.0),
                              x, knob_radius * 1.6, plate))

    return sh.fuse_all([body] + burners + knobs)
