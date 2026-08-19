# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Display units for the parts panel: which unit a Length field is shown in,
# and the conversion between that unit and the millimetres everything
# downstream of the panel speaks.

from archplus.tools.partslib import units as pu


def test_core_module_does_not_import_freecad_at_module_scope():
    import inspect
    src = inspect.getsource(pu)
    head = src.split("def is_imperial", 1)[0]
    for banned in ("import FreeCAD", "import Part", "from PySide"):
        assert banned not in head


def test_metric_lengths_default_to_centimetres():
    assert pu.display_unit({"type": "Length"}, imperial=False) == "cm"


def test_imperial_lengths_default_to_inches():
    assert pu.display_unit({"type": "Length"}, imperial=True) == "in"


def test_a_field_override_replaces_the_metric_default():
    spec = {"type": "Length", "unit": {"metric": "mm", "imperial": "in"}}
    assert pu.display_unit(spec, imperial=False) == "mm"


def test_a_field_override_replaces_the_imperial_default():
    spec = {"type": "Length", "unit": {"metric": "m", "imperial": "ft"}}
    assert pu.display_unit(spec, imperial=True) == "ft"


def test_a_malformed_override_falls_back_to_the_default():
    # validate_manifest() rejects these before they ship, but a stale part
    # loaded from a user's own library folder must still draw a field.
    spec = {"type": "Length", "unit": {"metric": "furlong"}}
    assert pu.display_unit(spec, imperial=False) == "cm"


def test_from_mm_converts_into_the_display_unit():
    assert pu.from_mm(1050, "cm") == 105.0
    assert pu.from_mm(1050, "m") == 1.05
    assert pu.from_mm(25.4, "in") == 1.0


def test_to_mm_is_the_inverse_of_from_mm():
    for unit in pu.LENGTH_UNITS:
        assert abs(pu.to_mm(pu.from_mm(1234.5, unit), unit) - 1234.5) < 1e-9


def test_decimals_keep_a_whole_millimetre_expressible():
    # 1 mm must be typeable in every unit we offer, or the panel silently
    # rounds away a dimension the builder can still receive.
    for unit, places in ((u, pu.decimals(u)) for u in pu.LENGTH_UNITS):
        step = pu.to_mm(10 ** -places, unit)
        assert step <= 1.0, "%s rounds to %s mm steps" % (unit, step)


def test_format_length_labels_the_value_with_its_unit():
    assert pu.format_length(1050, "cm") == "105.0 cm"
    assert pu.format_length(1050, "mm") == "1050 mm"


# --- typed entry ----------------------------------------------------------
# A field pinned to cm must still accept "18 mm" or '2 ft', or the pinned
# unit becomes a trap for anyone whose drawing is dimensioned differently.

def test_a_bare_number_means_the_fields_own_unit():
    assert pu.parse_length("105", "cm") == 1050.0
    assert pu.parse_length("105", "mm") == 105.0


def test_a_typed_unit_overrides_the_fields_unit():
    assert pu.parse_length("18 mm", "cm") == 18.0
    assert pu.parse_length("1 m", "cm") == 1000.0


def test_a_typed_unit_needs_no_space():
    assert pu.parse_length("18mm", "cm") == 18.0


def test_imperial_spellings_are_accepted():
    for text in ("2 ft", "2ft", "2 feet", "2 foot", "2'"):
        assert pu.parse_length(text, "cm") == 609.6, text
    for text in ("1 in", "1inch", "1 inches", '1"'):
        assert pu.parse_length(text, "cm") == 25.4, text


def test_feet_and_inches_add_up():
    assert abs(pu.parse_length("5' 6\"", "cm") - 1676.4) < 1e-9
    assert abs(pu.parse_length("1 m 5 cm", "cm") - 1050.0) < 1e-9


def test_a_bare_number_inside_a_compound_is_ambiguous_and_rejected():
    # "5' 6" could be 6 inches or 6 of the field's own unit. Refuse rather
    # than guess: the user still has the last good value in the widget.
    assert pu.parse_length("5' 6", "cm") is None


def test_a_comma_is_a_decimal_separator():
    assert pu.parse_length("1,5 cm", "cm") == 15.0


def test_a_three_digit_group_after_a_comma_is_ambiguous_and_rejected():
    # "1,500" is 1500 to an English speaker and 1.5 to a German one.
    assert pu.parse_length("1,500", "cm") is None


def test_garbage_is_rejected():
    for text in ("", "   ", "abc", "18 furlongs", "1..5", "18 mm mm",
                 "$18", "18mm)", None):
        assert pu.parse_length(text, "cm") is None, repr(text)


def test_a_negative_length_is_rejected():
    assert pu.parse_length("-5", "cm") is None


def test_partial_input_is_recognised_while_the_user_is_still_typing():
    # QDoubleSpinBox.validate() must answer Intermediate for these or the
    # keystrokes that would complete "2 ft" never reach the field.
    for text in ("", "2", "2 ", "2 f", "1 m 5 c", "1,"):
        assert pu.is_partial_length(text), repr(text)


def test_input_that_can_never_complete_is_not_partial():
    for text in ("$", "2 f$", "abc!", None):
        assert not pu.is_partial_length(text), repr(text)


# --- override validation --------------------------------------------------
# The messages themselves are asserted in test_partslib_manifest.py, which is
# where a library author meets them. These cover the shape of the rule.

def test_a_param_with_no_override_has_nothing_to_report():
    assert pu.unit_errors("Width", {"type": "Length"}) == []


def test_a_complete_override_has_nothing_to_report():
    spec = {"type": "Length", "unit": {"metric": "mm", "imperial": "in"}}
    assert pu.unit_errors("PanelThickness", spec) == []


def test_both_halves_are_reported_when_both_are_wrong():
    spec = {"type": "Length", "unit": {"metric": "in", "imperial": "cm"}}
    assert len(pu.unit_errors("Width", spec)) == 2


# --- which family the user is working in ----------------------------------

class _FakeQuantity:
    def __init__(self, preferred=None, user_string=None):
        self._preferred = preferred
        self.UserString = user_string

    def getUserPreferred(self):
        if self._preferred is None:
            raise RuntimeError("not available in this build")
        return self._preferred


def _schema(monkeypatch, **kwargs):
    import FreeCAD
    import types
    monkeypatch.setattr(
        FreeCAD, "Units",
        types.SimpleNamespace(Length=object(),
                              Quantity=lambda *a: _FakeQuantity(**kwargs)),
        raising=False)


def test_a_millimetre_schema_is_not_imperial(monkeypatch):
    _schema(monkeypatch, preferred=("1000,00 mm", 1.0, "mm"))
    assert pu.is_imperial() is False


def test_an_inch_schema_is_imperial(monkeypatch):
    _schema(monkeypatch, preferred=("39.37 in", 25.4, "in"))
    assert pu.is_imperial() is True


def test_a_feet_and_inches_schema_is_imperial(monkeypatch):
    _schema(monkeypatch, preferred=("3' 3.37\"", 304.8, "ft"))
    assert pu.is_imperial() is True


def test_the_printed_string_decides_when_the_preferred_api_is_missing(
        monkeypatch):
    # getUserPreferred() is the clean answer but not one this code can prove
    # across FreeCAD versions, so the user-visible string is the fallback.
    _schema(monkeypatch, preferred=None, user_string="39.37 in")
    assert pu.is_imperial() is True
    _schema(monkeypatch, preferred=None, user_string="1000,00 mm")
    assert pu.is_imperial() is False


def test_no_usable_units_api_leaves_the_panel_metric(monkeypatch):
    import FreeCAD
    monkeypatch.delattr(FreeCAD, "Units", raising=False)
    assert pu.is_imperial() is False


def test_a_spelled_out_metric_unit_is_not_mistaken_for_imperial(monkeypatch):
    # "millimeter" contains "mil"; matching on substrings would call a
    # metric schema imperial and show the whole catalogue in inches.
    _schema(monkeypatch, preferred=None, user_string="1000,00 millimeter")
    assert pu.is_imperial() is False


# --- the readability rule -------------------------------------------------
# The point of pinning a unit is that a dimension reads the way it would on a
# drawing: two or three digits. A field showing 2000 or 0.5 is telling you the
# unit is wrong, not that the part is unusual - so it is a rule, not a hint,
# and test_library_content.py enforces it over the shipped catalogue.

def test_a_dimension_that_reads_in_two_or_three_digits_is_readable():
    assert pu.is_readable(1050, "cm") is True          # 105.0 cm
    assert pu.is_readable(18, "mm") is True            # 18 mm
    assert pu.is_readable(2200, "in") is True          # 86.61 in


def test_a_dimension_that_reads_in_thousands_is_not_readable():
    assert pu.is_readable(20000, "cm") is False        # 2000.0 cm


def test_a_dimension_that_reads_below_one_is_not_readable():
    assert pu.is_readable(5, "cm") is False            # 0.5 cm - want mm


def test_zero_reads_the_same_in_every_unit():
    for unit in pu.LENGTH_UNITS:
        assert pu.is_readable(0, unit) is True
