# SPDX-License-Identifier: LGPL-2.1-or-later
#
# StairsPlus - a configuration-dialog front end for the _StairsPlus object.
#
# The Task panel creates a real _StairsPlus object as soon as it opens and
# updates its properties live (debounced) as you change the widgets, so the
# stair renders in the 3D view while you interact. OK keeps it; Cancel aborts
# the transaction, which removes the preview.

import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

# Make sibling modules (stairsplus_object) importable.
_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

ICON = os.path.join(_DIR, "Resources", "icons", "StairsPlus.svg")


# ---------------------------------------------------------------------------
# Apply a settings dict to an existing _StairsPlus object.
# ---------------------------------------------------------------------------
def applySettings(obj, width, height, length, numberOfSteps, treadDepth,
                  nosing, treadThickness, riserThickness, flight, breakSteps,
                  breakAtStep, align, structure, structureThickness,
                  stringerWidth):
    """Write the panel's exposed values onto a _StairsPlus object.

    `breakSteps` is the unified turn/break setting: 0 = none (continuous),
    1 = landing (flat platform), >=2 = winder (wedge) steps. `breakAtStep` is
    the step the break sits on. All length values are in millimetres."""
    obj.Width = width
    obj.Height = height
    obj.Length = length
    obj.NumberOfSteps = numberOfSteps
    obj.Nosing = nosing
    obj.TreadThickness = treadThickness
    obj.RiserThickness = riserThickness
    # TreadDepth is computed/read-only; TreadDepthEnforce overrides it (0 = auto).
    obj.TreadDepthEnforce = treadDepth
    obj.Flight = flight
    obj.Align = align

    # Map the unified break setting onto the engine's existing properties:
    #   0      -> no break (continuous flight)
    #   1      -> flat landing
    #   >= 2   -> winder steps (half-turn only; ignored for a straight flight)
    n = int(breakSteps)
    obj.LandingStep = int(breakAtStep)
    if n == 1:
        obj.Landings = "At center"      # flat landing
    else:
        obj.Landings = "None"
    if n >= 2:
        obj.WinderSteps = n             # winders (triggered on a half-turn)
    obj.WinderHoleSize = 0              # winder well not exposed (see TODO)

    obj.Structure = structure
    obj.StructureThickness = structureThickness
    obj.StringerWidth = stringerWidth


def makeStairsPlus(width=1000.0, height=3000.0, length=4000.0,
                   numberOfSteps=17, treadDepth=0.0, nosing=25.0,
                   treadThickness=50.0, riserThickness=50.0,
                   flight="Straight", breakSteps=0, breakAtStep=8,
                   align="Left", structure="Massive",
                   structureThickness=150.0, stringerWidth=120.0):
    """Create a _StairsPlus object configured with the given values."""
    import stairsplus_object

    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument()
    obj = stairsplus_object.makeStairsPlus()
    applySettings(obj, width, height, length, numberOfSteps, treadDepth,
                  nosing, treadThickness, riserThickness, flight, breakSteps,
                  breakAtStep, align, structure, structureThickness,
                  stringerWidth)
    FreeCAD.ActiveDocument.recompute()
    return obj


# ---------------------------------------------------------------------------
# Task panel - the docked configuration UI with live preview.
# ---------------------------------------------------------------------------
class StairsPlusTaskPanel:
    """Docked panel. FreeCAD supplies OK/Cancel and routes them to
    self.accept() / self.reject()."""

    def __init__(self, obj=None):
        self.obj = obj                 # None = create mode; object = edit mode
        self.editing = obj is not None
        self._building = True          # suppress live updates during widget setup

        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Edit Stairs" if self.editing else "Stairs")
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))

        outer = QtGui.QVBoxLayout(self.form)

        # --- Shape & layout ------------------------------------------------
        shapeBox = QtGui.QGroupBox("Shape && layout")
        shapeForm = QtGui.QFormLayout(shapeBox)
        self.flight = QtGui.QComboBox()
        self.flight.addItems(["Straight", "HalfTurnLeft", "HalfTurnRight"])

        # Unified break/turn setting (see _breakSteps / applySettings):
        #   straight  -> a Landing checkbox  (off = 0, on = 1)
        #   half-turn -> a Turn-steps spinbox (1 = landing, >=2 = winders)
        self.landingChk = QtGui.QCheckBox()
        self.landingChk.setToolTip("Add a flat landing partway up the flight")
        self.turnSteps = QtGui.QSpinBox()
        self.turnSteps.setRange(1, 50)
        self.turnSteps.setValue(3)
        self.turnSteps.setToolTip(
            "Steps that make up the turn. 1 = a flat landing; 2 or more = "
            "winder (wedge) steps that climb through the turn.")
        self.atStep = QtGui.QSpinBox()
        self.atStep.setRange(1, 200)
        self.atStep.setValue(8)               # centered for the default 17 steps
        self.atStep.setToolTip("The step the landing/turn sits on")
        self.align = QtGui.QComboBox()
        self.align.addItems(["Left", "Right", "Center"])

        # Rows for options that only apply to some shapes keep explicit label
        # widgets so they can be hidden together with their field.
        self._shapeForm = shapeForm
        shapeForm.addRow("Shape", self.flight)
        self.lblLanding = QtGui.QLabel("Landing")
        shapeForm.addRow(self.lblLanding, self.landingChk)
        self.lblTurnSteps = QtGui.QLabel("Turn steps (1 = landing)")
        shapeForm.addRow(self.lblTurnSteps, self.turnSteps)
        self.lblAtStep = QtGui.QLabel("At step")
        shapeForm.addRow(self.lblAtStep, self.atStep)
        shapeForm.addRow("Alignment", self.align)
        outer.addWidget(shapeBox)

        # --- Dimensions ----------------------------------------------------
        dimBox = QtGui.QGroupBox("Dimensions")
        dimV = QtGui.QVBoxLayout(dimBox)
        dimV.addWidget(self._refImage("dimensions_ref", QtCore.QSize(220, 130)))
        dimForm = QtGui.QFormLayout()
        self.width = self._len(1000)
        self.height = self._len(3000)
        self.length = self._len(4000)
        dimForm.addRow("W · Width (per flight)", self.width)
        dimForm.addRow("H · Total height (rise)", self.height)
        dimForm.addRow("L · Run length", self.length)
        dimV.addLayout(dimForm)
        outer.addWidget(dimBox)

        # --- Steps ---------------------------------------------------------
        stepBox = QtGui.QGroupBox("Steps")
        stepV = QtGui.QVBoxLayout(stepBox)
        stepV.addWidget(self._refImage("steps_ref", QtCore.QSize(210, 150)))
        stepForm = QtGui.QFormLayout()
        self.steps = QtGui.QSpinBox()
        self.steps.setRange(1, 200)
        self.steps.setValue(17)
        self.tread = self._len(0)          # 0 = let engine compute from length
        self.tread.setToolTip("0 = auto (computed from run length). "
                              "Set a value to enforce a fixed tread depth.")
        self.nosing = self._len(25)
        self.treadTh = self._len(50)
        self.riserTh = self._len(50)
        stepForm.addRow("Number of steps", self.steps)
        stepForm.addRow("T · Tread depth / going (0 = auto)", self.tread)
        stepForm.addRow("n · Nosing", self.nosing)
        stepForm.addRow("Tt · Tread thickness", self.treadTh)
        stepForm.addRow("Rt · Riser thickness", self.riserTh)
        stepV.addLayout(stepForm)
        # a (riser height, computed) + Blondel comfort note
        self.comfort = QtGui.QLabel()
        self.comfort.setWordWrap(True)
        stepV.addWidget(self.comfort)
        outer.addWidget(stepBox)

        # --- Structure -----------------------------------------------------
        structBox = QtGui.QGroupBox("Structure")
        structForm = QtGui.QFormLayout(structBox)
        self.structure = QtGui.QComboBox()
        self.structure.addItems(["None", "Massive", "One stringer", "Two stringers"])
        self.structure.setCurrentText("Massive")
        self.structTh = self._len(150)
        self.stringerW = self._len(120)
        structForm.addRow("Type", self.structure)
        structForm.addRow("Structure thickness", self.structTh)
        structForm.addRow("Stringer width", self.stringerW)
        outer.addWidget(structBox)

        # Debounce timer: coalesce rapid edits into one recompute.
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        # Connect every input to the live-update scheduler.
        for w in (self.width, self.height, self.length, self.tread,
                  self.nosing, self.treadTh, self.riserTh, self.structTh,
                  self.stringerW, self.turnSteps, self.atStep):
            w.valueChanged.connect(self._schedule)
        self.steps.valueChanged.connect(self._schedule)
        self.landingChk.toggled.connect(self._schedule)
        for c in (self.flight, self.align, self.structure):
            c.currentIndexChanged.connect(self._schedule)
        # Which break controls are shown depends on the shape and the landing
        # checkbox; the "at step" max must track the step count.
        self.flight.currentIndexChanged.connect(self._syncShapeRows)
        self.landingChk.toggled.connect(self._syncShapeRows)
        self.steps.valueChanged.connect(self._syncLandingStepRange)
        self._syncShapeRows()
        self._syncLandingStepRange()

        if self.editing:
            # Edit mode: load the object's current values, then open an
            # abortable transaction so Cancel reverts the edits.
            self._loadFromObject()
            self._building = False
            FreeCAD.ActiveDocument.openTransaction("Edit Stairs")
            self._updateComfort()
        else:
            # Create mode: build a live-preview object now.
            self._building = False
            self._startPreview()

    # --- widget helpers ----------------------------------------------------
    def _len(self, default):
        """A unit-aware length input. Gui::QuantitySpinBox shows/parses values
        in the user's configured unit schema (mm, cm, inch, ...) while storing
        the value internally in mm. Falls back to a plain mm spinbox if the
        FreeCAD widget can't be created (e.g. no GUI)."""
        try:
            w = FreeCADGui.UiLoader().createWidget("Gui::QuantitySpinBox")
            w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(default)))
            return w
        except Exception:
            w = QtGui.QDoubleSpinBox()
            w.setRange(0, 1_000_000)
            w.setDecimals(1)
            w.setSuffix(" mm")
            w.setValue(default)
            return w

    @staticmethod
    def _mm(w):
        """Read a length widget's value in millimetres (FreeCAD's base unit)."""
        try:
            return float(w.property("value").Value)   # Gui::QuantitySpinBox
        except Exception:
            return float(w.value())                    # plain QDoubleSpinBox

    @staticmethod
    def _setmm(w, mm):
        """Set a length widget from a value in millimetres."""
        try:
            w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(mm)))
        except Exception:
            w.setValue(float(mm))

    def _isHalfTurn(self):
        return self.flight.currentText() in ("HalfTurnLeft", "HalfTurnRight")

    def _breakSteps(self):
        """Unified break setting: 0 = none, 1 = landing, >=2 = winders.

        For a half-turn it is the Turn-steps spinbox (min 1); for a straight
        flight it is the Landing checkbox (1 if checked, else 0)."""
        if self._isHalfTurn():
            return self.turnSteps.value()
        return 1 if self.landingChk.isChecked() else 0

    def _collect(self):
        return dict(
            width=self._mm(self.width),
            height=self._mm(self.height),
            length=self._mm(self.length),
            numberOfSteps=self.steps.value(),
            treadDepth=self._mm(self.tread),
            nosing=self._mm(self.nosing),
            treadThickness=self._mm(self.treadTh),
            riserThickness=self._mm(self.riserTh),
            flight=self.flight.currentText(),
            breakSteps=self._breakSteps(),
            breakAtStep=self.atStep.value(),
            align=self.align.currentText(),
            structure=self.structure.currentText(),
            structureThickness=self._mm(self.structTh),
            stringerWidth=self._mm(self.stringerW),
        )

    def _refImage(self, name, size):
        """A centered QLabel holding a reference SVG (or empty if missing)."""
        lbl = QtGui.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        path = os.path.join(_DIR, "Resources", "icons", name + ".svg")
        if os.path.exists(path):
            lbl.setPixmap(QtGui.QIcon(path).pixmap(size))
        return lbl

    def _setRow(self, label, field, visible):
        """Show/hide a form row (label + field). Uses Qt's setRowVisible when
        available (Qt 6.4+), otherwise hides both widgets so the row collapses."""
        if hasattr(self._shapeForm, "setRowVisible"):
            self._shapeForm.setRowVisible(field, visible)
        else:
            label.setVisible(visible)
            field.setVisible(visible)

    def _syncShapeRows(self, *args):
        """Show only the break controls that apply to the current shape.

        - Straight: the Landing checkbox (a half-turn hides it).
        - Half-turn: the Turn-steps spinbox.
        - At step: whenever there is a break (half-turn, or landing checked)."""
        isHalfTurn = self._isHalfTurn()
        self._setRow(self.lblLanding, self.landingChk, not isHalfTurn)
        self._setRow(self.lblTurnSteps, self.turnSteps, isHalfTurn)
        hasBreak = isHalfTurn or self.landingChk.isChecked()
        self._setRow(self.lblAtStep, self.atStep, hasBreak)

    def _syncLandingStepRange(self, *args):
        """Cap the break position to [1, steps-1] so it leaves a step per side."""
        self.atStep.setMaximum(max(1, self.steps.value() - 1))

    def _loadFromObject(self):
        """Populate the widgets from an existing object's properties.

        Runs while self._building is True so it doesn't trigger rebuilds."""
        o = self.obj
        self._setmm(self.width, o.Width.Value)
        self._setmm(self.height, o.Height.Value)
        self._setmm(self.length, o.Length.Value)
        self.steps.setValue(int(o.NumberOfSteps))
        self._setmm(self.tread, o.TreadDepthEnforce.Value)
        self._setmm(self.nosing, o.Nosing.Value)
        self._setmm(self.treadTh, o.TreadThickness.Value)
        self._setmm(self.riserTh, o.RiserThickness.Value)
        self.flight.setCurrentText(o.Flight)
        # Reconstruct the unified break setting from the engine properties.
        nsteps = int(o.NumberOfSteps)
        isHalfTurn = o.Flight in ("HalfTurnLeft", "HalfTurnRight")
        if o.Landings == "At center":
            n = 1                                  # flat landing
        elif isHalfTurn:
            n = max(2, int(getattr(o, "WinderSteps", 2)))   # winders
        else:
            n = 0                                  # continuous straight flight
        self.landingChk.setChecked(n >= 1)
        self.turnSteps.setValue(max(1, n))
        # Break position: use the stored step, else the centered default.
        ls = int(getattr(o, "LandingStep", 0))
        self.atStep.setValue(ls if 1 <= ls <= nsteps - 1 else max(1, nsteps // 2))
        self.align.setCurrentText(o.Align)
        self.structure.setCurrentText(o.Structure)
        self._setmm(self.structTh, o.StructureThickness.Value)
        self._setmm(self.stringerW, o.StringerWidth.Value)

    # --- live preview ------------------------------------------------------
    def _startPreview(self):
        import stairsplus_object
        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("Create Stairs")
        self.obj = stairsplus_object.makeStairsPlus()
        self._apply()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    def _schedule(self, *args):
        """Called on any widget change: refresh comfort note, debounce rebuild."""
        self._updateComfort()
        if not self._building and self.obj is not None:
            self._timer.start()

    def _apply(self):
        """Push current widget values onto the preview object and recompute."""
        if self.obj is None:
            return
        try:
            applySettings(self.obj, **self._collect())
            FreeCAD.ActiveDocument.recompute()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus: %s\n" % exc)

    def _updateComfort(self):
        n = max(self.steps.value(), 1)
        riser = self._mm(self.height) / n
        tread = self._mm(self.tread)
        if not tread:  # auto: mirror the engine's tread-depth calculation
            length = self._mm(self.length)
            # A break (landing or winders) splits the run and reserves ~one
            # stair width for the turn region, so treads share (length - width)
            # over (steps - 2). A plain straight flight shares length / steps-1.
            hasSplit = self._breakSteps() >= 1 and n > 3
            if hasSplit:
                tread = (length - self._mm(self.width)) / max(n - 2, 1)
            else:
                tread = length / max(n - 1, 1)
        blondel = 2 * riser + tread
        ok = 600 <= blondel <= 640        # comfortable range, mm (internal)
        colour = "#2ec27e" if ok else "#e01b24"
        verdict = "comfortable" if ok else "outside comfort range"

        def q(v):  # format a mm value in the user's display unit
            try:
                return FreeCAD.Units.Quantity("%.6f mm" % v).UserString
            except Exception:
                return "%.0f mm" % v

        self.comfort.setText(
            "<b>R · Riser height:</b> {} &nbsp; "
            "<b>T · Tread depth:</b> {}<br>"
            "<b>Blondel (2R + T):</b> "
            "<span style='color:{}'>{} – {}</span>".format(
                q(riser), q(tread), colour, q(blondel), verdict))

    # --- task panel callbacks ---------------------------------------------
    def accept(self):
        # Flush any pending debounce, finalize the object.
        self._timer.stop()
        self._apply()
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        self.obj = None
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        # Abort the transaction -> the preview object is removed.
        self._timer.stop()
        self.obj = None
        FreeCAD.ActiveDocument.abortTransaction()
        FreeCAD.ActiveDocument.recompute()
        FreeCADGui.Control.closeDialog()
        return True


# ---------------------------------------------------------------------------
# Command - the toolbar/menu button.
# ---------------------------------------------------------------------------
class StairsPlusCommand:
    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Stairs",
                "ToolTip": "Create a parametric stair via a configuration dialog"}

    def Activated(self):
        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()
        FreeCADGui.Control.showDialog(StairsPlusTaskPanel())

    def IsActive(self):
        return True


FreeCADGui.addCommand("ArchPlus_Stairs", StairsPlusCommand())
