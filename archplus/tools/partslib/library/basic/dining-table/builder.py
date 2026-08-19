# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A dining table: the family's apron-framed table at seating height.
#
# This delegates rather than duplicating because the dining table and the
# coffee table are genuinely one design at two proportions today - the
# shelf and the apron are what distinguish them. When a real difference
# appears, it belongs here rather than as another branch in _shared.table.

from .. import _shared


def build(params, assets, ctx):
    """Build the dining table."""
    # A heavier leg than the shared default: a dining table carries more
    # and reads as more substantial.
    return _shared.table(params, assets, ctx, leg_radius=35.0)
