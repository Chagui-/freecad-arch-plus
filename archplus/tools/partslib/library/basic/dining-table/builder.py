# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A dining table: the family's apron-framed table at seating height.
#
# This delegates rather than duplicating because the dining table and the
# coffee table are genuinely one design at two proportions today - the
# manifest's ShelfHeight is what distinguishes them. When a real difference
# appears, it belongs here rather than as another branch in _shared.table.

from .. import _shared


def derived_params(params):
    """Values this part derives but does not build.

    A dining table has no per-seat geometry, so SeatCount cannot be read back
    off the shape the way Width and Height can. Deriving it here rather than
    inside build() gives it one home with a real caller: build() would only
    compute it into a local nothing consumes, and the value a user should see
    is not a by-product of building.

    Returns {name: value} for every param this builder derives that its
    geometry does not embody. Only params the manifest declares "auto" and
    that build() does not consume belong here.
    """
    width = float(params.get("Width", 1200))
    # 500mm of table edge per diner, both long sides laid: 1200 seats 4,
    # 1600 seats 6, 2000 seats 8.
    return {"SeatCount": max(2 * int(width // 500), 2)}


def build(params, assets, ctx):
    """Build the dining table and report its derived seating capacity.

    SeatCount is derived, not built: a table has no per-seat geometry. See
    derived_params() - the geometry here does not depend on it.
    """
    return _shared.table(params, assets, ctx)
