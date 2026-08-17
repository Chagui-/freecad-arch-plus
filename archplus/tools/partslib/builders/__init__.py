# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Curated part builders. Every builder in this package is repo code, reviewed
# alongside the rest of ArchPlus. Manifests reference builders by symbol
# ("module.function") and can never name a path or an import target outside
# this package - that is what keeps a manifest from executing arbitrary code.
#
# Builder contract:
#     def build(params, assets, ctx) -> Part.Shape
