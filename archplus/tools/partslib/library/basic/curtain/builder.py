# SPDX-License-Identifier: LGPL-2.1-or-later

import math

from archplus.tools.partslib import shapes as sh


# The curtain is the one shape here a primitive really cannot describe, and
# it took three attempts to get right. Grooves cut into a flat slab read as
# a board with holes. A row of fat overlapping cylinders read as sausages.
# Both miss what gathered cloth actually is: a THIN sheet whose plane waves
# in and out. So the fabric is now exactly that - one sine wave laid out in
# plan, interpolated into a pair of smooth curves offset by the fabric
# thickness, closed with end caps into a face and extruded floor to hem.
# One continuous serpentine sheet, and not a single boolean on it.
def _serpentine_samples(span, folds, fullness, thickness):
    """(x, y) plan samples of the fabric wave, ends on the centreline.

    Pure math on purpose: this is the part of the curtain worth unit
    testing, and it needs no Part to check. `folds` half-waves fit the
    span, each half-wave being one bulge - alternately toward and away
    from the window, exactly as a gathered heading hangs. The amplitude
    leaves room for the fabric's own thickness, so the offset strip stays
    inside the fullness envelope."""
    amplitude = max(fullness / 2.0 - thickness / 2.0, 1.0)
    count = max(folds, 2) * 6 + 1
    return [
        (span * i / (count - 1.0),
         fullness / 2.0
         + amplitude * math.sin(math.pi * folds * i / (count - 1.0)))
        for i in range(count)
    ]


def _fabric_sheet(span, folds, fullness, thickness, fabric_height):
    """The extruded serpentine sheet, or a plain slab if the kernel balks.

    The two wave curves are built from the same samples with the second
    shifted `thickness` along Y - a pure translation, so a strip that
    pinches slightly at the crests and swells at the troughs, the way
    tensioned cloth behaves, and one that can never self-intersect."""
    import Part

    points = _serpentine_samples(span, folds, fullness, thickness)
    try:
        front = Part.BSplineCurve()
        front.interpolate([sh.vector(x, y, 0) for x, y in points])
        back = Part.BSplineCurve()
        back.interpolate([sh.vector(x, y + thickness, 0)
                          for x, y in points])
        start, end = points[0], points[-1]
        # Chained front-to-back so every edge meets the next at a vertex:
        # MakeWire connects edges in sequence, not by searching.
        caps = [
            Part.makeLine(sh.vector(end[0], end[1], 0),
                          sh.vector(end[0], end[1] + thickness, 0)),
            Part.makeLine(sh.vector(start[0], start[1] + thickness, 0),
                          sh.vector(start[0], start[1], 0)),
        ]
        wire = Part.Wire([front.toShape(), caps[0], back.toShape(),
                          caps[1]])
        return Part.Face(wire).extrude(sh.vector(0, 0, fabric_height))
    except Exception:
        # A kernel refusing any step above must degrade to a plain sheet,
        # not lose the part outright.
        return sh.rounded_box(span, fullness, fabric_height, radius=8)


def build(params, assets, ctx):
    """A curtain on a rail, gathered into folds. Wall-hosted.

    Params: Width, Height, Fullness, RailDiameter, HeaderHeight (mm). The
    fold count follows the width - see the module notes for how the fabric
    itself is built."""
    import Part

    width = float(params.get("Width", 1600))
    height = float(params.get("Height", 2200))
    fullness = float(params.get("Fullness", 110))
    rail_diameter = float(params.get("RailDiameter", 28))
    header_height = float(params.get("HeaderHeight", 60))
    # One fold roughly every 133mm of rail: 1600 gives 12, 2400 gives 18.
    folds = max(int(width // 133), 2)

    fabric_height = max(height - header_height, 10.0)
    # The rail is what defines the part's Width; the fabric hangs inside it,
    # so a curtain still measures exactly what the manifest advertises.
    overrun = min(80.0, width * 0.06)
    span = max(width - 2 * overrun, 10.0)

    thickness = min(12.0, fullness / 4.0)
    fabric = _fabric_sheet(span, folds, fullness, thickness, fabric_height)
    fabric = sh.place(fabric, overrun, 0, 0)

    rail_z = fabric_height + header_height / 2.0
    rail = Part.makeCylinder(rail_diameter / 2.0, width,
                             sh.vector(0, 0, 0), sh.vector(1, 0, 0))
    rail = sh.place(rail, 0, fullness / 2.0, rail_z)

    finial_length = rail_diameter * 0.9
    finials = [
        sh.place(Part.makeCylinder(rail_diameter * 0.75, finial_length,
                                   sh.vector(0, 0, 0), sh.vector(1, 0, 0)),
                 x, fullness / 2.0, rail_z)
        for x in (0.0, width - finial_length)
    ]

    return sh.fuse_all([fabric, rail] + finials)
