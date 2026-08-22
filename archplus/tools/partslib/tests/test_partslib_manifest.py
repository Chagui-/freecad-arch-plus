from archplus.tools.partslib import manifest as pm

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


# -- facet_label / facet_icon -----------------------------------------------

def test_facet_label_returns_the_declared_label():
    facets = {"element": {"values": {"WC": {"label": "Toilets"}}}}
    assert pm.facet_label(facets, "element", "WC") == "Toilets"


def test_facet_label_falls_back_to_the_value():
    facets = {"element": {"values": {"WC": {}}}}
    assert pm.facet_label(facets, "element", "WC") == "WC"


def test_facet_icon_returns_the_declared_filename():
    facets = {"element": {"values": {"WC": {"icon": "wc.svg"}}}}
    assert pm.facet_icon(facets, "element", "WC") == "wc.svg"


def test_facet_icon_absent_returns_none():
    facets = {"element": {"values": {"WC": {}}}}
    assert pm.facet_icon(facets, "element", "WC") is None


def test_valid_label_and_icon_have_no_validation_errors():
    doc = {"element": {"values": {"WC": {"label": "Toilets", "icon": "wc.svg"}}}}
    assert pm.validate_facets(doc) == []


def test_non_string_label_is_a_validation_error():
    doc = {"element": {"values": {"WC": {"label": 5}}}}
    errors = pm.validate_facets(doc)
    assert any("label" in e for e in errors)


def test_icon_with_a_forward_slash_is_a_validation_error():
    doc = {"element": {"values": {"WC": {"icon": "icons/wc.svg"}}}}
    errors = pm.validate_facets(doc)
    assert any("icon" in e for e in errors)


def test_icon_with_a_backslash_is_a_validation_error():
    doc = {"element": {"values": {"WC": {"icon": "icons\\wc.svg"}}}}
    errors = pm.validate_facets(doc)
    assert any("icon" in e for e in errors)


def test_icon_with_dotdot_is_a_validation_error():
    doc = {"element": {"values": {"WC": {"icon": "../wc.svg"}}}}
    errors = pm.validate_facets(doc)
    assert any("icon" in e for e in errors)


def test_absolute_icon_path_is_a_validation_error():
    doc = {"element": {"values": {"WC": {"icon": "/etc/wc.svg"}}}}
    errors = pm.validate_facets(doc)
    assert any("icon" in e for e in errors)


import json

import pytest


def _part(**over):
    data = {
        "schema": 1,
        "id": "wc-geberit-icon",
        "name": "Wall-hung WC",
        "facets": {"function": "Sanitary", "element": "WC",
                   "room": ["Bathroom"]},
        "geometry": {"assets": {"body": "wc-360.brep"}},
    }
    data.update(over)
    return data


def test_valid_manifest_has_no_errors():
    errors, warnings = pm.validate_manifest(_part(), FACETS)
    assert errors == []
    assert warnings == []


@pytest.mark.parametrize("field", ["schema", "name", "facets", "geometry"])
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


def test_geometry_with_no_builder_field_is_not_an_error():
    # The field is gone from the schema: which code runs is decided by
    # whether the part folder holds a builder.py, not by anything named here.
    errors, _ = pm.validate_manifest(_part(geometry={}), FACETS)
    assert errors == []


def test_non_object_geometry_is_an_error():
    errors, _ = pm.validate_manifest(_part(geometry="nope"), FACETS)
    assert any("geometry" in e for e in errors)


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


def test_a_manifest_declaring_variants_is_rejected():
    data = _part_with_ui()
    data["variants"] = [{"label": "800 mm"}]
    errors, _warnings = pm.validate_manifest(data, {})
    assert any("variants" in error for error in errors)


def test_variants_is_an_error_not_an_ignored_unknown_field():
    data = _part_with_ui()
    data["variants"] = []
    errors, warnings = pm.validate_manifest(data, {})
    assert any("variants" in error for error in errors)
    assert not any("variants" in warning for warning in warnings)


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


# -- param_specs / merge_params ---------------------------------------------

def _part_with_params():
    return _part(params={"Width": {"type": "Length", "default": 490}})


def test_param_specs_returns_the_declared_params_block():
    assert pm.param_specs(_part_with_ui())["Width"] == {
        "type": "Length", "default": 600, "ui": "primary"}


def test_param_specs_is_empty_when_params_block_absent():
    assert pm.param_specs({"schema": 1, "name": "X"}) == {}


def test_merge_params_uses_declared_defaults_with_no_overrides():
    manifest = _part_with_params()
    assert pm.merge_params(manifest, None) == {"Width": 490}
    assert pm.merge_params(manifest, {}) == {"Width": 490}


def test_merge_params_override_replaces_the_default():
    manifest = _part_with_params()
    assert pm.merge_params(manifest, {"Width": 750}) == {"Width": 750}


def test_merge_params_none_override_falls_back_to_default():
    manifest = _part_with_params()
    assert pm.merge_params(manifest, {"Width": None}) == {"Width": 490}


def test_merge_params_ignores_an_undeclared_override():
    manifest = _part_with_params()
    merged = pm.merge_params(manifest, {"Width": 750, "Bogus": 42})
    assert merged == {"Width": 750}
    assert "Bogus" not in merged


def test_merge_params_with_no_params_block_is_empty():
    resolved = _part()
    assert pm.merge_params(resolved, {"Width": 750}) == {}


def test_a_path_shaped_id_is_valid():
    assert pm.validate_part_id("basic/coffee-table") == []


def test_a_single_segment_id_is_valid():
    # A standalone part - one reserved for future one-off imports - sits at
    # the library root and so has a one-segment id.
    assert pm.validate_part_id("geberit-icon") == []


def test_an_uppercase_id_segment_is_rejected():
    assert pm.validate_part_id("basic/Coffee-Table") != []


def test_an_underscore_id_segment_is_rejected():
    assert pm.validate_part_id("basic/coffee_table") != []


def test_an_id_segment_containing_a_dot_is_rejected():
    # A dot would split the dotted import path used to load builder.py.
    assert pm.validate_part_id("basic/55.inch") != []


def test_an_empty_id_is_rejected():
    assert pm.validate_part_id("") != []


def test_a_manifest_without_an_id_is_valid():
    # The id is derived from the folder; only an explicit override is checked.
    data = _part()
    del data["id"]
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert [e for e in errors if "id" in e] == []


# -- primary_params ---------------------------------------------------------

def _part_with_ui():
    return {
        "schema": 1, "name": "Cabinet",
        "facets": {}, "geometry": {},
        "params": {
            "Width": {"type": "Length", "default": 600, "ui": "primary"},
            "Depth": {"type": "Length", "default": 600, "ui": "primary"},
            "KickHeight": {"type": "Length", "default": 100},
            "DoorCount": {"type": "Integer", "default": "auto"},
        },
    }


def test_primary_params_are_the_ones_marked_in_declared_order():
    assert pm.primary_params(_part_with_ui()) == ["Width", "Depth"]


def test_primary_params_falls_back_to_the_first_three_declared():
    data = _part_with_ui()
    for spec in data["params"].values():
        spec.pop("ui", None)
    assert pm.primary_params(data) == ["Width", "Depth", "KickHeight"]


def test_primary_params_fallback_stops_at_what_exists():
    data = {"params": {"Width": {"type": "Length", "default": 600}}}
    assert pm.primary_params(data) == ["Width"]


def test_primary_params_is_empty_when_no_params_declared():
    assert pm.primary_params({"params": {}}) == []


# -- "auto" defaults --------------------------------------------------------

def test_merge_params_resolves_an_auto_default_to_none():
    merged = pm.merge_params(_part_with_ui(), None)
    assert merged["DoorCount"] is None
    assert merged["Width"] == 600


def test_merge_params_override_pins_an_auto_param():
    merged = pm.merge_params(_part_with_ui(), {"DoorCount": 3})
    assert merged["DoorCount"] == 3


def test_merge_params_still_drops_an_undeclared_override():
    merged = pm.merge_params(_part_with_ui(), {"Nonsense": 1})
    assert "Nonsense" not in merged


# -- Choice options and placement ------------------------------------------

def _part_with_choice():
    return {
        "schema": 1, "name": "Television",
        "facets": {}, "geometry": {},
        "placement": {"host": "floor", "offset": 0},
        "params": {
            "ScreenSize": {"type": "Integer", "default": 55, "ui": "primary"},
            "Mounting": {
                "type": "Choice", "default": "stand", "ui": "primary",
                "options": {
                    "stand": {"label": "On stand"},
                    "wall": {"label": "Wall-mounted",
                             "placement": {"host": "wall", "offset": 1100}},
                },
            },
        },
    }


def test_choice_options_returns_the_declared_map():
    spec = _part_with_choice()["params"]["Mounting"]
    assert list(pm.choice_options(spec)) == ["stand", "wall"]


def test_choice_options_is_empty_for_a_non_choice_param():
    assert pm.choice_options({"type": "Length", "default": 600}) == {}


def test_resolve_placement_returns_the_part_block_when_no_option_overrides():
    data = _part_with_choice()
    assert pm.resolve_placement(data, {"Mounting": "stand"}) == {
        "host": "floor", "offset": 0}


def test_resolve_placement_merges_a_selected_option_over_the_part():
    data = _part_with_choice()
    assert pm.resolve_placement(data, {"Mounting": "wall"}) == {
        "host": "wall", "offset": 1100}


def test_resolve_placement_merges_per_key():
    data = _part_with_choice()
    data["params"]["Mounting"]["options"]["wall"]["placement"] = {
        "host": "wall"}
    assert pm.resolve_placement(data, {"Mounting": "wall"}) == {
        "host": "wall", "offset": 0}


def test_resolve_placement_ignores_an_unknown_option_value():
    data = _part_with_choice()
    assert pm.resolve_placement(data, {"Mounting": "nope"}) == {
        "host": "floor", "offset": 0}


def test_resolve_placement_never_mutates_the_manifest():
    data = _part_with_choice()
    pm.resolve_placement(data, {"Mounting": "wall"})
    assert data["placement"] == {"host": "floor", "offset": 0}


# -- params block validation ------------------------------------------------

@pytest.mark.parametrize("kind", pm.PARAM_TYPES)
def test_every_known_param_type_is_accepted(kind):
    spec = {"type": kind, "default": 0}
    if kind == "Choice":
        spec = {"type": kind, "default": "stand",
                "options": {"stand": {}, "wall": {}}}
    errors, _warnings = pm.validate_manifest(_part(params={"P": spec}),
                                             FACETS)
    assert errors == []


def test_params_block_must_be_an_object():
    errors, _warnings = pm.validate_manifest(_part(params="nope"), FACETS)
    assert any("params" in e for e in errors)


def test_param_spec_must_be_an_object():
    errors, _warnings = pm.validate_manifest(
        _part(params={"Width": 600}), FACETS)
    assert any("Width" in e for e in errors)


def test_unknown_param_type_is_an_error():
    data = _part(params={"Width": {"type": "Wavelength", "default": 600}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Width" in e and "Wavelength" in e for e in errors)


@pytest.mark.parametrize("kind", ["Angle", "Bool", "String", "Choice"])
def test_auto_default_is_rejected_outside_integer_and_length(kind):
    spec = {"type": kind, "default": "auto"}
    if kind == "Choice":
        spec["options"] = {"stand": {}, "wall": {}}
    errors, _warnings = pm.validate_manifest(_part(params={"P": spec}),
                                             FACETS)
    assert any("P" in e and "auto" in e for e in errors)


@pytest.mark.parametrize("kind", pm.AUTO_PARAM_TYPES)
def test_auto_default_is_accepted_on_integer_and_length(kind):
    data = _part(params={"Width": {"type": kind, "default": "auto"}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert errors == []


@pytest.mark.parametrize("name", pm.AUTO_PARAM_NAMES)
def test_auto_default_is_accepted_on_a_measurable_dimension(name):
    data = _part(params={name: {"type": "Length", "default": "auto"}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert errors == []


@pytest.mark.parametrize("name", ["DoorCount", "ShelfCount", "BasinWidth"])
def test_auto_default_is_rejected_on_anything_a_shape_cannot_report(name):
    # A derived count has nothing to measure, so object.py's write-back
    # leaves it at 0 in the property editor forever. Declaring one is now
    # an error rather than a control that silently does not work.
    data = _part(params={name: {"type": "Integer", "default": "auto"}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any(name in e and "auto" in e for e in errors)


def test_choice_param_without_options_is_an_error():
    data = _part(params={"Mounting": {"type": "Choice",
                                      "default": "stand"}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Mounting" in e and "options" in e for e in errors)


def test_choice_param_with_empty_options_is_an_error():
    data = _part(params={"Mounting": {"type": "Choice",
                                      "default": "stand",
                                      "options": {}}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Mounting" in e and "options" in e for e in errors)


def test_choice_param_with_non_object_options_is_an_error():
    data = _part(params={"Mounting": {"type": "Choice",
                                      "default": "stand",
                                      "options": ["stand", "wall"]}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Mounting" in e and "options" in e for e in errors)


def test_choice_default_not_a_declared_option_is_an_error():
    data = _part(params={"Mounting": {"type": "Choice",
                                      "default": "bracket",
                                      "options": {"stand": {},
                                                  "wall": {}}}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Mounting" in e and "bracket" in e for e in errors)


def test_choice_default_in_the_declared_options_is_valid():
    data = _part(params={"Mounting": {"type": "Choice",
                                       "default": "stand",
                                       "options": {"stand": {},
                                                   "wall": {}}}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert errors == []


# -- "resets" (editing a driver discards pinned derived values) --------------

def _part_with_resets():
    return _part(params={
        "BurnerCount": {
            "type": "Choice", "default": "4",
            "options": {"1": {}, "2": {}, "4": {}, "5": {}},
            "resets": ["Width", "Depth"]},
        "Width": {"type": "Length", "default": "auto"},
        "Depth": {"type": "Length", "default": "auto"},
    })


def test_a_resets_list_of_auto_params_is_valid():
    errors, _warnings = pm.validate_manifest(_part_with_resets(), FACETS)
    assert errors == []


def test_reset_targets_returns_the_declared_list():
    spec = _part_with_resets()["params"]["BurnerCount"]
    assert pm.reset_targets(spec) == ["Width", "Depth"]


def test_reset_targets_is_empty_without_a_resets_key():
    assert pm.reset_targets({"type": "Length", "default": 600}) == []


def test_resets_must_be_a_non_empty_list():
    data = _part_with_resets()
    data["params"]["BurnerCount"]["resets"] = "Width"
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("BurnerCount" in e and "resets" in e for e in errors)


def test_resets_must_name_declared_params():
    data = _part_with_resets()
    data["params"]["BurnerCount"]["resets"] = ["Nope"]
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Nope" in e for e in errors)


def test_resets_must_target_auto_params():
    # A reset means "discard the pinned value and derive again". A param
    # with a static default has nothing to derive, so resetting it would be
    # a silent no-op.
    data = _part_with_resets()
    data["params"]["Width"]["default"] = 600
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Width" in e and "auto" in e for e in errors)


def test_a_param_cannot_reset_itself():
    data = _part_with_resets()
    data["params"]["BurnerCount"]["resets"] = ["BurnerCount", "Width"]
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("itself" in e for e in errors)


def _choice_spec():
    return {"type": "Choice", "default": "4",
            "options": {"1": {"label": "1 burner"}, "2": {"label": "2 burners"},
                        "4": {"label": "4 burners"}, "5": {"label": "5 burners"}}}


def test_migrated_value_maps_an_old_value_into_a_choice():
    # A document saved while BurnerCount was an Integer carries a 4; the
    # new Choice must read it as the "4" option, not fall back to the
    # first option or the default.
    spec = _choice_spec()
    assert pm.migrated_value(4, spec) == "4"
    assert pm.migrated_value(2, spec) == "2"
    assert pm.migrated_value("5 burners", spec) == "5"
    assert pm.migrated_value("1", spec) == "1"


def test_migrated_value_that_maps_nowhere_returns_none():
    # Reseeding to the manifest default is better than guessing: a 3-burner
    # hob never existed, so the old 3 must not become "the first option".
    assert pm.migrated_value(3, _choice_spec()) is None
    assert pm.migrated_value("6 burners", _choice_spec()) is None


def test_migrated_value_passes_a_plain_value_straight_through():
    spec = {"type": "Length", "default": 900}
    assert pm.migrated_value(600, spec) == 600


# -- per-field display unit overrides ---------------------------------------
# A Length param may pin the unit its field is shown in. Both halves are
# required: a part that only answers for metric leaves an imperial user
# looking at a field nobody chose.

def _length_with_unit(unit):
    return _part(params={"PanelThickness": {"type": "Length", "default": 18,
                                            "unit": unit}})


def test_a_complete_unit_override_is_valid():
    data = _length_with_unit({"metric": "mm", "imperial": "in"})
    errors, warnings = pm.validate_manifest(data, FACETS)
    assert errors == []
    assert warnings == []


def test_a_unit_override_missing_the_imperial_half_is_an_error():
    data = _length_with_unit({"metric": "mm"})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("PanelThickness" in e and "imperial" in e for e in errors)


def test_a_unit_override_missing_the_metric_half_is_an_error():
    data = _length_with_unit({"imperial": "in"})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("PanelThickness" in e and "metric" in e for e in errors)


def test_an_unknown_unit_is_an_error():
    data = _length_with_unit({"metric": "furlong", "imperial": "in"})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("PanelThickness" in e and "furlong" in e for e in errors)


def test_an_imperial_unit_in_the_metric_half_is_an_error():
    data = _length_with_unit({"metric": "in", "imperial": "in"})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("PanelThickness" in e and "metric" in e for e in errors)


def test_a_metric_unit_in_the_imperial_half_is_an_error():
    data = _length_with_unit({"metric": "mm", "imperial": "cm"})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("PanelThickness" in e and "imperial" in e for e in errors)


def test_a_unit_override_that_is_not_an_object_is_an_error():
    data = _length_with_unit("mm")
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("PanelThickness" in e and "unit" in e for e in errors)


def test_a_unit_override_on_a_param_with_no_unit_is_an_error():
    # Only a Length is drawn in a unit; a unit on a count or a flag means the
    # author expected a conversion that will never happen.
    data = _part(params={"Shelves": {"type": "Integer", "default": 3,
                                     "unit": {"metric": "mm",
                                              "imperial": "in"}}})
    errors, _warnings = pm.validate_manifest(data, FACETS)
    assert any("Shelves" in e and "unit" in e for e in errors)
