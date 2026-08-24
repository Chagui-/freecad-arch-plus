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
        self.tooltip = None
        self.stylesheet = None

    def blockSignals(self, state):
        self.blocked.append(state)

    def setMmValue(self, value):
        self.value = value

    def mmValue(self):
        return self.value

    def setStyleSheet(self, sheet):
        self.stylesheet = sheet

    def setToolTip(self, text):
        self.tooltip = text


def _bare_form(auto=(), widgets=None):
    """A ParamForm with its Qt construction skipped.

    Built with object.__new__ the way the panels' edit round-trip tests are:
    what is under test is the pristine/derived bookkeeping, not layout."""
    form = object.__new__(pf.ParamForm)
    form._specs = {}
    form._tips = {}
    form._tokens = {}
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


def test_editing_a_driver_returns_its_targets_to_derived():
    # Width and Depth were pinned, then the burner count changed. The pins
    # are discarded so the next rebuild re-derives both from the new count,
    # instead of building the new hob at the old dimensions.
    width, depth = _Field(), _Field()
    form = _bare_form(widgets={"Width": width, "Depth": depth})
    form._specs = {
        "BurnerCount": {"type": "Choice", "default": "4",
                        "options": {"1": {}, "2": {}, "4": {}, "5": {}},
                        "resets": ["Width", "Depth"]},
        "Width": {"type": "Length", "default": "auto"},
        "Depth": {"type": "Length", "default": "auto"},
    }
    form._onEdited("BurnerCount")

    assert form.hasDerivedFields()
    assert not form.isPristine()
    form.setDerived({"Width": 300.0, "Depth": 510.0})
    assert width.value == 300.0
    assert depth.value == 510.0


def test_editing_a_driver_without_resets_leaves_other_fields_pinned():
    form = _bare_form(widgets={"Width": _Field(), "Depth": _Field()})
    form._specs = {
        "BurnerCount": {"type": "Choice", "default": "4",
                        "options": {"1": {}, "2": {}, "4": {}, "5": {}}},
        "Width": {"type": "Length", "default": "auto"},
        "Depth": {"type": "Length", "default": "auto"},
    }
    form._onEdited("BurnerCount")

    assert not form.hasDerivedFields()


def test_has_derived_fields_is_false_without_auto_params():
    # 27 of the 31 bundled parts. This is what spares them measure(), whose
    # optimalBoundingBox costs about as much as building the shape.
    assert not _bare_form().hasDerivedFields()


def test_has_derived_fields_is_true_while_one_is_unpinned():
    assert _bare_form(auto=["Width"]).hasDerivedFields()


class _Choice:
    """A combo as far as _valueOf/_setValueOf need one."""

    def __init__(self):
        self.index = 0
        self.items = []

    def addItem(self, label, data):
        self.items.append((label, data))

    def blockSignals(self, state):
        pass

    def setStyleSheet(self, sheet):
        pass

    def setToolTip(self, text):
        pass

    def setCurrentIndex(self, index):
        self.index = index

    def findData(self, data):
        for i, (_label, item_data) in enumerate(self.items):
            if item_data == data:
                return i
        return -1

    def currentIndex(self):
        return self.index

    def itemData(self, index):
        return self.items[index][1]


def _value_of(form, name):
    spec = form._specs.get(name) or {}
    widget = form._widgets.get(name)
    assert widget is not None, name
    return pf._valueOf(widget, spec)


def test_load_values_writes_every_field_and_leaves_the_form_pristine():
    # Entering edit loads the placed object's values; that is not a user
    # edit, so the form must still count as pristine and not emit changed.
    width, depth = _Field(), _Field()
    form = _bare_form(widgets={"Width": width, "Depth": depth})
    form._specs = {"Width": {"type": "Length"}, "Depth": {"type": "Length"}}
    form.loadValues({"Width": 1600.0, "Depth": 2000.0})

    assert width.value == 1600.0
    assert depth.value == 2000.0
    assert form.isPristine()
    assert form.changed.count == 0


def test_load_values_marks_the_objects_derived_fields():
    # The placed object's AutoParams is the truth about what is derived; it
    # need not match the manifest defaults a browser selection derives from.
    width, depth = _Field(), _Field()
    form = _bare_form(auto=["Width"], widgets={"Width": width, "Depth": depth})
    form._specs = {"Width": {"type": "Length"}, "Depth": {"type": "Length"}}
    form.loadValues({"Width": 1800.0, "Depth": 2000.0}, auto=["Depth"])

    assert form.autoNames() == {"Depth"}
    assert form.hasDerivedFields()


def test_load_values_skips_values_it_has_no_widget_for():
    field = _Field()
    form = _bare_form(widgets={"Width": field})
    form._specs = {"Width": {"type": "Length"}}
    form.loadValues({"Width": 1600.0, "NotAField": 1.0})

    assert field.value == 1600.0
    assert form.changed.count == 0


def test_set_field_edits_like_a_user_edit():
    # The verification scripts need a way to simulate typing into a field;
    # it must behave exactly like the signal path: pin the field, emit
    # changed, dirty the form.
    field = _Field()
    form = _bare_form(auto=["Width"], widgets={"Width": field})
    form._specs = {"Width": {"type": "Length"}}
    form.setField("Width", 1600.0)

    assert field.value == 1600.0
    assert form.autoNames() == set()
    assert not form.isPristine()
    assert form.changed.count == 1


def test_set_field_on_an_unknown_name_is_a_noop():
    form = _bare_form()
    form.setField("Nothing", 1.0)
    assert form.isPristine()
    assert form.changed.count == 0


def test_displayed_reads_every_field_stable_values():
    width, mounting = _Field(), _Choice()
    mounting.items = [("Wall-mounted", "wall"), ("Free-standing", "free")]
    form = _bare_form(widgets={"Width": width, "Mounting": mounting})
    form._specs = {
        "Width": {"type": "Length"},
        "Mounting": {"type": "Choice", "options": {"wall": {}, "free": {}}},
    }
    form.loadValues({"Width": 1600.0, "Mounting": "wall"})

    assert form.displayed() == {"Width": 1600.0, "Mounting": "wall"}


def test_load_values_restyles_fields_to_the_objects_truth():
    # A field the manifest derives but the object has pinned must come back
    # with the pinned look, and vice versa: derived-ness on a placed object
    # is AutoParams, not the manifest default.
    field = _Field()
    form = _bare_form(widgets={"Width": field})
    form._specs = {"Width": {"type": "Length", "default": "auto"}}
    form._tips["Width"] = "base tip"
    form.loadValues({"Width": 1600.0}, auto=[])

    assert "Width" not in form.autoNames()
    assert field.stylesheet == ""
    assert field.tooltip == "base tip"

    form.loadValues({"Width": 1600.0}, auto=["Width"])
    assert form.autoNames() == {"Width"}
    assert field.tooltip is not None and "Derived" in field.tooltip
