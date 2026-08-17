# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the shared ArchPlus spec-persistence helpers, extracted from the
# byte-identical copies that lived in the Doors and Windows panels.

from archplus.common import spec


def test_store_then_read_round_trips(fake_obj):
    payload = {"operation": "Single swing", "width": 900}
    spec.storeSpec(fake_obj, payload)
    assert spec.readSpec(fake_obj) == payload


def test_store_creates_the_property_when_it_is_absent(fake_obj):
    assert not hasattr(fake_obj, spec.SPEC_PROP)
    spec.storeSpec(fake_obj, {"a": 1})
    assert hasattr(fake_obj, spec.SPEC_PROP)


def test_store_on_none_is_a_no_op():
    spec.storeSpec(None, {"a": 1})   # must not raise


def test_read_returns_none_when_nothing_was_stored(fake_obj):
    assert spec.readSpec(fake_obj) is None


def test_read_returns_none_on_malformed_json(fake_obj):
    setattr(fake_obj, spec.SPEC_PROP, "{not json")
    assert spec.readSpec(fake_obj) is None


def test_read_returns_none_when_the_json_is_not_a_dict(fake_obj):
    setattr(fake_obj, spec.SPEC_PROP, "[1, 2, 3]")
    assert spec.readSpec(fake_obj) is None
