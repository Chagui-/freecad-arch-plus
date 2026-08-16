import pytest

from partslib import placement as pp


def test_missing_placement_block_defaults_to_free():
    assert pp.host_of({}) == "free"
    assert pp.offset_of({}) == 0.0


def test_host_and_offset_are_read_from_the_manifest():
    resolved = {"placement": {"host": "wall", "offset": 400}}
    assert pp.host_of(resolved) == "wall"
    assert pp.offset_of(resolved) == 400.0


def test_unknown_host_falls_back_to_free():
    assert pp.host_of({"placement": {"host": "moon"}}) == "free"


@pytest.mark.parametrize("host,sign", [
    ("wall", 1.0), ("floor", 1.0), ("ceiling", -1.0), ("free", 0.0)])
def test_offset_direction_per_host(host, sign):
    assert pp.offset_sign(host) == sign


def test_every_host_has_a_sign():
    for host in pp.HOSTS:
        assert pp.offset_sign(host) in (-1.0, 0.0, 1.0)
