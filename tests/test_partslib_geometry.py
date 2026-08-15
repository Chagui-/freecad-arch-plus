import pytest

import partslib_geometry as pg


@pytest.mark.parametrize("symbol", [
    "asset",                      # no function part
    "",                           # empty
    "asset.single.extra",         # too many parts
    "../evil.run",                # path traversal
    "/abs/path.run",              # absolute path
    "partslib_builders.asset.single",  # package prefix not allowed
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
    loader = pg.AssetLoader("/some/part/dir", {"body": "../evil.brep"})
    with pytest.raises(ValueError):
        loader.shape("body")


def test_backslash_traversal_asset_name_is_rejected():
    loader = pg.AssetLoader("/some/part/dir", {"body": "..\\evil.brep"})
    with pytest.raises(ValueError):
        loader.shape("body")


def test_absolute_asset_path_is_rejected():
    loader = pg.AssetLoader("/some/part/dir", {"body": "/abs/path.step"})
    with pytest.raises(ValueError):
        loader.shape("body")


def test_contained_asset_name_is_not_rejected_by_containment_check(
        tmp_path, monkeypatch):
    (tmp_path / "body.brep").write_bytes(b"")
    loader = pg.AssetLoader(str(tmp_path), {"body": "body.brep"})
    monkeypatch.setattr(loader, "_read", lambda source: "stub-shape")
    assert loader.shape("body") == "stub-shape"
