# Task 7 report: delete `variants`

## Result

Task 7 is implemented. The manifest schema now rejects any manifest carrying
`variants` as a hard validation error, and does not also report it as an
ignored unknown-field warning. The variant resolver API and default label were
removed. Index entries now carry `params` and no `variants`; `CACHE_VERSION` is
2, so version-1 caches are rejected.

The headless manifest and index modules remain free of FreeCAD, Part, and
PySide imports.

## Tests

The exact full-suite count before the change was:

- `233 passed in 33.14s`

The exact full-suite count after the change was:

- `225 passed in 32.14s`

Command used:

    uvx --with pytest pytest archplus -q

Tests deleted:

- `test_part_without_variants_has_one_default`
- `test_variant_labels_are_listed_in_declared_order`
- `test_resolving_default_variant_returns_the_part_unchanged`
- `test_variant_assets_override_part_assets`
- `test_variant_ifc_properties_merge_over_part_level`
- `test_variant_params_override_part_params`
- `test_variant_placement_overrides_the_part_placement`
- `test_variant_placement_merges_per_key`
- `test_resolving_leaves_the_original_manifest_untouched`
- `test_unknown_variant_label_raises`
- `test_scan_records_variant_labels`
- `test_every_part_variant_labels_are_non_empty_and_unique`

The two `param_specs` tests were retained and rewritten to use plain
manifests. The library placement tests were also retained and rewritten to
read the manifest directly rather than resolve a variant. New coverage checks
that a manifest declaring `variants` is rejected, that it is not downgraded to
an unknown-field warning, that index entries carry `params`, and that a
version-1 cache is rejected.

## Deliberately broken downstream call sites

Per the task brief, `object.py` and `gui.py` were not repaired, shimmed, or
made compatible. Task 8 and Task 9 are responsible for those rewrites.

In `archplus/tools/partslib/object.py`, the deliberately broken call sites
are:

- around lines 214 and 216: `resolve_variant` and `DEFAULT_VARIANT_LABEL`
- around lines 242 and 244: `resolve_variant` and `DEFAULT_VARIANT_LABEL`
- around lines 329 and 331: `variant_labels` and `resolve_variant`
- around lines 375 and 381: `variant_labels` and its `resolve_variant` error-path comment
- around line 406: `resolve_variant`

In `archplus/tools/partslib/gui.py`, the deliberately broken call sites are:

- around lines 839-844: reads `entry["variants"]` for the display label
- around lines 923-924: `resolve_variant` using `entry["variants"][0]`
- around line 968: reads `entry["variants"]` for variant chips
- around lines 1066-1067: reads `entry["variants"]` and calls `resolve_variant`
- around line 1099: reads `entry["variants"]`
- around line 1267: reads `entry["variants"]`

These files were intentionally left broken because they import FreeCAD or
PySide and are not exercised by the headless suite.
