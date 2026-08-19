# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A coffee table: the family's apron-framed table, low, with a lower shelf.
#
# Delegates to the shared table for the same reason dining-table does; the
# manifest's non-zero ShelfHeight is the only thing separating them today.

from .. import _shared


def build(params, assets, ctx):
    # A shallower apron and a lower shelf are what make this a coffee
    # table rather than a short dining table.
    return _shared.table(params, assets, ctx,
                         apron_height=55.0, shelf_height=120.0)
