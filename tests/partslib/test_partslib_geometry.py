import pytest

from partslib import geometry as pg


@pytest.mark.parametrize("symbol", [
    "asset",                      # no function part
    "",                           # empty
    "asset.single.extra",         # too many parts
    "../evil.run",                # path traversal
    "/abs/path.run",              # absolute path
    "partslib.builders.asset.single",  # package prefix not allowed
])
def test_malformed_builder_symbols_are_rejected(symbol):
    with pytest.raises(ValueError):
        pg.resolve_builder(symbol)


def test_unknown_builder_module_is_rejected():
    with pytest.raises(ValueError):
        pg.resolve_builder("nosuchmodule.single")


def test_unknown_builder_function_is_rejected():
    with pytest.raises(ValueError):
        pg.resolve_builder("asset.nosuchfunction")


def test_stock_asset_builder_resolves():
    assert callable(pg.resolve_builder("asset.single"))


def test_demo_builder_resolves():
    assert callable(pg.resolve_builder("demo.box"))


def test_dunder_attribute_is_not_resolved_as_a_builder():
    with pytest.raises(ValueError):
        pg.resolve_builder("asset.__class__")


def test_dunder_init_is_not_resolved_as_a_builder():
    with pytest.raises(ValueError):
        pg.resolve_builder("asset.__init__")


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


def _manifest(builder="demo.box", params=None, variant=None):
    data = {
        "geometry": {"builder": builder},
        "params": params or {"Width": {"type": "Length", "default": 100}},
    }
    if variant is not None:
        data["variantLabel"] = variant
    return data


def _patched_builder(monkeypatch, calls):
    def _build(params, assets, ctx):
        calls.append(dict(params))
        return _CountingShape(len(calls))

    monkeypatch.setattr(pg, "resolve_builder", lambda symbol: _build)
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
