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
