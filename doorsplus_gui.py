# SPDX-License-Identifier: LGPL-2.1-or-later
#
# DoorsPlus - a door-specific creation UI with live 3D preview.
#
# The Task panel creates a real _Window-based door object as soon as it opens
# and updates its properties live (debounced) as you change the widgets, so the
# door renders in the 3D view while you interact. OK keeps it; Cancel aborts
# the transaction, which removes the preview.
#
# Door types supported: Single swing, Double swing, Single sliding,
#   Double sliding, Opening only.
# Panel styles: Solid, Glass (full).

import json
import math
import os
import sys

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

_DIR = os.path.dirname(__file__)
if _DIR not in sys.path:
    sys.path.append(_DIR)

ICON = os.path.join(_DIR, "Resources", "icons", "DoorsPlus.svg")

# ---------------------------------------------------------------------------
# Spec persistence
# ---------------------------------------------------------------------------
# The native Window object only stores Width/Height/Frame. The remaining panel
# settings (operation, panel style, frame width/depth, swing, panel position)
# are persisted on the object as a hidden JSON string so they can be restored
# when the object is edited.
SPEC_PROP = "ArchPlusSpec"


def storeSpec(obj, spec):
    """Persist the ArchPlus creation spec on the object as JSON."""
    if obj is None:
        return
    if not hasattr(obj, SPEC_PROP):
        obj.addProperty("App::PropertyString", SPEC_PROP, "ArchPlus",
                        "Serialized ArchPlus settings (internal)")
        try:
            obj.setEditorMode(SPEC_PROP, 2)   # hidden from the property editor
        except Exception:
            pass
    setattr(obj, SPEC_PROP, json.dumps(spec))


def readSpec(obj):
    """Return the stored ArchPlus spec dict, or None if absent/unreadable."""
    raw = getattr(obj, SPEC_PROP, "") or ""
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except Exception:
        return None
    return d if isinstance(d, dict) else None

# ---------------------------------------------------------------------------
# Door type → preset mapping
# ---------------------------------------------------------------------------
DOOR_OPERATIONS = [
    "Single swing",
    "Double swing",
    "Sliding (single)",
    "Sliding (double)",
    "Opening only",
]

PANEL_STYLES = [
    "Solid",
    "Glass (full)",
]

SWING_SIDES = ["Left", "Right"]
SWING_DIRS = ["Inward", "Outward"]
PANEL_POSITIONS = ["Centered", "Front", "Back"]  # leaf position in frame depth


def _operationNeedsLeaves(op):
    """Return True if the operation creates one or more door leaves."""
    return op != "Opening only"


def _operationLeafCount(op):
    """Number of leaf panels for the given operation."""
    if op in ("Single swing", "Sliding (single)"):
        return 1
    if op in ("Double swing", "Sliding (double)"):
        return 2
    return 0


def _operationIsSliding(op):
    return "Sliding" in op


def _openingModeFor(op, leafIndex):
    """Return the opening Mode integer for a leaf.

    leafIndex: 0 = left leaf, 1 = right leaf (for double doors).

    Swing doors use Arc modes (hinged); sliding doors use Sliding mode.
    The direction (Inward/Outward) is handled by toggling between Mode 1/2
    (Arc 90 / Arc 90 inv) or Mode 9/10 (Sliding / Sliding inv).
    """
    if _operationIsSliding(op):
        return 9        # Both leaves use the same base mode; the inward/outward
                        # toggle and the geometry of each leaf's hinge edge cause
                        # them to slide in opposite (outward) world directions.
    # Swing
    if leafIndex == 0:
        return 1        # Arc 90
    return 2            # Arc 90 inv


def _openingModeInv(op, leafIndex):
    """The inverted version of the opening mode (for inward/outward toggle)."""
    pairs = {1: 2, 2: 1, 9: 10, 10: 9}
    return pairs.get(_openingModeFor(op, leafIndex), 1)


# ---------------------------------------------------------------------------
# Door geometry generation
# ---------------------------------------------------------------------------
def _makeDoorGeometry(spec):
    """Build a sketch and WindowParts array for the given door specification.

    spec keys:
        operation  : str  ("Single swing", "Double swing", ...)
        panelStyle : str  ("Solid", "Glass (full)")
        width      : float (mm, overall)
        height     : float (mm, overall)
        frameWidth : float (mm, jamb width h1)
        panelThk   : float (mm, door leaf thickness)
        frameDepth : float (mm, frame extrusion depth into wall)
        swingSide  : str  ("Left" / "Right")

    Always uses Mode1 (Arc 90) for the opening direction.  The user
    can invert the opening later via the right-click context menu
    ("Invert Opening Direction"), which toggles Mode1↔Mode2.
    This avoids the unreliable "inward"/"outward" distinction that
    depends on wall face orientation.

    Returns (sketch, windowParts).
    """

    import Part
    import Sketcher

    w = spec["width"]
    h = spec["height"]
    jw = spec["frameWidth"]           # jamb width (h1)
    pt = spec["panelThk"]             # panel thickness (w2)
    fd = spec["frameDepth"]           # frame depth (w1)
    op = spec["operation"]
    style = spec["panelStyle"]
    ss = spec.get("swingSide", "Left")
    sd = spec.get("swingDir", "Outward")
    pp = spec.get("panelPos", "Centered")    # leaf position within frame depth

    # Opening mode helper: Mode1 on left hinge opens opposite direction
    # of Mode1 on right hinge.  XOR hinge-side with inward to keep
    # "Inward"/"Outward" semantically consistent regardless of hinge.
    def _swingMode(leaf=0):
        m = _openingModeFor(op, leaf)
        if (ss == "Right") != (sd == "Inward"):
            m = _openingModeInv(op, leaf)
        return m

    # Defaults from ArchWindowPresets conventions
    h2 = jw                            # inner frame width same as outer
    tol = jw / 10 if jw > 0 else 1     # small gap to avoid auto-wire issues
    gla = 10                           # glass thickness divisor

    s = FreeCAD.ActiveDocument.addObject("Sketcher::SketchObject", "Sketch")
    wp = []

    # --- Helper: add a rectangle to the sketch ---
    def _rect(p1, p2, p3, p4):
        idx = s.GeometryCount
        s.addGeometry(Part.LineSegment(p1, p2))
        s.addGeometry(Part.LineSegment(p2, p3))
        s.addGeometry(Part.LineSegment(p3, p4))
        s.addGeometry(Part.LineSegment(p4, p1))
        s.addConstraint(Sketcher.Constraint("Coincident", idx, 2, idx + 1, 1))
        s.addConstraint(Sketcher.Constraint("Coincident", idx + 1, 2, idx + 2, 1))
        s.addConstraint(Sketcher.Constraint("Coincident", idx + 2, 2, idx + 3, 1))
        s.addConstraint(Sketcher.Constraint("Coincident", idx + 3, 2, idx, 1))
        s.addConstraint(Sketcher.Constraint("Horizontal", idx))
        s.addConstraint(Sketcher.Constraint("Horizontal", idx + 2))
        s.addConstraint(Sketcher.Constraint("Vertical", idx + 1))
        s.addConstraint(Sketcher.Constraint("Vertical", idx + 3))

    def _addFrame(outer_p1, outer_p2, outer_p3, outer_p4,
                  inner_p1, inner_p2, inner_p3, inner_p4):
        """Add outer+inner rectangles forming a frame."""
        _rect(outer_p1, outer_p2, outer_p3, outer_p4)
        _rect(inner_p1, inner_p2, inner_p3, inner_p4)

    # --- Build the outer frame (3-sided: left, right, top; bottom flush) ---
    # Outer rectangle
    outer = [
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(w, 0, 0),
        FreeCAD.Vector(w, h, 0),
        FreeCAD.Vector(0, h, 0),
    ]
    # Inner rectangle: frame on sides (jw) and top (jw), bottom flush at y=0
    inner = [
        FreeCAD.Vector(jw, 0, 0),
        FreeCAD.Vector(w - jw, 0, 0),
        FreeCAD.Vector(w - jw, h - jw, 0),
        FreeCAD.Vector(jw, h - jw, 0),
    ]

    _addFrame(*outer, *inner)
    # Overall Width & Height constraints
    s.addConstraint(Sketcher.Constraint("DistanceY", 1, h))
    s.addConstraint(Sketcher.Constraint("DistanceX", 0, w))
    s.renameConstraint(s.ConstraintCount - 2, "Height")
    s.renameConstraint(s.ConstraintCount - 1, "Width")
    # Frame width constraints (left, right, top)
    s.addConstraint(Sketcher.Constraint("DistanceY", 6, 2, 2, 2, jw))
    s.addConstraint(Sketcher.Constraint("DistanceX", 2, 2, 6, 2, jw))
    s.addConstraint(Sketcher.Constraint("DistanceX", 4, 2, 0, 2, jw))
    # Bottom flush: Y distance between inner bottom and outer bottom = 0
    s.addConstraint(Sketcher.Constraint("DistanceY", 0, 2, 4, 2, 0.0))
    # Pin outer to origin
    s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))

    cstart = s.ConstraintCount
    cname = 18  # constraint naming start index (after Width=16, Height=17)

    # Wire0 = outer frame wire (index 0), Wire1 = inner frame wire (index 1)
    offset_str = "0.00+V"
    fthk = fd - pt
    if fthk < 0:
        fthk = 0
    wp.append(["OuterFrame", "Frame", "Wire0,Wire1", "%.4f+V" % fthk, offset_str])

    # Where the leaf sits within the frame depth. The frame spans 0..fd along
    # the normal; the leaf is `pt` thick, so it can slide between the front face
    # (0) and the back (fd - pt). Centred is the natural default.
    if pp == "Front":
        panelZ = 0.0
    elif pp == "Back":
        panelZ = fthk
    else:                                    # Centered
        panelZ = fthk / 2.0
    leaf_off = "%.4f+V" % panelZ             # depth offset for solid leaves/frames
    glass_off = "%.4f+V" % (panelZ + pt / 2.0)   # glass sheet, mid-leaf

    leaf_count = _operationLeafCount(op)

    # Edge index helpers.  After the outer frame (2 rectangles via _addFrame),
    # the sketch has 8 edges (0–7).  Wire0 = edges 0-3, Wire1 = edges 4-7.
    # Each additional rectangle adds 4 edges.
    # Global edge indices (1-based, as used in WindowParts strings):
    _BASE_EDGES = 8          # edges consumed by the outer frame
    _W1_LEFT   = 8           # Wire1 left   = global edge  7 → Edge8
    _W1_RIGHT  = 6           # Wire1 right  = global edge  5 → Edge6

    if leaf_count == 1 and not _operationIsSliding(op) and style == "Solid":
        # Single swing / solid — door leaf = Wire1 (the inner opening)
        hinge = _W1_LEFT if ss == "Left" else _W1_RIGHT
        wp.append(["Door", "Solid panel", "Wire1,Edge%d,Mode%d" % (hinge, _swingMode()),
                   "%.4f" % pt, leaf_off])

    elif leaf_count == 1 and _operationIsSliding(op) and style == "Solid":
        # Single sliding / solid
        wp.append(["Door", "Solid panel", "Wire1,Edge8,Mode%d" % _swingMode(),
                   "%.4f" % pt, leaf_off])

    elif leaf_count == 1 and style == "Glass (full)":
        # Single door with full glass — inner frame + glass inside the door leaf.
        # Wire2 (edges 8-11): inner frame outer
        # Wire3 (edges 12-15): inner frame inner (glass opening)
        inner_frame_outer = [
            FreeCAD.Vector(jw + tol, 0.0, 0),
            FreeCAD.Vector(w - jw - tol, 0.0, 0),
            FreeCAD.Vector(w - jw - tol, h - jw - tol, 0),
            FreeCAD.Vector(jw + tol, h - jw - tol, 0),
        ]
        inner_frame_inner = [
            FreeCAD.Vector(jw + h2, 0.0, 0),
            FreeCAD.Vector(w - jw - h2, 0.0, 0),
            FreeCAD.Vector(w - jw - h2, h - jw - h2, 0),
            FreeCAD.Vector(jw + h2, h - jw - h2, 0),
        ]
        _addFrame(*inner_frame_outer, *inner_frame_inner)
        hinge = _W1_LEFT if ss == "Left" else _W1_RIGHT
        fw = "%.4f" % pt
        wp.append(["InnerFrame", "Frame", "Wire2,Wire3,Edge%d,Mode%d" % (hinge, _swingMode()),
                   fw, leaf_off])
        wp.append(["InnerGlass", "Glass panel", "Wire3",
                   "%.4f" % (pt / gla), glass_off])

    elif leaf_count == 2 and style == "Solid":
        # Double door — split the inner opening into two leaves.
        # Wire1 = full opening (used by frame)
        # Wire2 = left leaf  → edges 8-11
        # Wire3 = right leaf → edges 12-15
        half = w / 2.0
        _rect(*[FreeCAD.Vector(jw + tol, 0.0, 0),
                FreeCAD.Vector(half - tol, 0.0, 0),
                FreeCAD.Vector(half - tol, h - jw - tol, 0),
                FreeCAD.Vector(jw + tol, h - jw - tol, 0)])   # Wire2
        _rect(*[FreeCAD.Vector(half + tol, 0.0, 0),
                FreeCAD.Vector(w - jw - tol, 0.0, 0),
                FreeCAD.Vector(w - jw - tol, h - jw - tol, 0),
                FreeCAD.Vector(half + tol, h - jw - tol, 0)])  # Wire3

        # Wire2 left edge  = edge 11 (1-based: Edge12)
        # Wire3 right edge = edge 13 (1-based: Edge14)
        wp.append(["LeftDoor", "Solid panel", "Wire2,Edge12,Mode%d" % _swingMode(0),
                   "%.4f" % pt, leaf_off])
        wp.append(["RightDoor", "Solid panel", "Wire3,Edge14,Mode%d" % _swingMode(1),
                   "%.4f" % pt, leaf_off])

    elif leaf_count == 2 and style == "Glass (full)":
        # Double glass door — glass in each leaf.
        half = w / 2.0
        _addFrame(*[FreeCAD.Vector(jw + tol, 0.0, 0),
                    FreeCAD.Vector(half - tol, 0.0, 0),
                    FreeCAD.Vector(half - tol, h - jw - tol, 0),
                    FreeCAD.Vector(jw + tol, h - jw - tol, 0)],
                  *[FreeCAD.Vector(jw + h2, 0.0, 0),
                    FreeCAD.Vector(half - h2, 0.0, 0),
                    FreeCAD.Vector(half - h2, h - jw - h2, 0),
                    FreeCAD.Vector(jw + h2, h - jw - h2, 0)])  # Wire2, Wire3
        _addFrame(*[FreeCAD.Vector(half + tol, 0.0, 0),
                    FreeCAD.Vector(w - jw - tol, 0.0, 0),
                    FreeCAD.Vector(w - jw - tol, h - jw - tol, 0),
                    FreeCAD.Vector(half + tol, h - jw - tol, 0)],
                  *[FreeCAD.Vector(half + h2, 0.0, 0),
                    FreeCAD.Vector(w - jw - h2, 0.0, 0),
                    FreeCAD.Vector(w - jw - h2, h - jw - h2, 0),
                    FreeCAD.Vector(half + h2, h - jw - h2, 0)])  # Wire4, Wire5

        wp.append(["LeftFrame", "Frame", "Wire2,Wire3,Edge12,Mode%d" % _swingMode(0),
                   "%.4f" % pt, leaf_off])
        wp.append(["LeftGlass", "Glass panel", "Wire3",
                   "%.4f" % (pt / gla), glass_off])
        wp.append(["RightFrame", "Frame", "Wire4,Wire5,Edge18,Mode%d" % _swingMode(1),
                   "%.4f" % pt, leaf_off])
        wp.append(["RightGlass", "Glass panel", "Wire5",
                   "%.4f" % (pt / gla), glass_off])

    elif op == "Opening only":
        # Just a single rectangle — no door leaf, just the hole
        # We already have Wire0 (outer) and Wire1 (inner), but for opening only
        # we want just one wire for the opening. Overwrite with a simple rectangle.
        # Actually, the existing sketch structure works — Wire0=outer, Wire1=inner.
        # We just don't add any door/glass components.
        pass

    # Flatten WindowParts list for the property (5-element groups)
    flat = []
    for part in wp:
        flat.extend(part)

    return s, flat


# ---------------------------------------------------------------------------
# Apply door settings to an existing _Window object
# ---------------------------------------------------------------------------
def applyDoorSettings(obj, spec):
    """Push door spec onto an _Window object."""
    sketch, wp = _makeDoorGeometry(spec)
    # Replace the object's base sketch
    obj.Base = sketch
    obj.WindowParts = wp
    obj.Width = spec["width"]
    obj.Height = spec["height"]
    obj.Frame = spec["panelThk"]
    obj.Offset = 0
    obj.Preset = 0  # custom (not a built-in preset)
    obj.Label = "Door"


def makeDoor(width=900.0, height=2100.0, operation="Single swing",
             panelStyle="Solid", frameWidth=70.0, panelThk=45.0,
             frameDepth=100.0, swingSide="Left", swingDir="Inward"):
    """Create a _Window-based door object with the given parameters."""
    import doorsplus_object

    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument()

    spec = dict(
        operation=operation,
        panelStyle=panelStyle,
        width=width,
        height=height,
        frameWidth=frameWidth,
        panelThk=panelThk,
        frameDepth=frameDepth,
        swingSide=swingSide,
        swingDir=swingDir,
    )

    sketch, wp = _makeDoorGeometry(spec)
    FreeCAD.ActiveDocument.recompute()

    obj = doorsplus_object.makeWindow(sketch, width, height, wp)
    if obj is None:
        # makeWindow returns None if Arch module isn't available;
        # fall back to creating the _Window object ourselves
        obj = FreeCAD.ActiveDocument.addObject(
            "Part::FeaturePython", "Door", doorsplus_object._Window())
        doorsplus_object._Window(obj)
        obj.Base = sketch
        obj.WindowParts = wp

    obj.Width = width
    obj.Height = height
    obj.Frame = panelThk
    obj.Offset = 0
    obj.Label = "Door"

    FreeCAD.ActiveDocument.recompute()
    return obj


def _recomputeWithHosts(obj):
    """Recompute the door, then re-cut its host walls in the same edit.

    A hosted window is computed BEFORE its host wall in the dependency graph,
    so one recompute leaves the wall still cutting the door's previous shape and
    position — the change only appears after some later recompute. Touching the
    hosts and recomputing again makes the wall opening follow the door now."""
    if obj is None:
        return
    doc = obj.Document
    doc.recompute()
    touched = False
    for h in (getattr(obj, "Hosts", None) or []):
        try:
            h.touch()
            touched = True
        except Exception:
            pass
    if touched:
        doc.recompute()


# ---------------------------------------------------------------------------
# Task panel
# ---------------------------------------------------------------------------
class DoorsPlusTaskPanel:
    """Docked panel. FreeCAD supplies OK/Cancel and routes them to
    self.accept() / self.reject()."""

    def __init__(self, obj=None, placed=False):
        self.obj = obj                 # None = create; object = edit or placed
        self.editing = obj is not None and not placed
        self.placed = placed           # True: door was just placed, config it
        self._building = True          # suppress live updates during widget setup
        self._sketch = None            # the door's base sketch

        title = "Door"
        if self.editing:
            title = "Edit Door"
        elif self.placed:
            title = "Configure Door"
        self.form = QtGui.QWidget()
        self.form.setWindowTitle(title)
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))

        outer = QtGui.QVBoxLayout(self.form)

        # ---- Operation & style --------------------------------------------
        typeBox = QtGui.QGroupBox("Door Type")
        typeForm = QtGui.QFormLayout(typeBox)
        self.operation = QtGui.QComboBox()
        self.operation.addItems(DOOR_OPERATIONS)
        self.panelStyle = QtGui.QComboBox()
        self.panelStyle.addItems(PANEL_STYLES)
        self.panelPos = QtGui.QComboBox()
        self.panelPos.addItems(PANEL_POSITIONS)
        self.panelPos.setToolTip(
            "Where the leaf sits within the frame depth: centred, flush to the "
            "front face, or flush to the back.")
        typeForm.addRow("Operation", self.operation)
        typeForm.addRow("Panel style", self.panelStyle)
        typeForm.addRow("Panel position", self.panelPos)
        outer.addWidget(typeBox)

        # ---- Swing --------------------------------------------------------
        swingBox = QtGui.QGroupBox("Swing")
        swingForm = QtGui.QFormLayout(swingBox)
        self.swingSide = QtGui.QComboBox()
        self.swingSide.addItems(SWING_SIDES)
        self.swingDir = QtGui.QComboBox()
        self.swingDir.addItems(SWING_DIRS)
        swingForm.addRow("Hinge side", self.swingSide)
        swingForm.addRow("Direction", self.swingDir)
        self._swingBox = swingBox
        self._swingForm = swingForm
        outer.addWidget(swingBox)

        # ---- Dimensions ---------------------------------------------------
        dimBox = QtGui.QGroupBox("Dimensions")
        dimV = QtGui.QVBoxLayout(dimBox)
        # Dimension reference diagram
        self._dimRefSize = QtCore.QSize(220, 130)
        self.dimRef = self._refImage("dimensions_ref_door", self._dimRefSize)
        dimV.addWidget(self.dimRef)
        dimForm = QtGui.QFormLayout()
        self.width = self._len(900)
        self.height = self._len(2100)
        self.frameWidth = self._len(70)
        self.frameWidth.setToolTip("Jamb width — the width of the frame on sides and top")
        self.panelThk = self._len(45)
        self.panelThk.setToolTip("Thickness of the door leaf/panel")
        self.frameDepth = self._len(100)
        self.frameDepth.setToolTip("Depth of the frame into the wall (perpendicular to opening)")
        dimForm.addRow("W · Overall width", self.width)
        dimForm.addRow("H · Overall height", self.height)
        dimForm.addRow("Fw · Frame width (jamb)", self.frameWidth)
        dimForm.addRow("Pt · Panel thickness", self.panelThk)
        dimForm.addRow("Fd · Frame depth", self.frameDepth)
        dimV.addLayout(dimForm)
        outer.addWidget(dimBox)

        # ---- Position -----------------------------------------------------
        # A door is placed and moved with the mouse (see DoorsPlusCommand /
        # repositionDoor), sitting on the wall base by default. The sill field
        # raises it above that base (e.g. a raised threshold or a window-like
        # door over a low wall); the button re-enters mouse placement.
        posBox = QtGui.QGroupBox("Position")
        posV = QtGui.QVBoxLayout(posBox)
        posForm = QtGui.QFormLayout()
        self.sill = self._len(0)
        self.sill.setToolTip(
            "Height of the door's base above the wall base (the floor). "
            "0 sits it on the floor; increase to raise it (e.g. a threshold, or "
            "a door set partway up the wall with steps below).")
        posForm.addRow("Height above wall base", self.sill)
        posV.addLayout(posForm)
        self.repositionBtn = QtGui.QPushButton("Reposition with mouse…")
        self.repositionBtn.setToolTip(
            "Pick a new location for this door in the 3D view. It re-orients to "
            "the wall face you point at and drops to the floor automatically.")
        self.repositionBtn.clicked.connect(self._reposition)
        posV.addWidget(self.repositionBtn)
        outer.addWidget(posBox)

        # ---- Opening preview ----------------------------------------------
        openBox = QtGui.QGroupBox("3D Opening")
        openV = QtGui.QVBoxLayout(openBox)
        self.opening = QtGui.QSlider(QtCore.Qt.Horizontal)
        self.opening.setRange(0, 100)
        self.opening.setValue(0)
        self.opening.setTickInterval(10)
        self.opening.setTickPosition(QtGui.QSlider.TicksBelow)
        openLbl = QtGui.QLabel("0%")
        openLbl.setAlignment(QtCore.Qt.AlignCenter)
        self._openLbl = openLbl
        openV.addWidget(openLbl)
        openV.addWidget(self.opening)
        # Symbol display toggles
        symForm = QtGui.QFormLayout()
        self.symbolPlan = QtGui.QCheckBox()
        self.symbolPlan.setToolTip("Show plan opening symbol (swing arc)")
        self.symbolElev = QtGui.QCheckBox()
        self.symbolElev.setToolTip("Show elevation opening symbol")
        symForm.addRow("Plan symbol", self.symbolPlan)
        symForm.addRow("Elevation symbol", self.symbolElev)
        openV.addLayout(symForm)
        outer.addWidget(openBox)

        # ---- Metadata -----------------------------------------------------
        metaBox = QtGui.QGroupBox("Metadata")
        metaForm = QtGui.QFormLayout(metaBox)
        self.tag = QtGui.QLineEdit()
        self.tag.setPlaceholderText("e.g. D01")
        self.fireRating = QtGui.QComboBox()
        self.fireRating.addItems(["None", "FD30", "FD60", "FD90", "FD120"])
        self.isExternal = QtGui.QCheckBox()
        metaForm.addRow("Tag / Mark", self.tag)
        metaForm.addRow("Fire rating", self.fireRating)
        metaForm.addRow("External door", self.isExternal)
        outer.addWidget(metaBox)

        # Debounce timer
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        # Connect widgets to live-update scheduler
        for w in (self.width, self.height, self.frameWidth, self.panelThk,
                  self.frameDepth):
            w.valueChanged.connect(self._schedule)
        # Sill only moves the door vertically; handle it directly (no rebuild).
        self.sill.valueChanged.connect(self._onSillChanged)
        self.opening.valueChanged.connect(self._onOpeningChanged)
        for c in (self.operation, self.panelStyle, self.panelPos, self.swingSide,
                  self.swingDir, self.fireRating):
            c.currentIndexChanged.connect(self._schedule)
        self.symbolPlan.toggled.connect(self._onSymbolToggled)
        self.symbolElev.toggled.connect(self._onSymbolToggled)
        # Set checked AFTER connecting so the signal reaches the object.
        self.symbolPlan.setChecked(True)
        self.symbolElev.setChecked(False)
        self.operation.currentIndexChanged.connect(self._syncOperationRows)
        self._syncOperationRows()

        if self.editing:
            self._loadFromObject()
            self._building = False
            FreeCAD.ActiveDocument.openTransaction("Edit Door")
        elif self.placed:
            # Door was just created by the command; transaction already open.
            self._sketch = self.obj.Base
            # Reflect the actually-placed size (width can be changed in the
            # placement step) so the panel matches what was built and a later
            # edit doesn't silently resize it. Done while _building is True so
            # it doesn't trigger a rebuild.
            self._setmm(self.width, self.obj.Width.Value)
            self._setmm(self.height, self.obj.Height.Value)
            self._setmm(self.panelThk, self.obj.Frame.Value)
            self._loadSill()
            self._building = False
            # Sync initial symbol state to the placed door.
            self._onSymbolToggled()
        else:
            self._building = False
            self._startPreview()

    # ---- widget helpers ---------------------------------------------------
    def _len(self, default):
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
        try:
            return float(w.property("value").Value)
        except Exception:
            return float(w.value())

    @staticmethod
    def _setmm(w, mm):
        try:
            w.setProperty("value", FreeCAD.Units.Quantity("%.6f mm" % float(mm)))
        except Exception:
            w.setValue(float(mm))

    def _refImage(self, name, size):
        lbl = QtGui.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        path = os.path.join(_DIR, "Resources", "icons", name + ".svg")
        if os.path.exists(path):
            lbl.setPixmap(QtGui.QIcon(path).pixmap(size))
        return lbl

    def _collect(self):
        return dict(
            operation=self.operation.currentText(),
            panelStyle=self.panelStyle.currentText(),
            width=self._mm(self.width),
            height=self._mm(self.height),
            frameWidth=self._mm(self.frameWidth),
            panelThk=self._mm(self.panelThk),
            frameDepth=self._mm(self.frameDepth),
            swingSide=self.swingSide.currentText(),
            swingDir=self.swingDir.currentText(),
            panelPos=self.panelPos.currentText(),
        )

    def _syncOperationRows(self):
        """Show swing controls only for hinged (non-sliding) operations."""
        op = self.operation.currentText()
        hasSwing = op in ("Single swing", "Double swing")
        self._swingBox.setVisible(hasSwing)

    def _onOpeningChanged(self, val):
        self._openLbl.setText("%d%%" % val)
        if self.obj is not None:
            try:
                self.obj.Opening = val
                FreeCAD.ActiveDocument.recompute()
            except Exception:
                pass

    def _onSymbolToggled(self, *args):
        if self.obj is not None:
            try:
                self.obj.SymbolPlan = self.symbolPlan.isChecked()
                self.obj.SymbolElevation = self.symbolElev.isChecked()
                FreeCAD.ActiveDocument.recompute()
            except Exception:
                pass

    def _loadSill(self):
        """Set the sill widget from the door's current height above its host."""
        if self._sketch is None:
            return
        baseZ = self._hostBaseZ()
        if baseZ is None:
            baseZ = 0.0
        self._setmm(self.sill, max(0.0, self._sketch.Placement.Base.z - baseZ))

    def _hostBaseZ(self):
        """Lowest base level of the door's host wall(s), or None if unhosted."""
        zs = []
        for h in (getattr(self.obj, "Hosts", None) or []):
            try:
                zs.append(h.Shape.BoundBox.ZMin)
            except Exception:
                pass
        return min(zs) if zs else None

    def _onSillChanged(self, *args):
        """Raise/lower the door so its base sits `sill` above the wall base.

        Only the vertical (Z) coordinate of the base sketch is moved; doors live
        in vertical walls, so this keeps the door in the wall plane. Measured
        from the host wall base, or from the global origin if unhosted."""
        if self._building or self.obj is None or self._sketch is None:
            return
        baseZ = self._hostBaseZ()
        if baseZ is None:
            baseZ = 0.0
        pl = self._sketch.Placement
        newPl = FreeCAD.Placement(pl)
        newPl.Base = FreeCAD.Vector(pl.Base.x, pl.Base.y,
                                    baseZ + self._mm(self.sill))
        self._sketch.Placement = newPl
        _recomputeWithHosts(self.obj)

    # ---- repositioning ----------------------------------------------------
    def _reposition(self):
        """Close the panel (keeping edits) and re-place the door with the mouse."""
        if self.obj is None:
            return
        door = self.obj
        # Commit + close the panel: a Snapper pick can't run while this task
        # dialog owns the task view. repositionDoor re-shows the panel when the
        # move finishes (or is cancelled), so it feels like it stayed open.
        self.accept()
        QtCore.QTimer.singleShot(0, lambda: repositionDoor(door, reopen=True))

    # ---- live preview -----------------------------------------------------
    def _startPreview(self):
        import doorsplus_object

        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("Create Door")

        spec = self._collect()
        sketch, wp = _makeDoorGeometry(spec)
        FreeCAD.ActiveDocument.recompute()
        self._sketch = sketch

        obj = doorsplus_object.makeWindow(sketch, spec["width"], spec["height"], wp)
        if obj is None:
            obj = FreeCAD.ActiveDocument.addObject(
                "Part::FeaturePython", "Door", doorsplus_object._Window())
            doorsplus_object._Window(obj)
            obj.Base = sketch
            obj.WindowParts = wp

        obj.Width = spec["width"]
        obj.Height = spec["height"]
        obj.Frame = spec["panelThk"]
        obj.Offset = 0
        obj.Label = "Door"
        self.obj = obj

        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    def _schedule(self, *args):
        if not self._building and self.obj is not None:
            self._timer.start()

    def _apply(self):
        if self.obj is None:
            return
        try:
            spec = self._collect()
            old_sketch = self._sketch
            old_pl = None
            if old_sketch is not None and hasattr(old_sketch, "Placement"):
                old_pl = old_sketch.Placement

            sketch, wp = _makeDoorGeometry(spec)
            self._sketch = sketch

            if old_pl is not None:
                sketch.Placement = old_pl

            # Detach old sketch BEFORE assigning new one, so FreeCAD
            # doesn't hold internal references that block the swap.
            self.obj.Base = None
            self.obj.Base = sketch
            self.obj.WindowParts = wp
            self.obj.Width = spec["width"]
            self.obj.Height = spec["height"]
            self.obj.Frame = spec["panelThk"]

            # Apply opening percentage and symbols
            self.obj.Opening = self.opening.value()
            if hasattr(self.obj, "SymbolPlan"):
                self.obj.SymbolPlan = self.symbolPlan.isChecked()
            if hasattr(self.obj, "SymbolElevation"):
                self.obj.SymbolElevation = self.symbolElev.isChecked()

            # Persist the spec so it can be restored when the object is edited.
            storeSpec(self.obj, spec)

            # Touch the object so recompute is guaranteed to rebuild it, then
            # re-cut the host wall so the change is visible immediately.
            self.obj.touch()
            _recomputeWithHosts(self.obj)

            # Now that the new sketch is fully in use, remove the old one.
            if old_sketch is not None and old_sketch != sketch:
                try:
                    FreeCAD.ActiveDocument.removeObject(old_sketch.Name)
                except Exception:
                    pass

        except Exception as exc:
            import traceback
            FreeCAD.Console.PrintError(
                "DoorsPlus _apply error: %s\n%s\n" % (exc, traceback.format_exc()))

    # ---- load from existing object (edit mode) -----------------------------
    def _loadFromObject(self):
        o = self.obj
        self._sketch = o.Base            # needed for placement reuse on rebuild
        spec = readSpec(o)
        if spec:
            # Populate the widgets from the stored spec.
            self.operation.setCurrentText(spec.get("operation", "Single swing"))
            self.panelStyle.setCurrentText(spec.get("panelStyle", "Solid"))
            self._setmm(self.width, spec.get("width", o.Width.Value))
            self._setmm(self.height, spec.get("height", o.Height.Value))
            self._setmm(self.frameWidth, spec.get("frameWidth", 70))
            self._setmm(self.panelThk, spec.get("panelThk", o.Frame.Value))
            self._setmm(self.frameDepth, spec.get("frameDepth", 100))
            self.swingSide.setCurrentText(spec.get("swingSide", "Left"))
            self.swingDir.setCurrentText(spec.get("swingDir", "Inward"))
            self.panelPos.setCurrentText(spec.get("panelPos", "Centered"))
        else:
            # Legacy object with no stored spec: restore what the native
            # properties hold; frame width/depth fall back to the defaults.
            self._setmm(self.width, o.Width.Value)
            self._setmm(self.height, o.Height.Value)
            self._setmm(self.frameWidth, 70)
            self._setmm(self.panelThk, o.Frame.Value)
            self._setmm(self.frameDepth, 100)
        self.opening.setValue(int(getattr(o, "Opening", 0)))
        self._loadSill()
        if hasattr(o, "SymbolPlan"):
            self.symbolPlan.setChecked(o.SymbolPlan)
        if hasattr(o, "SymbolElevation"):
            self.symbolElev.setChecked(o.SymbolElevation)

    # ---- task panel callbacks ----------------------------------------------
    def accept(self):
        self._timer.stop()
        self._apply()
        FreeCAD.ActiveDocument.commitTransaction()
        FreeCAD.ActiveDocument.recompute()
        self.obj = None
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        self._timer.stop()
        self.obj = None
        FreeCAD.ActiveDocument.abortTransaction()
        FreeCAD.ActiveDocument.recompute()
        FreeCADGui.Control.closeDialog()
        return True


# ---------------------------------------------------------------------------
# Mouse placement helpers (shared by create + reposition)
# ---------------------------------------------------------------------------
def _doorPlacement(point, baseFace, width, snapBase=True, baseOffset=0.0):
    """Build the door placement for a picked point.

    - Orientation: from the picked wall face (or the working plane if none).
    - Floor snap: drop to the host's base so you only aim along the wall.
    - Centring: the door sketch origin is its bottom-left corner, so shift half
      the width back along the wall — the door then lands centred on the cursor,
      matching the preview box (instead of off to one side)."""
    import WorkingPlane
    import DraftGeomUtils

    wp = WorkingPlane.get_working_plane()
    if baseFace is not None:
        f = baseFace[0].Shape.Faces[baseFace[1]]
        pl = DraftGeomUtils.placement_from_face(f, vec_z=wp.axis)
    else:
        pl = FreeCAD.Placement()
        pl.Rotation = FreeCAD.Rotation(wp.u, wp.axis, -wp.v, "XZY")

    host = baseFace[0] if baseFace is not None else None
    if snapBase and host is not None:
        try:
            point = FreeCAD.Vector(point.x, point.y,
                                   host.Shape.BoundBox.ZMin + float(baseOffset))
        except Exception:
            pass

    u = pl.Rotation.multVec(FreeCAD.Vector(1, 0, 0))   # along-wall direction
    if u.Length > 1e-9:
        u = FreeCAD.Vector(u.x / u.Length, u.y / u.Length, u.z / u.Length)
        point = point.add(u.multiply(-width / 2.0))
    pl.Base = point
    return pl


def _placeTracker(tracker, pl, width, height):
    """Position a box tracker to preview a door at placement `pl`.

    Orients the box so x=along-wall, y=depth, z=up, and centres it on the door
    footprint (whose origin is the bottom-left corner) — so the preview matches
    exactly where _doorPlacement will put the door."""
    u = pl.Rotation.multVec(FreeCAD.Vector(1, 0, 0))
    up = pl.Rotation.multVec(FreeCAD.Vector(0, 1, 0))
    n = pl.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
    tracker.setRotation(FreeCAD.Rotation(u, n, up, "XYZ"))
    tracker.pos(pl.multVec(FreeCAD.Vector(width / 2.0, height / 2.0, 0)))


def repositionDoor(door, reopen=False):
    """Move an existing door to a new mouse-picked location.

    Re-uses the same placement rules as creation (orient to the picked wall
    face, floor-snap, centre on the cursor). Runs its own Snapper session, so
    it must be invoked with no task dialog open (e.g. from the context menu, or
    after the panel closes). When `reopen` is True the DoorsPlus panel is
    re-shown afterwards — used by the panel's Reposition button, which has to
    close the panel to free the task view for the pick."""
    if door is None or getattr(door, "Base", None) is None:
        return
    import draftguitools.gui_trackers as DraftTrackers

    doc = door.Document
    width = door.Width.Value
    height = door.Height.Value
    depth = door.Frame.Value if hasattr(door, "Frame") else 100.0
    state = {"face": None}

    tracker = DraftTrackers.boxTracker()
    tracker.length(width)
    tracker.width(depth)
    tracker.height(height)
    tracker.on()

    def _move(point, info):
        if info and "Face" in info.get("Component", ""):
            o = doc.getObject(info["Object"])
            try:
                fi = int(info["Component"][4:]) - 1
            except (ValueError, IndexError):
                state["face"] = None
            else:
                state["face"] = [o, fi]
        _placeTracker(tracker, _doorPlacement(point, state["face"], width),
                      width, height)

    def _place(point=None, obj=None):
        FreeCADGui.Snapper.off()
        tracker.off()
        try:
            if point is None:
                return                       # cancelled
            doc.openTransaction("Reposition Door")
            door.Base.Placement = _doorPlacement(point, state["face"], width)
            if state["face"] is not None:
                import Draft
                host = state["face"][0]
                if Draft.getType(host) in ("Wall", "Structure", "Roof"):
                    door.Hosts = [host]
            # Moving the sketch placement touches the door but NOT its host, so
            # the old opening would linger. Force the door, then re-cut wall(s).
            door.touch()
            _recomputeWithHosts(door)
            doc.commitTransaction()
        finally:
            tracker.finalize()
            # Re-show the panel that closed itself to make room for the pick.
            if reopen:
                QtCore.QTimer.singleShot(
                    0, lambda: FreeCADGui.Control.showDialog(
                        DoorsPlusTaskPanel(door)))

    FreeCAD.Console.PrintMessage(
        "DoorsPlus: click a new location for the door.\n")
    FreeCADGui.Snapper.getPoint(callback=_place, movecallback=_move)


# ---------------------------------------------------------------------------
# Command — toolbar/menu button
# ---------------------------------------------------------------------------
class DoorsPlusCommand:
    """Interactive door command: pick a point/face, then configure.

    Flow:
      1. Activated()  — start box tracker + snapper
      2. update()     — move preview box with mouse
      3. getPoint()   — create door at picked location, open config panel
    """

    # Default dimensions (same as the task panel defaults)
    WIDTH = 900
    HEIGHT = 2100
    FRAME_W = 70
    PANEL_T = 45
    FRAME_D = 100

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Door",
                "ToolTip": "Place a door, then configure it (DoorsPlus)"}

    def IsActive(self):
        return hasattr(FreeCADGui.getMainWindow().getActiveWindow(), "getSceneGraph")

    def Activated(self):
        import draftguitools.gui_trackers as DraftTrackers
        import WorkingPlane

        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()

        self.doc = FreeCAD.ActiveDocument
        self.sel = FreeCADGui.Selection.getSelection()
        self.baseFace = None
        self.width = self.WIDTH
        self.height = self.HEIGHT
        self.frameDepth = self.FRAME_D
        # A door almost always sits on the floor, so by default we snap its
        # base to the bottom of whatever wall is pointed at. The user then only
        # aims along the wall, not at its (hard-to-hit) base edge.
        self.snapBase = True
        self.baseOffset = 0.0       # raise above the wall base (sill/threshold)

        # Box tracker as preview
        self.wp = WorkingPlane.get_working_plane()
        self.tracker = DraftTrackers.boxTracker()
        self.tracker.length(self.width)
        self.tracker.width(self.frameDepth)
        self.tracker.height(self.height)
        self.tracker.on()

        FreeCAD.Console.PrintMessage(
            "DoorsPlus: Click to place the door, then configure it.\n")

        FreeCADGui.Snapper.getPoint(
            callback=self.getPoint,
            movecallback=self.update,
            extradlg=self.taskbox(),
        )

    def update(self, point, info):
        """Move the preview box as the mouse moves.

        The box is positioned from the SAME _doorPlacement used on click, so the
        preview shows exactly where the door will land — centred on the cursor
        and sitting on the floor — rather than off to one side."""
        if info and "Face" in info.get("Component", ""):
            o = self.doc.getObject(info["Object"])
            try:
                fi = int(info["Component"][4:]) - 1
            except (ValueError, IndexError):
                self.baseFace = None
            else:
                self.baseFace = [o, fi]

        pl = _doorPlacement(point, self.baseFace, self.width,
                            self.snapBase, self.baseOffset)
        _placeTracker(self.tracker, pl, self.width, self.height)

    def getPoint(self, point=None, obj=None):
        """Called when the user clicks: create door, then schedule config panel."""
        FreeCADGui.Snapper.off()
        self.tracker.off()

        if point is None:
            self.tracker.finalize()
            return

        import Draft

        doc = self.doc
        doc.openTransaction("Create Door")

        # Placement: oriented to the picked face, floor-snapped, centred on the
        # cursor (shared with reposition so create and move behave identically).
        pl = _doorPlacement(point, self.baseFace, self.width,
                            self.snapBase, self.baseOffset)

        # Build the door geometry at identity, then apply placement
        spec = dict(
            operation="Single swing",
            panelStyle="Solid",
            width=self.width,
            height=self.height,
            frameWidth=self.FRAME_W,
            panelThk=self.PANEL_T,
            frameDepth=self.frameDepth,
            swingSide="Left",
            swingDir="Inward",
        )

        sketch, wp_list = _makeDoorGeometry(spec)
        sketch.Placement = pl
        doc.recompute()

        import doorsplus_object
        door = doorsplus_object.makeWindow(sketch, self.width, self.height,
                                           wp_list, name="Door")
        if door is None:
            doc.abortTransaction()
            self.tracker.finalize()
            return

        # The frame part's thickness is "(frameDepth - panelThk) + Frame", so
        # the geometry only matches frameDepth when Frame == panelThk. makeWindow
        # doesn't set these, so do it here (mirrors the panel's _apply), else the
        # freshly placed door renders with the wrong frame depth until re-edited.
        door.Frame = self.PANEL_T
        door.Offset = 0

        if door and hasattr(door, "Base") and door.Base:
            try:
                door.Base.ViewObject.DisplayMode = "Wireframe"
                door.Base.ViewObject.hide()
            except Exception:
                pass

        # Try to auto-host if a wall was clicked
        if self.baseFace is not None:
            host = self.baseFace[0]
            if Draft.getType(host) in ("Wall", "Structure", "Roof"):
                door.Hosts = [host]

        doc.recompute()
        self.tracker.finalize()

        # Defer panel opening to the next event-loop tick.
        # showDialog cannot be called from inside a Snapper callback.
        QtCore.QTimer.singleShot(
            0, lambda: FreeCADGui.Control.showDialog(
                DoorsPlusTaskPanel(obj=door, placed=True)))

    def taskbox(self):
        """Minimal widget shown during interactive placement."""
        from PySide import QtGui

        w = QtGui.QWidget()
        w.setWindowTitle("Door placement")
        grid = QtGui.QGridLayout(w)

        label = QtGui.QLabel("Click on a face or in space\nto place the door.")
        label.setWordWrap(True)
        grid.addWidget(label, 0, 0, 1, 2)

        # Width
        grid.addWidget(QtGui.QLabel("Width"), 1, 0, 1, 1)
        width_input = FreeCADGui.UiLoader().createWidget("Gui::QuantitySpinBox")
        try:
            width_input.setProperty("value",
                FreeCAD.Units.Quantity("%.6f mm" % float(self.WIDTH)))
        except Exception:
            width_input = QtGui.QDoubleSpinBox()
            width_input.setValue(self.WIDTH)
            width_input.setSuffix(" mm")
        grid.addWidget(width_input, 1, 1, 1, 1)

        def _on_width(val):
            try:
                self.width = float(val.Value)
            except Exception:
                self.width = float(val)
            self.tracker.length(self.width)
        try:
            width_input.valueChanged.connect(_on_width)
        except Exception:
            pass

        # Sit-on-base toggle — the whole point of this dialog: you aim along
        # the wall and the door drops to its base automatically.
        baseChk = QtGui.QCheckBox("Sit on wall base (floor)")
        baseChk.setChecked(self.snapBase)
        baseChk.setToolTip(
            "Drop the door to the bottom of the wall you point at, so you only "
            "need to aim along the wall — not at its base edge.")
        baseChk.toggled.connect(
            lambda checked: setattr(self, "snapBase", bool(checked)))
        grid.addWidget(baseChk, 2, 0, 1, 2)

        # Base offset — raise the door above the wall base (sill/threshold).
        grid.addWidget(QtGui.QLabel("Base offset"), 3, 0, 1, 1)
        offset_input = FreeCADGui.UiLoader().createWidget("Gui::QuantitySpinBox")
        try:
            offset_input.setProperty("value",
                FreeCAD.Units.Quantity("%.6f mm" % float(self.baseOffset)))
        except Exception:
            offset_input = QtGui.QDoubleSpinBox()
            offset_input.setSuffix(" mm")
            offset_input.setValue(self.baseOffset)
        offset_input.setToolTip(
            "Raise the door above the wall base (e.g. a threshold). "
            "0 keeps it on the floor.")
        grid.addWidget(offset_input, 3, 1, 1, 1)

        def _on_offset(val):
            try:
                self.baseOffset = float(val.Value)
            except Exception:
                self.baseOffset = float(val)
        try:
            offset_input.valueChanged.connect(_on_offset)
        except Exception:
            pass

        return w


# Register the command (FreeCAD 1.1 has no removeCommand; addCommand is a no-op
# if it's already registered, so guard to stay reload-safe).
if "ArchPlus_Doors" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_Doors", DoorsPlusCommand())
