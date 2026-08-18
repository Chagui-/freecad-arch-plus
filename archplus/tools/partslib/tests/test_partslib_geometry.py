import os
import sys

import pytest

from archplus.tools.partslib import geometry as pg


def test_forward_slash_traversal_asset_name_is_rejected():
    # Must be the containment rejection specifically, not the unrelated
    # "missing asset file" ValueError a broken check could fall through to.
    loader = pg.AssetLoader("/some/part/dir", {"body": "../evil.brep"})
    with pytest.raises(ValueError, match="inside the part folder"):
        loader.shape("body")


def test_backslash_traversal_asset_name_is_rejected():
    # Same as above, with the other OS's separator - proves the fix does not
    # only catch the host's native os.sep.
    loader = pg.AssetLoader("/some/part/dir", {"body": "..\\evil.brep"})
    with pytest.raises(ValueError, match="inside the part folder"):
        loader.shape("body")


def test_absolute_asset_path_is_rejected():
    loader = pg.AssetLoader("/some/part/dir", {"body": "/abs/path.step"})
    with pytest.raises(ValueError, match="inside the part folder"):
        loader.shape("body")


def test_contained_asset_name_is_not_rejected_by_containment_check(
        tmp_path, monkeypatch):
    # A real file under tmp_path, so shape() runs past the isabs/segment/
    # commonpath containment checks and reaches os.path.exists() rather than
    # short-circuiting there - the missing-asset-file ValueError is a
    # different code path from the containment check under test, and this is
    # what keeps the two from being confused. _read is stubbed only because
    # actually parsing a .brep needs FreeCAD/Part, which this test does not
    # have and does not need: it is not what is being verified here.
    (tmp_path / "body.brep").write_bytes(b"")
    loader = pg.AssetLoader(str(tmp_path), {"body": "body.brep"})
    monkeypatch.setattr(loader, "_read", lambda source: "stub-shape")
    try:
        result = loader.shape("body")
    except ValueError as exc:
        assert "inside the part folder" not in str(exc), (
            "a legitimate, contained asset name must not trip the "
            "containment check: %s" % (exc,))
        raise
    assert result == "stub-shape"


# -- shape cache ------------------------------------------------------------

class _CountingShape:
    """Stands in for a Part.Shape: knows only how to copy itself."""

    def __init__(self, tag):
        self.tag = tag
        self.copies = 0

    def copy(self):
        self.copies += 1
        clone = _CountingShape(self.tag)
        clone.origin = self
        return clone


@pytest.fixture(autouse=True)
def _clean_shape_cache():
    pg.clear_shape_cache()
    yield
    pg.clear_shape_cache()


def _manifest(params=None, variant=None):
    data = {
        "geometry": {},
        "params": params or {"Width": {"type": "Length", "default": 100}},
    }
    if variant is not None:
        data["variantLabel"] = variant
    return data


def _patched_builder(monkeypatch, calls):
    def _build(params, assets, ctx):
        calls.append(dict(params))
        return _CountingShape(len(calls))

    monkeypatch.setattr(pg, "select_builder",
                        lambda resolved, part_dir: _build)
    return calls


def test_identical_builds_hit_the_cache(tmp_path, monkeypatch):
    calls = _patched_builder(monkeypatch, [])
    pg.build_shape(_manifest(), str(tmp_path))
    pg.build_shape(_manifest(), str(tmp_path))
    assert len(calls) == 1


def test_the_cache_returns_a_copy_not_the_stored_shape(tmp_path, monkeypatch):
    # A shape handed to a document object becomes that object's. Returning
    # the cached instance itself would let one caller's mutation corrupt
    # every later hit.
    _patched_builder(monkeypatch, [])
    first = pg.build_shape(_manifest(), str(tmp_path))
    second = pg.build_shape(_manifest(), str(tmp_path))
    assert first is not second


def test_different_params_miss_the_cache(tmp_path, monkeypatch):
    calls = _patched_builder(monkeypatch, [])
    pg.build_shape(_manifest(), str(tmp_path))
    pg.build_shape(_manifest(), str(tmp_path),
                   overrides={"Width": 250})
    assert len(calls) == 2
    assert calls[1]["Width"] == 250


def test_different_variants_miss_the_cache(tmp_path, monkeypatch):
    calls = _patched_builder(monkeypatch, [])
    pg.build_shape(_manifest(variant="Small"), str(tmp_path))
    pg.build_shape(_manifest(variant="Large"), str(tmp_path))
    assert len(calls) == 2


def test_different_parts_miss_the_cache(tmp_path, monkeypatch):
    calls = _patched_builder(monkeypatch, [])
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    pg.build_shape(_manifest(), str(tmp_path / "a"))
    pg.build_shape(_manifest(), str(tmp_path / "b"))
    assert len(calls) == 2


def test_two_builders_sharing_a_module_do_not_share_a_cache_entry(
        tmp_path, monkeypatch):
    # Regression: two builder functions defined in the SAME module (e.g. two
    # kitchen.* functions such as base_cabinet and wall_cabinet) must not
    # collide on __module__ alone. A manifest edited to point at a sibling
    # function in the same module, with identical part_dir/params/variant,
    # must still get the SIBLING's shape - not the first function's stale
    # cache entry.
    def builder_one(params, assets, ctx):
        return _CountingShape("one")

    def builder_two(params, assets, ctx):
        return _CountingShape("two")

    builders = [builder_one, builder_two]
    monkeypatch.setattr(
        pg, "select_builder", lambda resolved, part_dir: builders.pop(0))

    first = pg.build_shape(_manifest(), str(tmp_path))
    second = pg.build_shape(_manifest(), str(tmp_path))

    assert first.tag == "one"
    assert second.tag == "two"


def test_clearing_the_cache_forces_a_rebuild(tmp_path, monkeypatch):
    calls = _patched_builder(monkeypatch, [])
    pg.build_shape(_manifest(), str(tmp_path))
    pg.clear_shape_cache()
    pg.build_shape(_manifest(), str(tmp_path))
    assert len(calls) == 2


def test_the_cache_is_bounded(tmp_path, monkeypatch):
    _patched_builder(monkeypatch, [])
    for i in range(pg._SHAPE_CACHE_LIMIT + 20):
        pg.build_shape(_manifest(params={
            "Width": {"type": "Length", "default": i}}), str(tmp_path))
    assert len(pg._SHAPE_CACHE) <= pg._SHAPE_CACHE_LIMIT


# -- local builder resolution ------------------------------------------------

@pytest.fixture
def fixture_library(tmp_path, monkeypatch):
    """A throwaway library root that is importable as a namespace package.

    Points geometry at tmp_path instead of the shipped library, so these
    tests never create or delete files under library/. tmp_path goes on
    sys.path so the fixture root imports as a top-level namespace package -
    no __init__.py anywhere, which is exactly how library/ works.
    """
    root = tmp_path / "fixturelib"
    root.mkdir()
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(pg, "LIBRARY_DIR", str(root))
    monkeypatch.setattr(pg, "LIBRARY_PACKAGE", "fixturelib")
    yield root
    for name in [n for n in list(sys.modules)
                 if n == "fixturelib" or n.startswith("fixturelib.")]:
        del sys.modules[name]


def _write_builder(part_dir, body="    return 'built'"):
    part_dir.mkdir(parents=True, exist_ok=True)
    (part_dir / "builder.py").write_text(
        "def build(params, assets, ctx):\n%s\n" % body)


def test_a_local_builder_resolves(fixture_library):
    part = fixture_library / "basic" / "television"
    _write_builder(part)

    builder = pg.load_local_builder(str(part))

    assert builder(None, None, None) == "built"


def test_a_local_builder_resolves_for_a_standalone_part(fixture_library):
    # One-off imports sit at the library root, so a one-segment path must
    # resolve too.
    part = fixture_library / "geberit-icon"
    _write_builder(part)

    assert callable(pg.load_local_builder(str(part)))


def test_a_part_directory_outside_the_library_is_rejected(
        fixture_library, tmp_path):
    outside = tmp_path / "elsewhere" / "evil"
    _write_builder(outside)

    with pytest.raises(ValueError):
        pg.load_local_builder(str(outside))


def test_the_library_root_itself_is_not_a_part(fixture_library):
    with pytest.raises(ValueError):
        pg.load_local_builder(str(fixture_library))


def test_a_dot_in_a_path_segment_is_rejected(fixture_library):
    part = fixture_library / "basic" / "55.inch"
    _write_builder(part)

    with pytest.raises(ValueError):
        pg.load_local_builder(str(part))


def test_a_builder_module_without_build_is_rejected(fixture_library):
    part = fixture_library / "basic" / "nobuild"
    part.mkdir(parents=True)
    (part / "builder.py").write_text("def make(params, assets, ctx):\n    pass\n")

    with pytest.raises(ValueError):
        pg.load_local_builder(str(part))


def test_an_imported_name_is_not_accepted_as_build(fixture_library):
    # `build` must be DEFINED here, not pulled in from elsewhere, so a
    # star-import cannot smuggle in a callable.
    part = fixture_library / "basic" / "imported"
    part.mkdir(parents=True)
    (part / "builder.py").write_text("from os.path import join as build\n")

    with pytest.raises(ValueError):
        pg.load_local_builder(str(part))


def test_has_local_builder_reports_file_presence(fixture_library):
    with_file = fixture_library / "basic" / "has-one"
    _write_builder(with_file)
    without = fixture_library / "basic" / "has-none"
    without.mkdir(parents=True)

    assert pg.has_local_builder(str(with_file)) is True
    assert pg.has_local_builder(str(without)) is False


def test_a_part_without_a_builder_py_falls_back_to_the_asset_builder(
        fixture_library):
    # A part shipping no code at all IS an asset-only part. The absence of
    # builder.py is the guarantee, rather than a manifest string claiming it.
    from archplus.tools.partslib import asset

    part = fixture_library / "basic" / "vendor-chair"
    part.mkdir(parents=True)

    assert pg.select_builder({"geometry": {}}, str(part)) is asset.single


def test_a_manifest_builder_symbol_is_ignored(fixture_library):
    # The field is gone from the schema; a stale one must not resurrect a
    # resolution path that no longer exists.
    from archplus.tools.partslib import asset

    part = fixture_library / "basic" / "vendor-chair"
    part.mkdir(parents=True)

    resolved = {"geometry": {"builder": "anything.at.all"}}

    assert pg.select_builder(resolved, str(part)) is asset.single


def test_clearing_the_cache_forgets_imported_library_builders(fixture_library):
    part = fixture_library / "basic" / "editable"
    _write_builder(part, "    return 'first'")

    assert pg.load_local_builder(str(part))(None, None, None) == "first"

    (part / "builder.py").write_text(
        "def build(params, assets, ctx):\n    return 'second'\n")
    # Without the sys.modules purge the edit is invisible for the rest of
    # the session, which is the whole point of this call.
    pg.clear_shape_cache()

    assert pg.load_local_builder(str(part))(None, None, None) == "second"
