# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A dining table: the family's apron-framed table at seating height.
#
# This delegates rather than duplicating because the dining table and the
# coffee table are genuinely one design at two proportions today - the
# manifest's ShelfHeight is what distinguishes them. When a real difference
# appears, it belongs here rather than as another branch in _shared.table.

from .. import _shared


def build(params, assets, ctx):
    """Build the dining table and report its derived seating capacity.

    SeatCount is derived from Width and reported rather than built: the
    table has no per-seat geometry, but the number is what a user picks by.
    """
    width = float(params.get("Width", 1200))
    seat_count = params.get("SeatCount")
    if seat_count is None:
        # 500mm of table edge per diner, both long sides laid: 1200 seats 4,
        # 1600 seats 6, 2000 seats 8.
        seat_count = 2 * int(width // 500)
    seat_count = max(int(seat_count), 2)
    return _shared.table(params, assets, ctx)
