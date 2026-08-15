# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Reference builder for pure generation - no assets, geometry computed from
# parameters. Kept as the worked example of the builder contract.


def box(params, assets, ctx):
    """A parametric box. Params: Width, Depth, Height (mm)."""
    import Part

    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 720))
    return Part.makeBox(width, depth, height)
