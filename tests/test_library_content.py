# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Verifies the REAL bundled seed library (library/ at the repo root), not a
# tmp_path fixture. A malformed shipped manifest would otherwise reach a user
# as a silently empty panel with a console error nobody reads, so this test
# is the headless substitute for eyeballing the panel inside FreeCAD.
#
# Deliberately does NOT import partslib_object - it imports FreeCAD at module
# scope and would fail under plain pytest.

import os

import partslib_geometry
import partslib_index
import partslib_manifest

LIBRARY_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "library")

EXPECTED_PART_IDS = {"base-cabinet", "wc-demo"}


def _scan():
    return partslib_index.scan(LIBRARY_DIR)


def test_scan_reports_zero_errors_for_the_shipped_library():
    index = _scan()
    assert index["errors"] == []


def test_both_seed_part_ids_are_present():
    index = _scan()
    ids = {entry["id"] for entry in index["entries"]}
    assert EXPECTED_PART_IDS <= ids


def test_every_entry_facet_value_exists_in_the_shipped_vocabulary():
    # Safety net, not an independent check today: validate_manifest() already
    # gates entry inclusion in scan(), so a part with a facet value outside
    # the vocabulary never reaches index["entries"] at all - it is excluded
    # and reported as a scan error first, which
    # test_scan_reports_zero_errors_for_the_shipped_library already catches.
    # This test only earns its keep if entry-inclusion and error-reporting
    # are ever decoupled from each other in a future refactor.
    index = _scan()
    facets = index["facets"]
    for entry in index["entries"]:
        for facet_name, value in (entry.get("facets") or {}).items():
            assert facet_name in facets, (
                "entry %r declares unknown facet %r" % (entry["id"], facet_name))
            allowed = partslib_manifest.facet_values(facets, facet_name)
            values = value if isinstance(value, list) else [value]
            for item in values:
                assert item in allowed, (
                    "entry %r declares unknown value %r for facet %r"
                    % (entry["id"], item, facet_name))


def test_every_entry_geometry_builder_resolves():
    index = _scan()
    for entry in index["entries"]:
        manifest = partslib_manifest.load_manifest(entry["path"])
        builder_symbol = manifest.get("geometry", {}).get("builder")
        # Must not raise.
        partslib_geometry.resolve_builder(builder_symbol)


def test_every_part_variant_labels_are_non_empty_and_unique():
    index = _scan()
    for entry in index["entries"]:
        labels = entry["variants"]
        assert labels, "entry %r has no variant labels at all" % (entry["id"],)
        for label in labels:
            assert label, "entry %r has an empty variant label" % (entry["id"],)
        assert len(labels) == len(set(labels)), (
            "entry %r has duplicate variant labels: %r" % (entry["id"], labels))
