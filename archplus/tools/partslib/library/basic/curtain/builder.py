# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


# The curtain is the one shape here a primitive really cannot describe, and
# the first attempt got it backwards: it cut grooves into a flat slab, which
# read exactly as what it was - a board with holes in it. Grooves SUBTRACT
# from a plane; folds DISPLACE it. It is now a row of overlapping vertical
# cylinders alternating front and back, fused into one serpentine body - a
# hanging plane curled into folds, which is what gathered cloth actually is.
def build(params, assets, ctx):
    """A curtain on a rail, gathered into folds. Wall-hosted.

    Params: Width, Height, Fullness, RailDiameter, HeaderHeight (mm),
    FoldCount (integer).

    The fabric is a serpentine of overlapping vertical cylinders, not a
    grooved slab - see the module notes. `Fullness` is the total depth the
    folds occupy, so it is what gives them room to bulge into."""
    import Part

    width = float(params.get("Width", 1600))
    height = float(params.get("Height", 2200))
    fullness = float(params.get("Fullness", 110))
    rail_diameter = float(params.get("RailDiameter", 28))
    header_height = float(params.get("HeaderHeight", 60))
    # One fold roughly every 133mm of rail: 1600 gives 12, 2400 gives 18.
    fold_count = max(int(width // 133), 2)

    fabric_height = max(height - header_height, 10.0)
    # The rail is what defines the part's Width; the fabric hangs inside it,
    # so a curtain still measures exactly what the manifest advertises.
    overrun = min(80.0, width * 0.06)
    span = max(width - 2 * overrun, 10.0)

    # The fabric is a SERPENTINE, built by fusing a row of vertical
    # cylinders whose centres alternate front and back. Adjacent cylinders
    # overlap, so the union is one continuous wavy body - a hanging plane
    # curled into folds, which is what a gathered curtain actually is.
    #
    # The previous version cut grooves into a flat slab, and it read
    # exactly as what it was: a board with holes in it. Grooves SUBTRACT
    # from a plane; folds DISPLACE it. Only the second reads as cloth.
    if fold_count > 0:
        # r > span / (2 * n) guarantees neighbouring folds intersect; at
        # span / (1.7 * n) they overlap comfortably. Without that the
        # curtain would come apart into a row of loose columns.
        radius = min(span / (1.7 * fold_count), fullness / 2.0)
        radius = max(radius, 1.0)
        step = ((span - 2 * radius) / (fold_count - 1.0)
                if fold_count > 1 else 0.0)
        folds = []
        for i in range(fold_count):
            x = radius + i * step if fold_count > 1 else span / 2.0
            # Alternate which side of the rail each fold bulges toward.
            y = radius if (i % 2 == 0) else max(fullness - radius, radius)
            folds.append(sh.place(Part.makeCylinder(radius, fabric_height),
                                  x, y, 0))
        fabric = sh.fuse_all(folds)
    else:
        fabric = sh.rounded_box(span, fullness, fabric_height, radius=8)
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
