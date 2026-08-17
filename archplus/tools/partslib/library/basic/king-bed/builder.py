# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A king bed: the family's divan-based bed with a panelled headboard.
#
# Delegates to the shared bed - king and single are one design at two
# mattress widths today. A real per-size difference goes here.

from .. import _shared


def build(params, assets, ctx):
    return _shared.bed(params, assets, ctx)
