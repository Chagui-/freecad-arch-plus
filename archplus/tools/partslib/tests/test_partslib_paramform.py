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
    # 2 ft is 60.96 cm, taken at the precision the field shows - see
    # test_a_typed_value_is_taken_at_the_precision_the_field_shows.
    assert field.valueFromText("2 ft") == 61.0


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


def test_a_typed_value_is_taken_at_the_precision_the_field_shows():
    # Real Qt keeps whatever valueFromText returns without rounding it to
    # decimals(), so "2 ft" in a centimetre field displayed 61.0 cm while
    # holding 609.6 mm. The field must not show one number and build another:
    # 61.0 cm is what the user is looking at, so 610 mm is what it means.
    field = _field("cm")
    assert field.valueFromText("2 ft") == 61.0
    field.setValue(field.valueFromText("2 ft"))
    assert field.mmValue() == 610.0


def test_rounding_to_the_shown_precision_keeps_a_millimetre_intact():
    # The decimals are chosen so 1 mm survives (see units.LENGTH_UNITS), so
    # rounding to them must not cost a millimetre anywhere.
    for unit in ("mm", "cm", "m", "in", "ft"):
        field = _field(unit)
        assert abs(field.valueFromText("18 mm")
                   - pf.partslib_units.from_mm(18, unit)) < 0.51 / (
                       pf.partslib_units.factor(unit)), unit


class _Signal:
    """Stands in for a Qt Signal - conftest fakes QtCore.Signal as a
    function returning None, so an instance needs its own."""

    def __init__(self):
        self.count = 0

    def emit(self):
        self.count += 1


class _Field:
    """A spinbox as far as _setValueOf and setDerived need one."""

    def __init__(self):
        self.value = None
        self.blocked = []

    def blockSignals(self, state):
        self.blocked.append(state)

    def setMmValue(self, value):
        self.value = value

    def setStyleSheet(self, _sheet):
        pass

    def setToolTip(self, _text):
        pass


def _bare_form(auto=(), widgets=None):
    """A ParamForm with its Qt construction skipped.

    Built with object.__new__ the way the panels' edit round-trip tests are:
    what is under test is the pristine/derived bookkeeping, not layout."""
    form = object.__new__(pf.ParamForm)
    form._specs = {}
    form._tips = {}
    form._widgets = dict(widgets or {})
    form._auto = set(auto)
    form._pristine = True
    form.changed = _Signal()
    return form


def test_a_freshly_populated_form_is_pristine():
    form = _bare_form()
    assert form.isPristine()


def test_editing_a_field_dirties_the_form():
    form = _bare_form()
    form._onEdited("Width")
    assert not form.isPristine()
    assert form.changed.count == 1


def test_a_derived_value_arriving_leaves_the_form_pristine():
    # The whole reason this is a flag and not a value comparison: setDerived
    # writes measured numbers into the auto fields moments after a part is
    # selected, and a value comparison would then call an untouched form
    # edited - sending every part straight back to the slow render path.
    field = _Field()
    form = _bare_form(auto=["Height"], widgets={"Height": field})
    form.setDerived({"Height": 1230.0})

    assert field.value == 1230.0
    assert form.isPristine()
    assert form.changed.count == 0


def test_pinning_a_derived_field_dirties_the_form_and_clears_its_auto_flag():
    field = _Field()
    form = _bare_form(auto=["Height"], widgets={"Height": field})
    form._onEdited("Height")

    assert not form.isPristine()
    assert not form.hasDerivedFields()


def test_has_derived_fields_is_false_without_auto_params():
    # 27 of the 31 bundled parts. This is what spares them measure(), whose
    # optimalBoundingBox costs about as much as building the shape.
    assert not _bare_form().hasDerivedFields()


def test_has_derived_fields_is_true_while_one_is_unpinned():
    assert _bare_form(auto=["Width"]).hasDerivedFields()
