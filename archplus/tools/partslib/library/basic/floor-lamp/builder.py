# SPDX-License-Identifier: LGPL-2.1-or-later

from archplus.tools.partslib import shapes as sh


def build(params, assets, ctx):
    """A floor lamp: weighted base, slim stem, conical shade.

    Params: Height, BaseDiameter, StemDiameter, ShadeHeight, ShadeTopDiameter,
    ShadeBottomDiameter (mm)."""
    import Part

    height = float(params.get("Height", 1600))
    base_diameter = float(params.get("BaseDiameter", 300))
    stem_diameter = float(params.get("StemDiameter", 30))
    shade_height = float(params.get("ShadeHeight", 320))
    shade_top = float(params.get("ShadeTopDiameter", 260))
    shade_bottom = float(params.get("ShadeBottomDiameter", 380))

    radius = max(base_diameter, shade_bottom) / 2.0
    base_height = 25.0

    base = Part.makeCylinder(base_diameter / 2.0, base_height)
    base = sh.soften_top(base, base_height * 0.4)
    base = sh.place(base, radius, radius, 0)

    stem_height = max(height - shade_height, 10.0)
    stem = Part.makeCylinder(stem_diameter / 2.0, stem_height)
    stem = sh.place(stem, radius, radius, 0)

    # A cone frustum, wider at the bottom - the one place in this library
    # where a turned profile is the right answer rather than a square one.
    shade = Part.makeCone(shade_bottom / 2.0, shade_top / 2.0, shade_height)
    shade = sh.place(shade, radius, radius, stem_height)

    return sh.fuse_all([base, stem, shade])
