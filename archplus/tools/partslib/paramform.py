# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib param form - the browser panel's editor for one part's params.
#
# Split out of gui.py, which is already long. Every DECISION this makes -
# which params are primary, in what order, which are derived - comes from
# manifest.py, which is FreeCAD-free and unit-tested. What is left here is
# widget construction and value read-back, which the headless suite cannot
# exercise because conftest fakes PySide.

from PySide import QtCore, QtGui

from . import manifest as partslib_manifest
from . import units as partslib_units

# The largest length a field accepts, in millimetres - a 100 m dimension is
# already past anything a part in this library is, and the cap is what stops
# a mistyped "1800" in a metre field from building a kilometre-wide bed.
MAX_LENGTH_MM = 100000.0

_DERIVED_TIP = "Derived from the other parameters. Editing this pins it."


class ParamForm(QtGui.QWidget):
    """Primary params in a row, the rest behind a collapsed expander."""

    changed = QtCore.Signal()

    def __init__(self, parent=None, tokens=None):
        QtGui.QWidget.__init__(self, parent)
        self._tokens = tokens or {}
        self._specs = {}
        self._widgets = {}
        self._auto = set()
        # See isPristine(). Initialised here so a form that is read before
        # its first setSpecs() still answers.
        self._pristine = True
        self._imperial = False
        self._tips = {}
        # Remembered for the session, not per part: a user who opens the
        # expander is telling us they work in detail, and re-collapsing it on
        # every selection would fight them.
        self._expanded = False

        layout = QtGui.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._primaryRow = QtGui.QGridLayout()
        layout.addLayout(self._primaryRow)

        controls = QtGui.QHBoxLayout()
        self._toggle = QtGui.QToolButton()
        self._toggle.setAutoRaise(True)
        self._toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self._toggle.setArrowType(QtCore.Qt.RightArrow)
        self._toggle.clicked.connect(self._onToggle)
        controls.addWidget(self._toggle)
        controls.addStretch(1)
        self._resetButton = QtGui.QPushButton("Reset")
        self._resetButton.setFlat(True)
        self._resetButton.clicked.connect(self.reset)
        controls.addWidget(self._resetButton)
        layout.addLayout(controls)

        self._more = QtGui.QWidget()
        self._moreRow = QtGui.QGridLayout(self._more)
        self._moreRow.setContentsMargins(0, 0, 0, 0)
        self._more.setVisible(False)
        layout.addWidget(self._more)

    def setSpecs(self, specs, primary):
        """Rebuild for one part. `primary` is manifest.primary_params()."""
        self._specs = dict(specs or {})
        self._tips = {}
        # Resolved per rebuild, not per field: every length in one form must
        # agree, and re-asking here picks up a unit-schema change without the
        # user having to reopen the panel.
        self._imperial = partslib_units.is_imperial()
        self._widgets = {}
        self._auto = set(
            name for name, spec in self._specs.items()
            if (spec or {}).get("default") == partslib_manifest.AUTO)
        _clearGrid(self._primaryRow)
        _clearGrid(self._moreRow)

        primary = [name for name in (primary or []) if name in self._specs]
        secondary = [name for name in self._specs if name not in primary]

        # One field per ROW, not primary params side by side. The sidebar is
        # 240-340 px wide (gui.py), so three label+field pairs across left
        # each spinbox about 40 px - too narrow to show "180.0 cm", let alone
        # with its spin arrows, and narrowing the pane clipped it further. A
        # row each gives every field the sidebar's full width and does not
        # care how many params a part declares.
        for row, name in enumerate(primary):
            self._addField(self._primaryRow, row, 0, name)
        for row, name in enumerate(secondary):
            self._addField(self._moreRow, row, 0, name)

        self._toggle.setVisible(bool(secondary))
        self._toggle.setText("More parameters (%d)" % len(secondary))
        self._more.setVisible(bool(secondary) and self._expanded)
        self._toggle.setArrowType(
            QtCore.Qt.DownArrow if self._expanded else QtCore.Qt.RightArrow)
        # A rebuild is a fresh part (or reset()), so nothing is edited yet.
        # This is also what makes reset() restore the committed thumbnail:
        # it goes through setSpecs, so the form comes back pristine.
        self._pristine = True

    def values(self):
        """{name: value} for every PINNED field.

        A derived field is omitted rather than sent as its displayed value,
        because sending it would pin it - merge_params() treats any present
        override as the user's answer."""
        out = {}
        for name, widget in self._widgets.items():
            if name in self._auto:
                continue
            out[name] = _valueOf(widget, self._specs.get(name) or {})
        return out

    def isPristine(self):
        """True while every field still holds its manifest default.

        A FLAG rather than a comparison of values against the manifest, on
        purpose: setDerived() writes measured numbers into the auto fields
        moments after a part is selected, so a value comparison would report
        an untouched form as edited. setDerived deliberately does not emit
        `changed`, and reset() goes through setSpecs, so both leave the form
        pristine.

        gui._refreshPreview reads this to decide whether the part's committed
        thumbnail.jpg already depicts these exact parameters - which, at the
        manifest's defaults, it does."""
        return self._pristine

    def hasDerivedFields(self):
        """True while some field still shows a value derived from the shape.

        setDerived() only ever writes into these, so when there are none,
        measuring the shape is pure waste - and measuring is not cheap:
        geometry.measure() calls optimalBoundingBox(), which costs about as
        much as building the shape (0.913s of the king bed's 1.76s click).
        27 of the 31 bundled parts declare no "auto" param at all."""
        return bool(self._auto)

    def setDerived(self, values):
        """Show computed values in the fields still marked derived.

        An "auto" param has no value to seed from the manifest - its default is
        the string AUTO - so until the shape is built there is nothing to show.
        The caller rebuilds, learns what the builder actually derived, and hands
        the answers here. Only fields still in self._auto are touched: once a
        user has pinned a field, its value is theirs and must not be overwritten
        by a later rebuild. Nothing here emits `changed`; a derived value
        arriving is not a user edit, and treating it as one would pin every
        field on the first rebuild.
        """
        for name, value in (values or {}).items():
            if name not in self._auto:
                continue
            widget = self._widgets.get(name)
            if widget is None or value is None:
                continue
            widget.blockSignals(True)
            try:
                _setValueOf(widget, self._specs.get(name) or {}, value)
            finally:
                widget.blockSignals(False)

    def reset(self):
        """Back to manifest defaults, which also restores derived fields."""
        self.setSpecs(self._specs,
                      partslib_manifest.primary_params(
                          {"params": self._specs}))
        self.changed.emit()

    def _addField(self, grid, row, column, name):
        spec = self._specs.get(name) or {}
        widget = _widgetFor(spec, self._imperial)
        if widget is None:
            # An unrecognised type gets NO field here, matching object.py's
            # warn-and-skip when declaring properties: guessing a spinbox
            # would send a float into build_shape as a real override for a
            # param nothing else represents.
            return
        caption = QtGui.QLabel(spec.get("label") or name)
        # A length field arrives with its unit hint already set; the derived
        # note is added to it rather than over it, and _onEdited puts the hint
        # back when the field is pinned.
        self._tips[name] = widget.toolTip()
        if name in self._auto:
            self._applyDerivedStyle(name)
        _connect(widget, name, self._onEdited)
        self._widgets[name] = widget
        grid.addWidget(caption, row, column * 2)
        grid.addWidget(widget, row, column * 2 + 1)
        # Whatever space the row has beyond the caption belongs to the field.
        grid.setColumnStretch(column * 2, 0)
        grid.setColumnStretch(column * 2 + 1, 1)

    def _applyDerivedStyle(self, name):
        """Italicise a field and explain that its value is derived.

        Called when a field is created derived and again when an edit of a
        driver param returns it to derived, so both routes present the pin
        invitation identically."""
        widget = self._widgets.get(name)
        if widget is None:
            return
        widget.setStyleSheet(
            "font-style: italic; color: %s;"
            % (self._tokens.get("text_dim", "#888888"),))
        widget.setToolTip("\n".join(
            tip for tip in (self._tips.get(name), _DERIVED_TIP) if tip))

    def _onEdited(self, name):
        if name in self._auto:
            self._auto.discard(name)
            widget = self._widgets.get(name)
            if widget is not None:
                widget.setStyleSheet("")
                widget.setToolTip(self._tips.get(name, ""))
        # Editing a driver param discards the pins its manifest names: a
        # hob's burner count, once changed, re-derives width and depth even
        # if the user had typed them before. The rebuilt shape's measurements
        # arrive via setDerived() moments later.
        for target in partslib_manifest.reset_targets(
                self._specs.get(name) or {}):
            if target not in self._widgets or target in self._auto:
                continue
            self._auto.add(target)
            self._applyDerivedStyle(target)
        self._pristine = False
        self.changed.emit()

    def _onToggle(self):
        self._expanded = not self._expanded
        self._more.setVisible(self._expanded)
        self._toggle.setArrowType(
            QtCore.Qt.DownArrow if self._expanded else QtCore.Qt.RightArrow)


class LengthSpinBox(QtGui.QDoubleSpinBox):
    """A length field pinned to one unit, that still accepts any other.

    Qt's own suffix handling is deliberately NOT used. setSuffix(" cm") makes
    the trailing " cm" mandatory, so typing "2 ft" is rejected keystroke by
    keystroke and the pinned unit becomes a cage. Owning validate(),
    valueFromText() and textFromValue() instead means the field displays cm
    and reads mm, inches, feet or "5' 6\"" - every rule of what is a length
    living in units.py, where it is unit-tested.

    The value Qt holds is in the DISPLAY unit; mmValue()/setMmValue() are the
    millimetre boundary, and _valueOf/_setValueOf use them so nothing outside
    this class has to know which unit a field happens to be showing."""

    def __init__(self, unit, parent=None):
        QtGui.QDoubleSpinBox.__init__(self, parent)
        self._unit = unit
        self.setDecimals(partslib_units.decimals(unit))
        self.setRange(0.0, partslib_units.from_mm(MAX_LENGTH_MM, unit))
        self.setToolTip("In %s. Another unit can be typed in full, "
                        "e.g. 18 mm, 1 m, 2 ft, 5' 6\"." % unit)
        # Ask for room for the widest value this field can hold, so a layout
        # squeezes something else instead of silently clipping the unit off
        # the end of the number.
        self.setMinimumWidth(self._widthFor(self.textFromValue(self.maximum())))

    def _widthFor(self, text):
        """Pixels needed for `text` plus the spin arrows and frame."""
        try:
            metrics = self.fontMetrics()
            width = metrics.horizontalAdvance(text)
        except Exception:
            return 0
        return width + 36

    def unit(self):
        return self._unit

    def mmValue(self):
        # Rounded because a display unit divides: 1.8 cm is 18.000000000000004
        # mm in binary floating point, and that number would be written into a
        # part's parameter as if the user had asked for it.
        return round(partslib_units.to_mm(self.value(), self._unit), 6)

    def setMmValue(self, value):
        self.setValue(partslib_units.from_mm(value, self._unit))

    def textFromValue(self, value):
        return "%.*f %s" % (self.decimals(), value, self._unit)

    def valueFromText(self, text):
        millimetres = partslib_units.parse_length(text, self._unit)
        if millimetres is None:
            return self.value()          # refuse it; keep what was there
        # Rounded to the precision the field DISPLAYS. Qt keeps whatever this
        # returns, so without it "2 ft" showed 61.0 cm while holding 609.6 mm
        # - the field saying one thing and the part being built as another,
        # which is the whole complaint that got the W/D/H readout deleted.
        # decimals() is chosen so a millimetre still survives the rounding.
        return round(partslib_units.from_mm(millimetres, self._unit),
                     self.decimals())

    def validate(self, text, position):
        if partslib_units.parse_length(text, self._unit) is not None:
            state = QtGui.QValidator.Acceptable
        elif partslib_units.is_partial_length(text):
            state = QtGui.QValidator.Intermediate
        else:
            state = QtGui.QValidator.Invalid
        return (state, text, position)


def _widgetFor(spec, imperial=False):
    """One editor widget for a param spec, or None for an unknown type.

    The None case is a SKIP, not a fallback widget: the old fall-through
    produced a millimetre QDoubleSpinBox for anything unrecognised, whose
    float would ride into build_shape as a real override. object.py warns
    and skips the same case when declaring properties, and the two sides
    must agree."""
    kind = spec.get("type")
    default = spec.get("default")
    if default == partslib_manifest.AUTO:
        default = None

    if kind == "Choice":
        widget = QtGui.QComboBox()
        options = partslib_manifest.choice_options(spec)
        for value, option in options.items():
            widget.addItem((option or {}).get("label") or value, value)
        if default is not None and default in options:
            widget.setCurrentIndex(list(options).index(default))
        return widget
    if kind == "Bool":
        widget = QtGui.QCheckBox()
        widget.setChecked(bool(default))
        return widget
    if kind == "String":
        widget = QtGui.QLineEdit()
        widget.setText(default or "")
        return widget
    if kind == "Integer":
        widget = QtGui.QSpinBox()
        widget.setRange(0, 9999)
        widget.setValue(int(default or 0))
        return widget
    if kind == "Length":
        widget = LengthSpinBox(partslib_units.display_unit(spec, imperial))
        widget.setMmValue(float(default or 0))
        return widget
    if kind == "Angle":
        widget = QtGui.QDoubleSpinBox()
        widget.setRange(0.0, 100000.0)
        widget.setDecimals(0)
        widget.setSuffix(" deg")
        widget.setValue(float(default or 0))
        return widget
    return None


def _connect(widget, name, slot):
    """Wire whichever change signal this widget class actually has."""
    for signal in ("valueChanged", "currentIndexChanged", "textEdited",
                   "toggled"):
        handler = getattr(widget, signal, None)
        if handler is not None:
            handler.connect(lambda *args: slot(name))
            return


def _valueOf(widget, spec):
    if spec.get("type") == "Choice":
        return widget.itemData(widget.currentIndex())
    # mmValue before value: a length field shows centimetres but every
    # consumer downstream - build_shape, the App::PropertyLength on a placed
    # part - is given millimetres.
    for reader in ("mmValue", "value", "text", "isChecked"):
        method = getattr(widget, reader, None)
        if method is not None:
            return method()
    return None


def _setValueOf(widget, spec, value):
    """Put a value into whichever widget class this spec produced."""
    if spec.get("type") == "Choice":
        index = widget.findData(value)
        if index >= 0:
            widget.setCurrentIndex(index)
        return
    for writer in ("setMmValue", "setValue", "setText", "setChecked"):
        method = getattr(widget, writer, None)
        if method is None:
            continue
        if writer == "setMmValue":
            method(float(value))
        elif writer == "setValue":
            method(int(value) if spec.get("type") == "Integer"
                   else float(value))
        elif writer == "setText":
            method("%s" % (value,))
        else:
            method(bool(value))
        return


def _clearGrid(grid):
    while grid.count():
        item = grid.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
