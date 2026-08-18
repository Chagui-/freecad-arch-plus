# Task 3 report: kitchen and sanitary coupled parts

## Status

Implemented Task 3 for base-cabinet, wall-cabinet, wardrobe, gas-hob, and vanity.

## TDD evidence

RED: ran `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q` after adding Steps 1-2 tests and before migrating the manifests. Result: `2 failed, 13 passed`; the new auto-parameter test failed because the manifests did not yet declare the coupled parameters as `"auto"` (the repository's scanned IDs also exposed the `basic/` prefix mismatch described below).

GREEN after manifest and builder migration: ran `uvx --with pytest pytest archplus/tools/partslib/tests/test_library_content.py -q`. Result: `15 passed`.

GREEN after adding the Step 6 source-inspection guard: ran the same command. Result: `16 passed`.

Final suite: ran `uvx --with pytest pytest archplus -q`. Result: `222 passed`.

## Manifest changes

Each of the five manifests no longer declares `variants`. Primary parameters and coupled defaults match the brief. The coupled parameters are declared with `"default": "auto"`:

- base-cabinet: DoorCount
- wall-cabinet: DoorCount
- wardrobe: DoorCount
- gas-hob: Width
- vanity: BasinWidth

## Builder ordering evidence

The derived variable is defined before its first use in each builder:

- base-cabinet/builder.py: `door_count` derives from `width`; `width` is defined at line 15.
- wall-cabinet/builder.py: `door_count` derives from `width`; `width` is defined at line 17.
- wardrobe/builder.py: `door_count` derives from `width`; `width` is defined at line 11.
- gas-hob/builder.py: `width` derives from `burner_count`; `burner_count` is defined at line 17, before `width` at line 18. There is exactly one `burner_count =` assignment.
- vanity/builder.py: `basin_width` derives from `width`; `width` is defined at line 14.

All five builders retain FreeCAD/Part imports only inside `build()`.

## Test helper compatibility note

The brief's helper calls use bare IDs such as `base-cabinet`, while this repository's index derives shipped IDs as `basic/base-cabinet` from the required folder layout. `_entry()` therefore accepts the exact bare IDs from the brief and resolves the repository's `basic/`-prefixed IDs; no production index behavior was changed.

## Files

Modified manifests and builders under `archplus/tools/partslib/library/basic/`, plus `archplus/tools/partslib/tests/test_library_content.py`.
