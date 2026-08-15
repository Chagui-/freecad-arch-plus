# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The stock asset builder. A part backed by a downloaded STEP/BREP file needs
# no code of its own - it names this builder and supplies metadata, which is
# what makes third-party content safe: an asset-only part executes no
# library-supplied code at all.

ASSET_NAME = "body"


def single(params, assets, ctx):
    """Load the part's single shape asset and normalise it.

    The manifest's geometry.transform decides unit scale, rotation and anchor;
    see partslib_geometry._Context.normalize."""
    return ctx.normalize(assets.shape(ASSET_NAME), params)
