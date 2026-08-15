import partslib_manifest as pm

FACETS = {
    "function": {"label": "Function", "multi": False,
                 "values": {"Sanitary": {}, "Seating": {}}},
    "element": {"label": "Element", "multi": False,
                "values": {"WC": {"ifcType": "Sanitary Terminal"},
                           "Chair": {"ifcType": "Furniture"}}},
    "room": {"label": "Room", "multi": True,
             "values": {"Bathroom": {}, "Kitchen": {}}},
}


def test_core_module_does_not_import_freecad():
    import inspect
    src = inspect.getsource(pm)
    for banned in ("import FreeCAD", "import Part", "from PySide"):
        assert banned not in src


def test_valid_vocabulary_has_no_errors():
    assert pm.validate_facets(FACETS) == []


def test_facet_without_values_is_an_error():
    errors = pm.validate_facets({"function": {"label": "Function"}})
    assert any("values" in e for e in errors)


def test_facet_values_must_be_a_mapping():
    errors = pm.validate_facets({"function": {"values": ["Sanitary"]}})
    assert any("values" in e for e in errors)


def test_multi_defaults_to_false():
    assert pm.facet_is_multi(FACETS, "element") is False
    assert pm.facet_is_multi(FACETS, "room") is True


def test_facet_values_are_listed_sorted():
    assert pm.facet_values(FACETS, "room") == ["Bathroom", "Kitchen"]


import json

import pytest


def _part(**over):
    data = {
        "schema": 1,
        "id": "wc-geberit-icon",
        "name": "Wall-hung WC",
        "facets": {"function": "Sanitary", "element": "WC",
                   "room": ["Bathroom"]},
        "geometry": {"builder": "asset.single",
                     "assets": {"body": "wc-360.brep"}},
    }
    data.update(over)
    return data


def test_valid_manifest_has_no_errors():
    errors, warnings = pm.validate_manifest(_part(), FACETS)
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("field", ["schema", "id", "name", "facets", "geometry"])
def test_missing_required_field_is_an_error(field):
    data = _part()
    del data[field]
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any(field in e for e in errors)


def test_future_schema_version_is_an_error():
    errors, _ = pm.validate_manifest(_part(schema=2), FACETS)
    assert any("schema" in e for e in errors)


def test_id_must_be_a_lowercase_slug():
    errors, _ = pm.validate_manifest(_part(id="WC Geberit"), FACETS)
    assert any("id" in e for e in errors)


def test_unknown_facet_is_an_error():
    data = _part(facets={"function": "Sanitary", "colour": "Blue"})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any("colour" in e for e in errors)


def test_unknown_facet_value_is_an_error():
    data = _part(facets={"function": "Plumbing"})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any("Plumbing" in e for e in errors)


def test_list_value_on_single_valued_facet_is_an_error():
    data = _part(facets={"function": ["Sanitary", "Seating"]})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert any("function" in e for e in errors)


def test_multi_valued_facet_accepts_a_bare_string():
    data = _part(facets={"function": "Sanitary", "room": "Bathroom"})
    errors, _ = pm.validate_manifest(data, FACETS)
    assert errors == []


def test_geometry_without_builder_is_an_error():
    errors, _ = pm.validate_manifest(_part(geometry={}), FACETS)
    assert any("builder" in e for e in errors)


def test_unknown_top_level_field_is_a_warning_not_an_error():
    errors, warnings = pm.validate_manifest(_part(futureField=1), FACETS)
    assert errors == []
    assert any("futureField" in w for w in warnings)


def test_load_manifest_reads_json(tmp_path):
    path = tmp_path / "part.json"
    path.write_text(json.dumps(_part()), encoding="utf8")
    assert pm.load_manifest(str(path))["id"] == "wc-geberit-icon"


def test_load_manifest_raises_on_bad_json(tmp_path):
    path = tmp_path / "part.json"
    path.write_text("{not json", encoding="utf8")
    with pytest.raises(ValueError):
        pm.load_manifest(str(path))


def _part_with_variants():
    return _part(
        params={"Width": {"type": "Length", "default": 360}},
        ifcProperties={"Manufacturer": "Pset_X;;IfcLabel;;Geberit"},
        variants=[
            {"label": "360 mm",
             "assets": {"body": "wc-360.brep"},
             "ifcProperties": {"ModelReference": "Pset_X;;IfcLabel;;204060"}},
            {"label": "490 mm",
             "assets": {"body": "wc-490.brep"},
             "params": {"Width": {"type": "Length", "default": 490}},
             "ifcProperties": {"ModelReference": "Pset_X;;IfcLabel;;204070"}},
        ])


def test_part_without_variants_has_one_default():
    assert pm.variant_labels(_part()) == ["Default"]


def test_variant_labels_are_listed_in_declared_order():
    assert pm.variant_labels(_part_with_variants()) == ["360 mm", "490 mm"]


def test_resolving_default_variant_returns_the_part_unchanged():
    resolved = pm.resolve_variant(_part(), "Default")
    assert resolved["geometry"]["assets"] == {"body": "wc-360.brep"}


def test_variant_assets_override_part_assets():
    resolved = pm.resolve_variant(_part_with_variants(), "490 mm")
    assert resolved["geometry"]["assets"] == {"body": "wc-490.brep"}


def test_variant_ifc_properties_merge_over_part_level():
    resolved = pm.resolve_variant(_part_with_variants(), "360 mm")
    assert resolved["ifcProperties"]["Manufacturer"] == "Pset_X;;IfcLabel;;Geberit"
    assert resolved["ifcProperties"]["ModelReference"] == "Pset_X;;IfcLabel;;204060"


def test_variant_params_override_part_params():
    resolved = pm.resolve_variant(_part_with_variants(), "490 mm")
    assert resolved["params"]["Width"]["default"] == 490


def test_resolving_leaves_the_original_manifest_untouched():
    data = _part_with_variants()
    pm.resolve_variant(data, "490 mm")
    assert data["geometry"]["assets"] == {"body": "wc-360.brep"}


def test_unknown_variant_label_raises():
    with pytest.raises(KeyError):
        pm.resolve_variant(_part_with_variants(), "999 mm")


def test_explicit_ifc_type_wins():
    data = _part(ifcType="Furniture")
    assert pm.resolve_ifc_type(data, FACETS) == "Furniture"


def test_ifc_type_comes_from_element_facet():
    assert pm.resolve_ifc_type(_part(), FACETS) == "Sanitary Terminal"


def test_ifc_type_falls_back_to_function_facet():
    facets = {"function": {"values": {"Seating": {"ifcType": "Furniture"}}}}
    data = _part(facets={"function": "Seating"})
    assert pm.resolve_ifc_type(data, facets) == "Furniture"


def test_ifc_type_falls_back_to_the_default():
    facets = {"function": {"values": {"Seating": {}}}}
    data = _part(facets={"function": "Seating"})
    assert pm.resolve_ifc_type(data, facets) == pm.DEFAULT_IFC_TYPE
