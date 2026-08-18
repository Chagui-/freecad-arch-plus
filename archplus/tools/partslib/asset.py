# SPDX-License-Identifier: LGPL-2.1-or-later
#
# The stock builder for a part that ships no code of its own. A part folder
# with no builder.py IS an asset-only part: the absence of the file is what
# guarantees nothing from that folder executes, rather than a manifest
# string claiming it. That is the property that could let a user-supplied
# library be admitted as data only.

ASSET_NAME = "body"


def single(params, assets, ctx):
    """Load the part's single shape asset and normalise it.

    The manifest's geometry.transform decides unit scale, rotation and anchor;
    see partslib_geometry._Context.normalize."""
    return ctx.normalize(assets.shape(ASSET_NAME), params)
