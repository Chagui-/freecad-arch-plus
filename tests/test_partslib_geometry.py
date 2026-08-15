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
