# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Reference builder for pure generation - no assets, geometry computed from
# parameters. Kept as the worked example of the builder contract.
#
# No library part currently references this builder (the library ships
# empty - see docs/PARTS-LIBRARY-VERIFICATION.md); this is a reference
# implementation kept for documentation (design spec Sec 6.1) and is not
# dead code to be pruned.


def box(params, assets, ctx):
    """A parametric box. Params: Width, Depth, Height (mm)."""
    import Part

    width = float(params.get("Width", 600))
    depth = float(params.get("Depth", 600))
    height = float(params.get("Height", 720))
    return Part.makeBox(width, depth, height)
