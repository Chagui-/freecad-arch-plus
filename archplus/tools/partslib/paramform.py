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


class ParamForm(QtGui.QWidget):
    """Primary params in a row, the rest behind a collapsed expander."""

    changed = QtCore.Signal()

    def __init__(self, parent=None, tokens=None):
        QtGui.QWidget.__init__(self, parent)
        self._tokens = tokens or {}
        self._specs = {}
        self._widgets = {}
        self._auto = set()
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
        self._widgets = {}
        self._auto = set(
            name for name, spec in self._specs.items()
            if (spec or {}).get("default") == partslib_manifest.AUTO)
        _clearGrid(self._primaryRow)
        _clearGrid(self._moreRow)

        primary = [name for name in (primary or []) if name in self._specs]
        secondary = [name for name in self._specs if name not in primary]

        for column, name in enumerate(primary):
            self._addField(self._primaryRow, 0, column, name)
        for row, name in enumerate(secondary):
            self._addField(self._moreRow, row, 0, name)

        self._toggle.setVisible(bool(secondary))
        self._toggle.setText("More parameters (%d)" % len(secondary))
        self._more.setVisible(bool(secondary) and self._expanded)
        self._toggle.setArrowType(
            QtCore.Qt.DownArrow if self._expanded else QtCore.Qt.RightArrow)

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
        caption = QtGui.QLabel(spec.get("label") or name)
        widget = _widgetFor(spec)
        if name in self._auto:
            widget.setStyleSheet(
                "font-style: italic; color: %s;"
                % (self._tokens.get("text_dim", "#888888"),))
            widget.setToolTip("Derived from the other parameters. "
                              "Editing this pins it.")
        _connect(widget, name, self._onEdited)
        self._widgets[name] = widget
        grid.addWidget(caption, row, column * 2)
        grid.addWidget(widget, row, column * 2 + 1)

    def _onEdited(self, name):
        if name in self._auto:
            self._auto.discard(name)
            widget = self._widgets.get(name)
            if widget is not None:
                widget.setStyleSheet("")
                widget.setToolTip("")
        self.changed.emit()

    def _onToggle(self):
        self._expanded = not self._expanded
        self._more.setVisible(self._expanded)
        self._toggle.setArrowType(
            QtCore.Qt.DownArrow if self._expanded else QtCore.Qt.RightArrow)


def _widgetFor(spec):
    """One editor widget for a param spec, seeded from its default."""
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

    widget = QtGui.QDoubleSpinBox()
    widget.setRange(0.0, 100000.0)
    widget.setDecimals(0)
    widget.setSuffix(" deg" if kind == "Angle" else " mm")
    widget.setValue(float(default or 0))
    return widget


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
    for reader in ("value", "text", "isChecked"):
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
    for writer in ("setValue", "setText", "setChecked"):
        method = getattr(widget, writer, None)
        if method is None:
            continue
        if writer == "setValue":
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
