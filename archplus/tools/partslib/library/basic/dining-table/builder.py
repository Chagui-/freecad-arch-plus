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
    return _shared.table(params, assets, ctx)
