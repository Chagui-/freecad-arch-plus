# SPDX-License-Identifier: LGPL-2.1-or-later
#
# LengthSpinBox - the glue between a field showing centimetres and the
# millimetres every consumer downstream of the panel expects.
#
# The RULES about what is a length live in units.py and are tested in
# test_partslib_units.py. What is tested here is the widget contract: that
# reading a field gives millimetres, that a typed unit survives the trip, and
# that Qt is told the right validator state for each kind of input - the three
# things a wrong answer to which silently builds the wrong part.

from PySide import QtGui

from archplus.tools.partslib import paramform as pf


def _field(unit):
    return pf.LengthSpinBox(unit)


def test_a_field_is_read_back_in_millimetres():
    field = _field("cm")
    field.setMmValue(1050)
    assert field.value() == 105.0
    assert field.mmValue() == 1050.0


def test_a_centimetre_field_still_expresses_whole_millimetres():
    field = _field("cm")
    field.setMmValue(18)
    assert field.mmValue() == 18.0


def test_the_displayed_text_carries_the_unit():
    field = _field("cm")
    field.setMmValue(1050)
    assert field.textFromValue(field.value()) == "105.0 cm"


def test_a_typed_unit_is_converted_into_the_fields_unit():
    field = _field("cm")
    assert field.valueFromText("18 mm") == 1.8
    assert field.valueFromText("2 ft") == 60.96


def test_text_that_is_not_a_length_keeps_the_value_the_field_had():
    field = _field("cm")
    field.setMmValue(900)
    assert field.valueFromText("nonsense") == 90.0


def test_a_length_is_accepted():
    field = _field("cm")
    state, _text, _pos = field.validate("2 ft", 4)
    assert state == QtGui.QValidator.Acceptable


def test_input_still_being_typed_is_intermediate():
    field = _field("cm")
    state, _text, _pos = field.validate("2 f", 3)
    assert state == QtGui.QValidator.Intermediate


def test_input_that_can_never_be_a_length_is_invalid():
    field = _field("cm")
    state, _text, _pos = field.validate("2 f$", 4)
    assert state == QtGui.QValidator.Invalid


def test_the_fields_own_text_reads_back_as_the_same_value():
    # textFromValue must round-trip through valueFromText, or committing an
    # untouched field changes the part.
    for unit in ("mm", "cm", "m", "in", "ft"):
        field = _field(unit)
        field.setMmValue(900)
        text = field.textFromValue(field.value())
        assert abs(field.valueFromText(text) - field.value()) < 1e-9, unit


def test_a_length_past_the_cap_is_clamped_rather_than_built():
    field = _field("cm")
    field.setMmValue(10 * pf.MAX_LENGTH_MM)
    assert field.mmValue() == pf.MAX_LENGTH_MM
