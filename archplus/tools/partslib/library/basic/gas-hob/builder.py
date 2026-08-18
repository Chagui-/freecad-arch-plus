# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A gas hob to drop into a worktop: a plate with burners and knobs.

    Params: Width, Depth, PlateThickness, BurnerHeight (mm), BurnerCount
    (integer - 4 or 5, laid out in two columns).

    Placed as its own part rather than modelled into `base_cabinet` because
    on a plan the hob is a separate schedule item, and it rarely sits on the
    unit whose width matches it."""
    import Part

    burner_count = max(int(params.get("BurnerCount", 4)), 1)
    width = params.get("Width")
    if width is None:
        # 150mm of hob per burner: the 4-burner 600mm and 5-burner 750mm
        # sizes every manufacturer ships.
        width = 150.0 * burner_count
    width = float(width)
    depth = float(params.get("Depth", 520))
    plate = float(params.get("PlateThickness", 40))
    burner_height = float(params.get("BurnerHeight", 25))
    body = sh.rounded_box(width, depth, plate, radius=10)
    body = sh.roll_top(body, min(plate * 0.3, 8.0), axis="x")

    burners = []
    columns = 2
    rows = int((burner_count + columns - 1) / columns)
    burner_radius = min(width / (columns * 2.6), depth / (rows * 2.6))
    made = 0
    for row in range(rows):
        for column in range(columns):
            if made >= burner_count:
                break
            x = width * (column + 1) / (columns + 1.0)
            y = depth * (row + 1) / (rows + 1.0) * 0.92 + depth * 0.06
            burners.append(sh.place(
                Part.makeCylinder(burner_radius, burner_height), x, y, plate))
            burners.append(sh.place(
                Part.makeCylinder(burner_radius * 0.42, burner_height * 1.5),
                x, y, plate))
            made += 1

    # Control knobs on the plate near the front edge. Deliberately standing
    # UP rather than projecting forward: a forward-facing knob would push
    # the part past its declared Depth, and on a hob dropped into a worktop
    # the controls are on the top surface anyway.
    knobs = []
    knob_radius = min(14.0, width * 0.03)
    for i in range(burner_count):
        x = width * (i + 1) / (burner_count + 1.0)
        knobs.append(sh.place(Part.makeCylinder(knob_radius, 12.0),
                              x, knob_radius * 1.6, plate))

    return sh.fuse_all([body] + burners + knobs)
