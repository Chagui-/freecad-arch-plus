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
                  nosing, treadThickness, riserThickness, flight, landings,
                  landingStep, winderSteps, winderHole, align, structure,
                  structureThickness, stringerWidth):
    """Write the panel's exposed values onto a _StairsPlus object.

    `landings` is a count (0 or 1); `landingStep` is the step the landing/turn
    sits on (0 = auto, centered); `winderSteps` is the number of wedge steps for
    a half-turn without a landing; `winderHole` is the square well half-size.
    All length values are in millimetres. Properties not exposed by the panel
    keep the defaults set at creation."""
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
    # The engine's Landings enum drives geometry; map the 0/1 count onto it.
    obj.Landings = "At center" if landings else "None"
    obj.LandingStep = int(landingStep)
    obj.WinderSteps = max(2, int(winderSteps))
    obj.WinderHoleSize = winderHole
    obj.Align = align
    obj.Structure = structure
    obj.StructureThickness = structureThickness
    obj.StringerWidth = stringerWidth


def makeStairsPlus(width=1000.0, height=3000.0, length=4000.0,
                   numberOfSteps=17, treadDepth=0.0, nosing=25.0,
                   treadThickness=50.0, riserThickness=50.0,
                   flight="Straight", landings=0, landingStep=0, winderSteps=3,
                   winderHole=0.0, align="Left", structure="Massive",
                   structureThickness=150.0, stringerWidth=120.0):
    """Create a _StairsPlus object configured with the given values."""
    import stairsplus_object

    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument()
    obj = stairsplus_object.makeStairsPlus()
    applySettings(obj, width, height, length, numberOfSteps, treadDepth,
                  nosing, treadThickness, riserThickness, flight, landings,
                  landingStep, winderSteps, winderHole, align, structure,
                  structureThickness, stringerWidth)
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
        self.form.setWindowTitle("Edit StairsPlus" if self.editing else "StairsPlus")
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))

        outer = QtGui.QVBoxLayout(self.form)

        # --- Shape & layout ------------------------------------------------
        shapeBox = QtGui.QGroupBox("Shape && layout")
        shapeForm = QtGui.QFormLayout(shapeBox)
        self.flight = QtGui.QComboBox()
        self.flight.addItems(["Straight", "HalfTurnLeft", "HalfTurnRight"])
        self.landings = QtGui.QSpinBox()
        self.landings.setRange(0, 1)
        self.landings.setToolTip("Number of landings (0 or 1)")
        self.landingStep = QtGui.QSpinBox()
        self.landingStep.setRange(0, 200)
        self.landingStep.setToolTip(
            "Step the landing/turn sits on (0 = auto, centered)")
        self.winderSteps = QtGui.QSpinBox()
        self.winderSteps.setRange(2, 50)      # winders are never fewer than 2
        self.winderSteps.setValue(3)
        self.winderSteps.setToolTip(
            "Winder (wedge) steps that sweep a half-turn when there is no "
            "landing (minimum 2).")
        self.winderHole = self._len(0)
        self.winderHole.setToolTip(
            "Half-size of the square hole (well) in the middle of the winder "
            "turn. 0 = winders meet at a point.")
        self.align = QtGui.QComboBox()
        self.align.addItems(["Left", "Right", "Center"])
        shapeForm.addRow("Flight / turn", self.flight)
        shapeForm.addRow("Landings (0 or 1)", self.landings)
        shapeForm.addRow("Landing/turn at step (0=auto)", self.landingStep)
        shapeForm.addRow("Winder steps (half-turn, no landing)", self.winderSteps)
        shapeForm.addRow("Winder hole half-size", self.winderHole)
        shapeForm.addRow("Alignment", self.align)
        outer.addWidget(shapeBox)

        # --- Dimensions ----------------------------------------------------
        dimBox = QtGui.QGroupBox("Dimensions")
        dimForm = QtGui.QFormLayout(dimBox)
        self.width = self._len(1000)
        self.height = self._len(3000)
        self.length = self._len(4000)
        dimForm.addRow("Width", self.width)
        dimForm.addRow("Total height (rise)", self.height)
        dimForm.addRow("Run length", self.length)
        outer.addWidget(dimBox)

        # --- Steps ---------------------------------------------------------
        stepBox = QtGui.QGroupBox("Steps")
        stepForm = QtGui.QFormLayout(stepBox)
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
        stepForm.addRow("Tread depth (0 = auto)", self.tread)
        stepForm.addRow("Nosing", self.nosing)
        stepForm.addRow("Tread thickness", self.treadTh)
        stepForm.addRow("Riser thickness", self.riserTh)
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

        # --- Comfort note (Blondel) ---------------------------------------
        self.comfort = QtGui.QLabel()
        self.comfort.setWordWrap(True)
        outer.addWidget(self.comfort)

        # Debounce timer: coalesce rapid edits into one recompute.
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        # Connect every input to the live-update scheduler.
        for w in (self.width, self.height, self.length, self.tread,
                  self.nosing, self.treadTh, self.riserTh, self.structTh,
                  self.stringerW, self.landings, self.landingStep,
                  self.winderSteps, self.winderHole):
            w.valueChanged.connect(self._schedule)
        self.steps.valueChanged.connect(self._schedule)
        for c in (self.flight, self.align, self.structure):
            c.currentIndexChanged.connect(self._schedule)
        # Landing-step input matters when a landing OR a half-turn exists, and
        # its max must track the step count (split must leave >=1 step/flight).
        self.landings.valueChanged.connect(self._syncLandingEnabled)
        self.flight.currentIndexChanged.connect(self._syncLandingEnabled)
        self.steps.valueChanged.connect(self._syncLandingStepRange)
        self._syncLandingEnabled()
        self._syncLandingStepRange()

        if self.editing:
            # Edit mode: load the object's current values, then open an
            # abortable transaction so Cancel reverts the edits.
            self._loadFromObject()
            self._building = False
            FreeCAD.ActiveDocument.openTransaction("Edit StairsPlus")
            self._updateComfort()
        else:
            # Create mode: build a live-preview object now.
            self._building = False
            self._startPreview()

    # --- widget helpers ----------------------------------------------------
    def _len(self, default):
        w = QtGui.QDoubleSpinBox()
        w.setRange(0, 1_000_000)
        w.setDecimals(1)
        w.setSuffix(" mm")
        w.setValue(default)
        return w

    def _collect(self):
        return dict(
            width=self.width.value(),
            height=self.height.value(),
            length=self.length.value(),
            numberOfSteps=self.steps.value(),
            treadDepth=self.tread.value(),
            nosing=self.nosing.value(),
            treadThickness=self.treadTh.value(),
            riserThickness=self.riserTh.value(),
            flight=self.flight.currentText(),
            landings=self.landings.value(),          # 0 or 1
            landingStep=self.landingStep.value(),    # 0 = auto (centered)
            winderSteps=self.winderSteps.value(),    # half-turn, no landing
            winderHole=self.winderHole.value(),      # square well half-size
            align=self.align.currentText(),
            structure=self.structure.currentText(),
            structureThickness=self.structTh.value(),
            stringerWidth=self.stringerW.value(),
        )

    def _syncLandingEnabled(self, *args):
        """Enable the landing-step input when there is a landing OR a half-turn.

        A half-turn splits the flight at the landing step (the turn point) even
        when no landing platform is drawn, so the step still matters there.
        Winder steps only apply to a half-turn that has no landing platform."""
        isHalfTurn = self.flight.currentText() in ("HalfTurnLeft", "HalfTurnRight")
        hasLanding = self.landings.value() > 0
        winders = isHalfTurn and not hasLanding
        self.landingStep.setEnabled(hasLanding or isHalfTurn)
        self.winderSteps.setEnabled(winders)
        self.winderHole.setEnabled(winders)

    def _syncLandingStepRange(self, *args):
        """Cap the landing step to [0, steps-1] so it can't exceed the flight.

        0 = auto (centered); 1..steps-1 places the landing after that step."""
        self.landingStep.setMaximum(max(1, self.steps.value() - 1))

    def _loadFromObject(self):
        """Populate the widgets from an existing object's properties.

        Runs while self._building is True so it doesn't trigger rebuilds."""
        o = self.obj
        self.width.setValue(o.Width.Value)
        self.height.setValue(o.Height.Value)
        self.length.setValue(o.Length.Value)
        self.steps.setValue(int(o.NumberOfSteps))
        self.tread.setValue(o.TreadDepthEnforce.Value)
        self.nosing.setValue(o.Nosing.Value)
        self.treadTh.setValue(o.TreadThickness.Value)
        self.riserTh.setValue(o.RiserThickness.Value)
        self.flight.setCurrentText(o.Flight)
        self.landings.setValue(1 if o.Landings == "At center" else 0)
        self.landingStep.setValue(int(getattr(o, "LandingStep", 0)))
        self.winderSteps.setValue(max(2, int(getattr(o, "WinderSteps", 0))))
        self.winderHole.setValue(getattr(o, "WinderHoleSize", 0).Value
                                 if hasattr(o, "WinderHoleSize") else 0)
        self.align.setCurrentText(o.Align)
        self.structure.setCurrentText(o.Structure)
        self.structTh.setValue(o.StructureThickness.Value)
        self.stringerW.setValue(o.StringerWidth.Value)

    # --- live preview ------------------------------------------------------
    def _startPreview(self):
        import stairsplus_object
        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("Create StairsPlus")
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
            FreeCAD.Console.PrintError("StairsPlus: %s\n" % exc)

    def _updateComfort(self):
        n = max(self.steps.value(), 1)
        riser = self.height.value() / n
        tread = self.tread.value()
        if not tread:  # auto: approx run / (steps - 1)
            tread = self.length.value() / max(n - 1, 1)
        blondel = 2 * riser + tread
        ok = 600 <= blondel <= 640        # comfortable range, mm
        colour = "#2ec27e" if ok else "#e01b24"
        verdict = "comfortable" if ok else "outside 600-640 mm comfort range"
        self.comfort.setText(
            "<b>Riser:</b> {:.0f} mm &nbsp; <b>Tread:</b> {:.0f} mm<br>"
            "<b>Blondel (2R + T):</b> "
            "<span style='color:{}'>{:.0f} mm - {}</span>".format(
                riser, tread, colour, blondel, verdict))

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
                "MenuText": "Create StairsPlus",
                "ToolTip": "Create a parametric stair via a configuration dialog"}

    def Activated(self):
        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()
        FreeCADGui.Control.showDialog(StairsPlusTaskPanel())

    def IsActive(self):
        return True


FreeCADGui.addCommand("StairsPlus_Create", StairsPlusCommand())
