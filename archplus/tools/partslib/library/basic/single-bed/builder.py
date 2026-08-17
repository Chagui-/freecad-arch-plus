# SPDX-License-Identifier: LGPL-2.1-or-later
#
# A single bed: the family's divan-based bed with a panelled headboard.
#
# Delegates to the shared bed for the same reason king-bed does.

from .. import _shared


def build(params, assets, ctx):
    return _shared.bed(params, assets, ctx)
