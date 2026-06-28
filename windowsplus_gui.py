# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WindowsPlus - a window-specific creation UI with live 3D preview.
#
# The Task panel creates a real _Window-based window object as soon as it opens
# and updates its properties live (debounced) as you change the widgets, so the
# window renders in the 3D view while you interact. OK keeps it; Cancel aborts
# the transaction, which removes the preview.
#
# Window types supported: Fixed, Single casement, Single sliding, Double casement.
# Glass is a single undivided pane per sash (no muntins/grille).
#
# Windows use a full 4-sided frame (left, right, top, AND bottom sill jamb)
# because they sit in a wall opening with a sill, unlike doors which sit on the
# floor and use a 3-sided frame.

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

ICON = os.path.join(_DIR, "Resources", "icons", "WindowsPlus.svg")

# ---------------------------------------------------------------------------
# Window type → operation mapping
# ---------------------------------------------------------------------------
WINDOW_OPERATIONS = [
    "Fixed",
    "Single casement",
    "Single sliding",
    "Double casement",
]

WINDOW_SHAPES = ["Rectangular", "Round"]  # overall opening outline

SWING_SIDES = ["Left", "Right"]
SWING_DIRS = ["Inward", "Outward"]
PANEL_POSITIONS = ["Front", "Back"]  # sash position in frame depth (interior/exterior flush)


def _shapeIsRound(spec):
    return spec.get("shape") == "Round"


# ---------------------------------------------------------------------------
# Spec persistence
# ---------------------------------------------------------------------------
# The native Window object only stores Width/Height/Frame. The remaining panel
# settings (operation, frame width/depth, swing, sash position, shape) are
# persisted on the object as a hidden JSON string so they can be restored when
# the object is edited.
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


def _operationNeedsSash(op):
    """Return True if the operation creates one or more sashes."""
    return op != "Fixed"


def _operationSashCount(op):
    """Number of sash panels for the given operation."""
    if op == "Single casement":
        return 1
    if op in ("Single sliding", "Double casement"):
        return 2
    return 0


def _operationIsSliding(op):
    return "sliding" in op.lower()


def _operationIsCasement(op):
    return "casement" in op


def _openingModeFor(op, leafIndex):
    """Return the opening Mode integer for a sash.

    leafIndex: 0 = left sash, 1 = right sash (for double casement).

    Casement windows use Arc modes (hinged); sliding windows use Sliding mode.
    The direction (Inward/Outward) is handled by toggling between Mode 1/2
    (Arc 90 / Arc 90 inv) or Mode 9/10 (Sliding / Sliding inv).
    """
    if _operationIsSliding(op):
        return 9        # Both sashes use the same base mode; the inward/outward
                        # toggle and the geometry of each sash's hinge edge cause
                        # them to slide in opposite (outward) world directions.
    # Casement
    if leafIndex == 0:
        return 1        # Arc 90
    return 2            # Arc 90 inv


def _openingModeInv(op, leafIndex):
    """The inverted version of the opening mode (for inward/outward toggle)."""
    pairs = {1: 2, 2: 1, 9: 10, 10: 9}
    return pairs.get(_openingModeFor(op, leafIndex), 1)


# ---------------------------------------------------------------------------
# Window geometry generation
# ---------------------------------------------------------------------------
def _makeWindowGeometry(spec):
    """Build a sketch and WindowParts array for the given window specification.

    spec keys:
        operation  : str  ("Fixed", "Single casement", "Single sliding",
                           "Double casement")
        width      : float (mm, overall)
        height     : float (mm, overall)
        frameWidth : float (mm, jamb width — all 4 sides)
        sashThk    : float (mm, sash profile depth along wall normal)
        frameDepth : float (mm, frame extrusion depth into wall)
        swingSide  : str  ("Left" / "Right") — hinge side for single casement
        swingDir   : str  ("Inward" / "Outward")

    The outer frame is 4-sided (inset on all sides, including the bottom sill
    jamb), unlike doors which use a 3-sided frame with the bottom flush.

    Returns (sketch, windowParts).
    """

    import Part
    import Sketcher

    w = spec["width"]
    h = spec["height"]
    jw = spec["frameWidth"]           # jamb width (all 4 sides)
    pt = spec["sashThk"]              # sash profile depth (also obj.Frame)
    fd = spec["frameDepth"]           # frame depth into wall
    op = spec["operation"]
    ss = spec.get("swingSide", "Left")
    sd = spec.get("swingDir", "Inward")
    pp = spec.get("panelPos", "Front")       # sash position within frame depth

    # Opening mode helper: Mode1 on left hinge opens opposite direction
    # of Mode1 on right hinge.  XOR hinge-side with inward to keep
    # "Inward"/"Outward" semantically consistent regardless of hinge.
    def _swingMode(leaf=0):
        m = _openingModeFor(op, leaf)
        if _operationIsSliding(op):
            return m          # Sliding: direction is purely geometric (along
                            # the hinge/track edge); the inward/outward XOR
                            # below is only meaningful for hinged casements.
        if (ss == "Right") != (sd == "Inward"):
            m = _openingModeInv(op, leaf)
        return m

    # Sash frame member width (thinner than the outer jamb).
    sfw = jw * 0.6
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

    # --- Round (circular oculus) window -------------------------------------
    # Two concentric circles: the ring between them is the frame, the inner
    # disc is fixed glass. Round windows are fixed (no sash) — the engine's
    # swing modes hinge a sash about a straight edge, which a circle lacks.
    # The diameter follows the overall width; the circle is centred at (R, R)
    # so the bounding box is 0..D on both axes, matching the rectangular
    # build's corner-at-origin convention (placement/sill logic is unchanged).
    if _shapeIsRound(spec):
        D = w
        R = D / 2.0
        rib = max(R - jw, R * 0.05)              # inner radius, kept positive
        nrm = FreeCAD.Vector(0, 0, 1)
        center = FreeCAD.Vector(R, R, 0)
        i_out = s.addGeometry(Part.Circle(center, nrm, R))    # Wire0 (outer)
        i_in = s.addGeometry(Part.Circle(center, nrm, rib))   # Wire1 (inner)
        # Concentric + radii + centre position fully constrain the sketch.
        # NB: do NOT name a constraint "Width"/"Height" — the engine's
        # onChanged() would setDatum() the diameter onto it (see object).
        s.addConstraint(Sketcher.Constraint("Coincident", i_out, 3, i_in, 3))
        s.addConstraint(Sketcher.Constraint("Radius", i_out, R))
        s.addConstraint(Sketcher.Constraint("Radius", i_in, rib))
        s.addConstraint(Sketcher.Constraint("DistanceX", -1, 1, i_out, 3, R))
        s.addConstraint(Sketcher.Constraint("DistanceY", -1, 1, i_out, 3, R))

        # Frame ring (Wire0 outer minus Wire1 inner), full frame depth.
        wp.append(["OuterFrame", "Frame", "Wire0,Wire1", "%.4f" % fd, "0.00+V"])
        # Glass disc fills the inner opening, set just behind the front face.
        wp.append(["Glass", "Glass panel", "Wire1",
                   "%.4f" % (pt / gla), "%.4f+V" % (pt / 2.0)])

        flat = []
        for part in wp:
            flat.extend(part)
        return s, flat

    # --- Build the outer frame (4-sided: left, right, top, AND bottom) ---
    outer = [
        FreeCAD.Vector(0, 0, 0),
        FreeCAD.Vector(w, 0, 0),
        FreeCAD.Vector(w, h, 0),
        FreeCAD.Vector(0, h, 0),
    ]
    # Inner rectangle: frame on ALL four sides (jw inset everywhere).
    # This is the key difference from doors, which are flush at the bottom.
    inner = [
        FreeCAD.Vector(jw, jw, 0),
        FreeCAD.Vector(w - jw, jw, 0),
        FreeCAD.Vector(w - jw, h - jw, 0),
        FreeCAD.Vector(jw, h - jw, 0),
    ]

    _addFrame(*outer, *inner)
    # Overall Width & Height constraints
    s.addConstraint(Sketcher.Constraint("DistanceY", 1, h))
    s.addConstraint(Sketcher.Constraint("DistanceX", 0, w))
    s.renameConstraint(s.ConstraintCount - 2, "Height")
    s.renameConstraint(s.ConstraintCount - 1, "Width")
    # Frame width constraints (top, left, right — same as doors)
    s.addConstraint(Sketcher.Constraint("DistanceY", 6, 2, 2, 2, jw))   # top
    s.addConstraint(Sketcher.Constraint("DistanceX", 2, 2, 6, 2, jw))   # left
    s.addConstraint(Sketcher.Constraint("DistanceX", 4, 2, 0, 2, jw))   # right
    # Bottom jamb (window: jw inset, not 0 like doors which are floor-flush)
    s.addConstraint(Sketcher.Constraint("DistanceY", 0, 2, 4, 2, jw))
    # Pin outer to origin
    s.addConstraint(Sketcher.Constraint("Coincident", 0, 1, -1, 1))

    # Wire0 = outer frame wire (index 0), Wire1 = inner frame wire (index 1)
    # Outer frame depth is the literal frame depth (fd).  We do NOT use the
    # "+V" suffix here — that would add obj.Frame to the thickness, creating
    # a fragile (fd - pt) + pt = fd identity that breaks if obj.Frame and the
    # WindowParts are ever briefly out of sync during a recompute.
    offset_str = "0.00+V"
    wp.append(["OuterFrame", "Frame", "Wire0,Wire1", "%.4f" % fd, offset_str])

    # Sash depth range within the frame: the frame is fd deep, the sash is pt
    # thick, so the sash can occupy z = 0 .. (fd - pt).  fthk is that range.
    fthk = fd - pt
    if fthk < 0:
        fthk = 0

    # Where the sash sits within the frame depth. The frame spans 0..fd along
    # the normal; the sash is `pt` thick, so it sits flush to either the front
    # (interior) face at 0 or the back (exterior) face at fd - pt. Front is the
    # default; a real sash sits flush to a face for opening clearance, not
    # floating in the middle.
    if pp == "Back":
        panelZ = fthk
    else:                                    # Front (default)
        panelZ = 0.0
    leaf_off = "%.4f+V" % panelZ             # depth offset for sash frames
    glass_off = "%.4f+V" % (panelZ + pt / 2.0)   # glass sheet, mid-sash

    sash_count = _operationSashCount(op)

    # Edge index helpers.  After the outer frame (2 rectangles via _addFrame),
    # the sketch has 8 edges (0–7).  Wire0 = edges 0-3, Wire1 = edges 4-7.
    # Each additional rectangle adds 4 edges; each _addFrame adds 8.
    # Global edge indices (1-based, as used in WindowParts strings):
    _BASE_EDGES = 8          # edges consumed by the outer frame
    _W1_LEFT   = 8           # Wire1 left   = global edge  7 → Edge8
    _W1_RIGHT  = 6           # Wire1 right  = global edge  5 → Edge6

    if op == "Fixed":
        # Fixed window — no sash, just glass filling the inner opening.
        # Wire1 (the inner opening) is the glass.
        wp.append(["Glass", "Glass panel", "Wire1",
                   "%.4f" % (pt / gla), glass_off])

    elif op == "Single sliding":
        # Two halves on separate z-tracks: left fixed (front track), right
        # sliding (back track).  The right sash slides leftward (Mode9,
        # hinged on its right edge) and passes BEHIND the fixed half —
        # exactly how a real single-sliding window works.
        # Wire2 (edges 8-11):  left (fixed) half outer
        # Wire3 (edges 12-15): left (fixed) half inner (glass opening)
        # Wire4 (edges 16-19): right (sliding) half outer
        # Wire5 (edges 20-23): right (sliding) half inner (glass opening)
        half = w / 2.0
        _addFrame(*[FreeCAD.Vector(jw + tol, jw + tol, 0),
                    FreeCAD.Vector(half - tol, jw + tol, 0),
                    FreeCAD.Vector(half - tol, h - jw - tol, 0),
                    FreeCAD.Vector(jw + tol, h - jw - tol, 0)],
                  *[FreeCAD.Vector(jw + sfw, jw + sfw, 0),
                    FreeCAD.Vector(half - sfw, jw + sfw, 0),
                    FreeCAD.Vector(half - sfw, h - jw - sfw, 0),
                    FreeCAD.Vector(jw + sfw, h - jw - sfw, 0)])   # Wire2, Wire3
        _addFrame(*[FreeCAD.Vector(half + tol, jw + tol, 0),
                    FreeCAD.Vector(w - jw - tol, jw + tol, 0),
                    FreeCAD.Vector(w - jw - tol, h - jw - tol, 0),
                    FreeCAD.Vector(half + tol, h - jw - tol, 0)],
                  *[FreeCAD.Vector(half + sfw, jw + sfw, 0),
                    FreeCAD.Vector(w - jw - sfw, jw + sfw, 0),
                    FreeCAD.Vector(w - jw - sfw, h - jw - sfw, 0),
                    FreeCAD.Vector(half + sfw, h - jw - sfw, 0)])  # Wire4, Wire5

        # Two z-tracks within the frame depth (fd).  The sash is pt thick,
        # so the play range is fthk = fd - pt.  Fixed half sits at the front
        # (z=0); sliding half sits at the back (z=fthk) so it slides behind.
        fixed_off   = "0.0000"
        fixed_glass = "%.4f" % (pt / 2.0)
        slide_off   = "%.4f" % fthk
        slide_glass = "%.4f" % (fthk + pt / 2.0)

        # Left half: fixed (no Edge/Mode → no opening animation)
        wp.append(["FixedSash", "Frame", "Wire2,Wire3",
                   "%.4f" % pt, fixed_off])
        wp.append(["FixedGlass", "Glass panel", "Wire3",
                   "%.4f" % (pt / gla), fixed_glass])
        # Right half: sliding, hinged on right edge (Edge18 = global edge 17).
        # Mode9 slides the sash leftward, behind the fixed half.
        mode = _swingMode()
        wp.append(["SlideSash", "Frame", "Wire4,Wire5,Edge18,Mode%d" % mode,
                   "%.4f" % pt, slide_off])
        wp.append(["SlideGlass", "Glass panel", "Wire5,Edge18,Mode%d" % mode,
                   "%.4f" % (pt / gla), slide_glass])

    elif sash_count == 1:
        # Single casement — one sash hinged on left or right edge of the
        # frame opening (Wire1's left = Edge8, right = Edge6).
        # Wire2 (edges 8-11): sash outer
        # Wire3 (edges 12-15): sash inner (glass opening)
        sash_outer = [
            FreeCAD.Vector(jw + tol, jw + tol, 0),
            FreeCAD.Vector(w - jw - tol, jw + tol, 0),
            FreeCAD.Vector(w - jw - tol, h - jw - tol, 0),
            FreeCAD.Vector(jw + tol, h - jw - tol, 0),
        ]
        sash_inner = [
            FreeCAD.Vector(jw + sfw, jw + sfw, 0),
            FreeCAD.Vector(w - jw - sfw, jw + sfw, 0),
            FreeCAD.Vector(w - jw - sfw, h - jw - sfw, 0),
            FreeCAD.Vector(jw + sfw, h - jw - sfw, 0),
        ]
        _addFrame(*sash_outer, *sash_inner)

        hinge = _W1_LEFT if ss == "Left" else _W1_RIGHT
        mode = _swingMode()
        wp.append(["Sash", "Frame", "Wire2,Wire3,Edge%d,Mode%d" % (hinge, mode),
                   "%.4f" % pt, leaf_off])
        wp.append(["Glass", "Glass panel", "Wire3,Edge%d,Mode%d" % (hinge, mode),
                   "%.4f" % (pt / gla), glass_off])

    elif sash_count == 2:
        # Double casement — two sashes, each hinged on its outer edge.
        # Wire2 (edges 8-11):  left sash outer
        # Wire3 (edges 12-15): left sash inner (glass opening)
        # Wire4 (edges 16-19): right sash outer
        # Wire5 (edges 20-23): right sash inner (glass opening)
        half = w / 2.0
        _addFrame(*[FreeCAD.Vector(jw + tol, jw + tol, 0),
                    FreeCAD.Vector(half - tol, jw + tol, 0),
                    FreeCAD.Vector(half - tol, h - jw - tol, 0),
                    FreeCAD.Vector(jw + tol, h - jw - tol, 0)],
                  *[FreeCAD.Vector(jw + sfw, jw + sfw, 0),
                    FreeCAD.Vector(half - sfw, jw + sfw, 0),
                    FreeCAD.Vector(half - sfw, h - jw - sfw, 0),
                    FreeCAD.Vector(jw + sfw, h - jw - sfw, 0)])   # Wire2, Wire3
        _addFrame(*[FreeCAD.Vector(half + tol, jw + tol, 0),
                    FreeCAD.Vector(w - jw - tol, jw + tol, 0),
                    FreeCAD.Vector(w - jw - tol, h - jw - tol, 0),
                    FreeCAD.Vector(half + tol, h - jw - tol, 0)],
                  *[FreeCAD.Vector(half + sfw, jw + sfw, 0),
                    FreeCAD.Vector(w - jw - sfw, jw + sfw, 0),
                    FreeCAD.Vector(w - jw - sfw, h - jw - sfw, 0),
                    FreeCAD.Vector(half + sfw, h - jw - sfw, 0)])  # Wire4, Wire5

        # Left sash hinge: Edge12 (left edge of Wire2, global edge 11)
        # Right sash hinge: Edge18 (right edge of Wire4, global edge 17)
        lmode = _swingMode(0)
        rmode = _swingMode(1)
        wp.append(["LeftSash", "Frame", "Wire2,Wire3,Edge12,Mode%d" % lmode,
                   "%.4f" % pt, leaf_off])
        wp.append(["LeftGlass", "Glass panel", "Wire3,Edge12,Mode%d" % lmode,
                   "%.4f" % (pt / gla), glass_off])
        wp.append(["RightSash", "Frame", "Wire4,Wire5,Edge18,Mode%d" % rmode,
                   "%.4f" % pt, leaf_off])
        wp.append(["RightGlass", "Glass panel", "Wire5,Edge18,Mode%d" % rmode,
                   "%.4f" % (pt / gla), glass_off])

    # Flatten WindowParts list for the property (5-element groups)
    flat = []
    for part in wp:
        flat.extend(part)

    return s, flat


# ---------------------------------------------------------------------------
# Apply window settings to an existing _Window object
# ---------------------------------------------------------------------------
def applyWindowSettings(obj, spec):
    """Push window spec onto an _Window object."""
    sketch, wp = _makeWindowGeometry(spec)
    obj.Base = sketch
    obj.WindowParts = wp
    obj.Width = spec["width"]
    obj.Height = spec["height"]
    obj.Frame = spec["sashThk"]
    obj.Offset = 0
    obj.Preset = 0  # custom (not a built-in preset)
    obj.Label = "Window"


def makeWindow(width=1200.0, height=1200.0, operation="Fixed",
               frameWidth=50.0, sashThk=45.0,
               frameDepth=100.0, swingSide="Left", swingDir="Inward"):
    """Create a _Window-based window object with the given parameters."""
    import windowsplus_object

    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument()

    spec = dict(
        operation=operation,
        width=width,
        height=height,
        frameWidth=frameWidth,
        sashThk=sashThk,
        frameDepth=frameDepth,
        swingSide=swingSide,
        swingDir=swingDir,
    )

    sketch, wp = _makeWindowGeometry(spec)
    FreeCAD.ActiveDocument.recompute()

    obj = windowsplus_object.makeWindow(sketch, width, height, wp, name="Window")
    if obj is None:
        obj = FreeCAD.ActiveDocument.addObject(
            "Part::FeaturePython", "Window", windowsplus_object._Window())
        windowsplus_object._Window(obj)
        obj.Base = sketch
        obj.WindowParts = wp

    obj.Width = width
    obj.Height = height
    obj.Frame = sashThk
    obj.Offset = 0
    obj.Label = "Window"

    FreeCAD.ActiveDocument.recompute()
    return obj


def _recomputeWithHosts(obj):
    """Recompute the window, then re-cut its host walls in the same edit.

    A hosted window is computed BEFORE its host wall in the dependency graph,
    so one recompute leaves the wall still cutting the window's previous shape
    and position — the change only appears after some later recompute. Touching
    the hosts and recomputing again makes the wall opening follow the window
    now."""
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
class WindowsPlusTaskPanel:
    """Docked panel. FreeCAD supplies OK/Cancel and routes them to
    self.accept() / self.reject()."""

    def __init__(self, obj=None, placed=False):
        self.obj = obj                 # None = create; object = edit or placed
        self.editing = obj is not None and not placed
        self.placed = placed           # True: window was just placed, configure it
        self._building = True          # suppress live updates during widget setup
        self._sketch = None            # the window's base sketch

        title = "Window"
        if self.editing:
            title = "Edit Window"
        elif self.placed:
            title = "Configure Window"
        self.form = QtGui.QWidget()
        self.form.setWindowTitle(title)
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))

        outer = QtGui.QVBoxLayout(self.form)

        # ---- Operation & style --------------------------------------------
        typeBox = QtGui.QGroupBox("Window Type")
        typeForm = QtGui.QFormLayout(typeBox)
        self.shape = QtGui.QComboBox()
        self.shape.addItems(WINDOW_SHAPES)
        self.shape.setToolTip(
            "Overall outline. Round is a circular oculus (fixed glass); its "
            "diameter follows the width.")
        self.operation = QtGui.QComboBox()
        self.operation.addItems(WINDOW_OPERATIONS)
        typeForm.addRow("Shape", self.shape)
        typeForm.addRow("Operation", self.operation)
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
        self.dimRef = self._refImage("dimensions_ref_window", self._dimRefSize)
        dimV.addWidget(self.dimRef)
        dimForm = QtGui.QFormLayout()
        self.width = self._len(1200)
        self.height = self._len(1200)
        self.frameWidth = self._len(50)
        self.frameWidth.setToolTip("Jamb width — the frame member width on all four sides")
        self.sashThk = self._len(45)
        self.sashThk.setToolTip(
            "Sash depth — how far the sash reaches into the wall (along the "
            "opening normal). Also drives the glass thickness. Bounded by the "
            "frame depth so the sash can't protrude. This is NOT the sash's "
            "head-on rail width (that follows the jamb width).")
        self.frameDepth = self._len(100)
        self.frameDepth.setToolTip("Depth of the frame into the wall (perpendicular to opening)")
        self.panelPos = QtGui.QComboBox()
        self.panelPos.addItems(PANEL_POSITIONS)
        self.panelPos.setToolTip(
            "Which face the sash sits flush to within the frame depth: Front "
            "(interior) or Back (exterior). Only has an effect when the sash "
            "depth is less than the frame depth.")
        dimForm.addRow("W · Overall width", self.width)
        dimForm.addRow("H · Overall height", self.height)
        dimForm.addRow("Fw · Frame width (jamb)", self.frameWidth)
        dimForm.addRow("Sd · Sash depth", self.sashThk)
        dimForm.addRow("Fd · Frame depth", self.frameDepth)
        dimForm.addRow("Sash position", self.panelPos)
        dimV.addLayout(dimForm)
        self._dimForm = dimForm
        outer.addWidget(dimBox)

        # ---- Position -----------------------------------------------------
        # A window is placed and moved with the mouse (see WindowsPlusCommand /
        # repositionWindow), sitting at a sill height above the wall base by
        # default. The sill field adjusts that height; the button re-enters
        # mouse placement.
        posBox = QtGui.QGroupBox("Position")
        posV = QtGui.QVBoxLayout(posBox)
        posForm = QtGui.QFormLayout()
        self.sill = self._len(900)
        self.sill.setToolTip(
            "Sill height — height of the window's base above the wall base "
            "(the floor). 900 mm is a typical sill height; increase for a "
            "clerestory or transom window, decrease toward 0 for a floor-level "
            "window or door-like opening.")
        posForm.addRow("Sill height", self.sill)
        posV.addLayout(posForm)
        self.repositionBtn = QtGui.QPushButton("Reposition with mouse…")
        self.repositionBtn.setToolTip(
            "Pick a new location for this window in the 3D view. It re-orients "
            "to the wall face you point at and re-sets to the sill height "
            "automatically.")
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
        self.tag.setPlaceholderText("e.g. W01")
        self.isExternal = QtGui.QCheckBox()
        metaForm.addRow("Tag / Mark", self.tag)
        metaForm.addRow("External window", self.isExternal)
        outer.addWidget(metaBox)

        # Debounce timer
        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        # Connect widgets to live-update scheduler
        for w in (self.width, self.height, self.frameWidth, self.sashThk,
                  self.frameDepth):
            w.valueChanged.connect(self._schedule)
        # Couple sash depth and frame depth so the sash can never be deeper
        # than the frame (which would make it protrude). Re-sync the spinbox
        # limits whenever either changes, and set the initial limits now.
        self.sashThk.valueChanged.connect(self._syncDepthLimits)
        self.frameDepth.valueChanged.connect(self._syncDepthLimits)
        self._syncDepthLimits()
        # Sill only moves the window vertically; handle it directly (no rebuild).
        self.sill.valueChanged.connect(self._onSillChanged)
        self.opening.valueChanged.connect(self._onOpeningChanged)
        for c in (self.operation, self.panelPos, self.swingSide,
                  self.swingDir):
            c.currentIndexChanged.connect(self._schedule)
        self.symbolPlan.toggled.connect(self._onSymbolToggled)
        self.symbolElev.toggled.connect(self._onSymbolToggled)
        # Set checked AFTER connecting so the signal reaches the object.
        self.symbolPlan.setChecked(True)
        self.symbolElev.setChecked(False)
        self.operation.currentIndexChanged.connect(self._syncOperationRows)
        self.shape.currentIndexChanged.connect(self._schedule)
        self.shape.currentIndexChanged.connect(self._syncShapeRows)
        self._syncShapeRows()

        if self.editing:
            self._loadFromObject()
            self._building = False
            FreeCAD.ActiveDocument.openTransaction("Edit Window")
        elif self.placed:
            # Window was just created by the command; transaction already open.
            self._sketch = self.obj.Base
            # Reflect the actually-placed size (width can be changed in the
            # placement step) so the panel matches what was built and a later
            # edit doesn't silently resize it. Done while _building is True so
            # it doesn't trigger a rebuild.
            self._setmm(self.width, self.obj.Width.Value)
            self._setmm(self.height, self.obj.Height.Value)
            self._setmm(self.sashThk, self.obj.Frame.Value)
            self._loadSill()
            self._building = False
            # Sync initial symbol state to the placed window.
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

    @staticmethod
    def _setmax(w, mm):
        try:
            w.setMaximum(float(mm))
        except Exception:
            try:
                w.setProperty("maximum", float(mm))
            except Exception:
                pass

    @staticmethod
    def _setmin(w, mm):
        try:
            w.setMinimum(float(mm))
        except Exception:
            try:
                w.setProperty("minimum", float(mm))
            except Exception:
                pass

    def _syncDepthLimits(self, *args):
        """Keep the sash inside the frame. A sash can't be deeper than the frame
        it sits in, so cap the sash-depth field at the frame depth and floor
        the frame-depth field at the sash depth. Enforcing it as spinbox
        limits blocks an invalid (protruding) window from being created at all,
        rather than clamping the offset and letting the sash stick out."""
        if getattr(self, "_syncingLimits", False):
            return
        self._syncingLimits = True
        try:
            fd = self._mm(self.frameDepth)
            self._setmax(self.sashThk, fd)        # sash depth <= frame depth
            st = self._mm(self.sashThk)           # re-read: may have just clamped
            self._setmin(self.frameDepth, st)     # frame depth >= sash depth
        finally:
            self._syncingLimits = False

    def _refImage(self, name, size):
        lbl = QtGui.QLabel()
        lbl.setAlignment(QtCore.Qt.AlignCenter)
        path = os.path.join(_DIR, "Resources", "icons", name + ".svg")
        if os.path.exists(path):
            lbl.setPixmap(QtGui.QIcon(path).pixmap(size))
        return lbl

    def _collect(self):
        shape = self.shape.currentText()
        width = self._mm(self.width)
        # Round windows are circular: the diameter follows the width, so the
        # (hidden) height tracks it and the operation is forced to Fixed.
        height = width if shape == "Round" else self._mm(self.height)
        return dict(
            shape=shape,
            operation=self.operation.currentText(),
            width=width,
            height=height,
            frameWidth=self._mm(self.frameWidth),
            sashThk=self._mm(self.sashThk),
            frameDepth=self._mm(self.frameDepth),
            swingSide=self.swingSide.currentText(),
            swingDir=self.swingDir.currentText(),
            panelPos=self.panelPos.currentText(),
        )

    @staticmethod
    def _setRowVisible(form, widget, visible):
        """Hide/show a QFormLayout row (the field widget and its label)."""
        widget.setVisible(visible)
        lbl = form.labelForField(widget)
        if lbl is not None:
            lbl.setVisible(visible)

    def _syncShapeRows(self, *args):
        """Round windows are fixed circular glass: lock Operation to Fixed,
        drop the Height row (the diameter follows the width), and relabel
        Width as the diameter."""
        round_ = self.shape.currentText() == "Round"
        if round_:
            self.operation.setCurrentIndex(0)        # Fixed
        self.operation.setEnabled(not round_)
        self._setRowVisible(self._dimForm, self.height, not round_)
        wlbl = self._dimForm.labelForField(self.width)
        if wlbl is not None:
            wlbl.setText("D · Diameter" if round_ else "W · Overall width")
        self._syncOperationRows()

    def _syncOperationRows(self):
        """Show swing controls only for casement (hinged) operations, and the
        sash-position selector only when the operation actually has a sash."""
        op = self.operation.currentText()
        self._swingBox.setVisible(_operationIsCasement(op))
        self._setRowVisible(self._dimForm, self.panelPos, _operationNeedsSash(op))

    def _onOpeningChanged(self, val):
        self._openLbl.setText("%d%%" % val)
        if self.obj is not None:
            try:
                # If a geometry update is pending (e.g. the user changed the
                # operation dropdown and immediately dragged this slider),
                # flush it first.  Otherwise the recompute below would use
                # the OLD WindowParts (still casement Mode1) and the sash
                # would swing/rotate instead of slide.
                if self._timer.isActive():
                    self._timer.stop()
                    self._apply()
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
        """Set the sill widget from the window's current height above its host."""
        if self._sketch is None:
            return
        baseZ = self._hostBaseZ()
        if baseZ is None:
            baseZ = 0.0
        self._setmm(self.sill, max(0.0, self._sketch.Placement.Base.z - baseZ))

    def _hostBaseZ(self):
        """Lowest base level of the window's host wall(s), or None if unhosted."""
        zs = []
        for h in (getattr(self.obj, "Hosts", None) or []):
            try:
                zs.append(h.Shape.BoundBox.ZMin)
            except Exception:
                pass
        return min(zs) if zs else None

    def _onSillChanged(self, *args):
        """Raise/lower the window so its base sits `sill` above the wall base.

        Only the vertical (Z) coordinate of the base sketch is moved; windows
        live in vertical walls, so this keeps the window in the wall plane.
        Measured from the host wall base, or from the global origin if
        unhosted."""
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
        """Close the panel (keeping edits) and re-place the window with the mouse."""
        if self.obj is None:
            return
        window = self.obj
        # Commit + close the panel: a Snapper pick can't run while this task
        # dialog owns the task view. repositionWindow re-shows the panel when
        # the move finishes (or is cancelled), so it feels like it stayed open.
        self.accept()
        QtCore.QTimer.singleShot(0, lambda: repositionWindow(window, reopen=True))

    # ---- live preview -----------------------------------------------------
    def _startPreview(self):
        import windowsplus_object

        if FreeCAD.ActiveDocument is None:
            FreeCAD.newDocument()
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("Create Window")

        spec = self._collect()
        sketch, wp = _makeWindowGeometry(spec)
        FreeCAD.ActiveDocument.recompute()
        self._sketch = sketch

        obj = windowsplus_object.makeWindow(sketch, spec["width"], spec["height"], wp,
                                             name="Window")
        if obj is None:
            obj = FreeCAD.ActiveDocument.addObject(
                "Part::FeaturePython", "Window", windowsplus_object._Window())
            windowsplus_object._Window(obj)
            obj.Base = sketch
            obj.WindowParts = wp

        obj.Width = spec["width"]
        obj.Height = spec["height"]
        obj.Frame = spec["sashThk"]
        obj.Offset = 0
        obj.Preset = 0          # custom (not a built-in preset)
        obj.Label = "Window"
        self.obj = obj

        # Sync opening + symbol state from the panel widgets so the first
        # recompute produces the correct geometry.  Without this, the object
        # inherits FreeCAD defaults (Opening=0 is fine, but SymbolPlan /
        # SymbolElevation may differ from the checkboxes, and Preset=0 must
        # be explicit so no preset regeneration overrides our WindowParts).
        obj.Opening = self.opening.value()
        if hasattr(obj, "SymbolPlan"):
            obj.SymbolPlan = self.symbolPlan.isChecked()
        if hasattr(obj, "SymbolElevation"):
            obj.SymbolElevation = self.symbolElev.isChecked()

        # Force a recompute so the window's Shape is built from the correct
        # WindowParts before the user interacts.  Without this, the first
        # interaction (e.g. dragging the Opening slider) can trigger a
        # recompute with stale/default state, producing wrong geometry.
        FreeCAD.ActiveDocument.recompute()

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

            sketch, wp = _makeWindowGeometry(spec)
            self._sketch = sketch

            if old_pl is not None:
                sketch.Placement = old_pl

            # Solve the new sketch before swapping it in, so the window's
            # execute() sees a valid Shape (with Wires) rather than an empty
            # sketch.  Without this, the wall host can get a null subvolume
            # and report "Wall: null shape" — especially when switching to
            # Fixed, where the sketch drops from 4 wires to 2.
            FreeCAD.ActiveDocument.recompute()

            # Swap the base sketch in one step (no Base=None first — that
            # creates an intermediate null-shape state that can propagate to
            # the host wall during an auto-recompute).
            self.obj.Base = sketch
            self.obj.WindowParts = wp
            self.obj.Width = spec["width"]
            self.obj.Height = spec["height"]
            self.obj.Frame = spec["sashThk"]

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
                "WindowsPlus _apply error: %s\n%s\n" % (exc, traceback.format_exc()))

    # ---- load from existing object (edit mode) -----------------------------
    def _loadFromObject(self):
        o = self.obj
        self._sketch = o.Base            # needed for placement reuse on rebuild
        spec = readSpec(o)
        if spec:
            # frameDepth is set before sashThk so the sash-depth cap
            # (_syncDepthLimits) is already raised and doesn't clamp the value.
            self.shape.setCurrentText(spec.get("shape", "Rectangular"))
            self.operation.setCurrentText(spec.get("operation", "Fixed"))
            self._setmm(self.width, spec.get("width", o.Width.Value))
            self._setmm(self.height, spec.get("height", o.Height.Value))
            self._setmm(self.frameWidth, spec.get("frameWidth", 50))
            self._setmm(self.frameDepth, spec.get("frameDepth", 100))
            self._setmm(self.sashThk, spec.get("sashThk", o.Frame.Value))
            self.swingSide.setCurrentText(spec.get("swingSide", "Left"))
            self.swingDir.setCurrentText(spec.get("swingDir", "Inward"))
            self.panelPos.setCurrentText(spec.get("panelPos", "Front"))
        else:
            # Legacy object with no stored spec: restore what the native
            # properties hold and infer the shape from the base sketch. Frame
            # width/depth can't be recovered, so fall back to the defaults.
            isRound = False
            try:
                isRound = any(g.TypeId == "Part::GeomCircle"
                              for g in o.Base.Geometry)
            except Exception:
                pass
            self.shape.setCurrentText("Round" if isRound else "Rectangular")
            self._setmm(self.width, o.Width.Value)
            self._setmm(self.height, o.Height.Value)
            self._setmm(self.frameWidth, 50)
            self._setmm(self.frameDepth, 100)
            self._setmm(self.sashThk, o.Frame.Value)
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
def _windowPlacement(point, baseFace, width, snapBase=True, baseOffset=0.0):
    """Build the window placement for a picked point.

    - Orientation: from the picked wall face (or the working plane if none).
    - Sill snap: place the window base at (host base + sill height) so you only
      aim along the wall. The sill height defaults to 900 mm for windows.
    - Centring: the window sketch origin is its bottom-left corner, so shift
      half the width back along the wall — the window then lands centred on the
      cursor, matching the preview box."""
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
    """Position a box tracker to preview a window at placement `pl`.

    Orients the box so x=along-wall, y=depth, z=up, and centres it on the
    window footprint (whose origin is the bottom-left corner) — so the preview
    matches exactly where _windowPlacement will put the window."""
    u = pl.Rotation.multVec(FreeCAD.Vector(1, 0, 0))
    up = pl.Rotation.multVec(FreeCAD.Vector(0, 1, 0))
    n = pl.Rotation.multVec(FreeCAD.Vector(0, 0, 1))
    tracker.setRotation(FreeCAD.Rotation(u, n, up, "XYZ"))
    tracker.pos(pl.multVec(FreeCAD.Vector(width / 2.0, height / 2.0, 0)))


def repositionWindow(window, reopen=False):
    """Move an existing window to a new mouse-picked location.

    Re-uses the same placement rules as creation (orient to the picked wall
    face, sill-height snap, centre on the cursor). Runs its own Snapper
    session, so it must be invoked with no task dialog open (e.g. from the
    context menu, or after the panel closes). When `reopen` is True the
    WindowsPlus panel is re-shown afterwards — used by the panel's Reposition
    button, which has to close the panel to free the task view for the pick."""
    if window is None or getattr(window, "Base", None) is None:
        return
    import draftguitools.gui_trackers as DraftTrackers

    doc = window.Document
    width = window.Width.Value
    height = window.Height.Value
    depth = window.Frame.Value if hasattr(window, "Frame") else 100.0
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
        _placeTracker(tracker, _windowPlacement(point, state["face"], width),
                      width, height)

    def _place(point=None, obj=None):
        FreeCADGui.Snapper.off()
        tracker.off()
        try:
            if point is None:
                return                       # cancelled
            doc.openTransaction("Reposition Window")
            window.Base.Placement = _windowPlacement(point, state["face"], width)
            if state["face"] is not None:
                import Draft
                host = state["face"][0]
                if Draft.getType(host) in ("Wall", "Structure", "Roof"):
                    window.Hosts = [host]
            # Moving the sketch placement touches the window but NOT its host,
            # so the old opening would linger. Force the window, then re-cut
            # wall(s).
            window.touch()
            _recomputeWithHosts(window)
            doc.commitTransaction()
        finally:
            tracker.finalize()
            # Re-show the panel that closed itself to make room for the pick.
            if reopen:
                QtCore.QTimer.singleShot(
                    0, lambda: FreeCADGui.Control.showDialog(
                        WindowsPlusTaskPanel(window)))

    FreeCAD.Console.PrintMessage(
        "WindowsPlus: click a new location for the window.\n")
    FreeCADGui.Snapper.getPoint(callback=_place, movecallback=_move)


# ---------------------------------------------------------------------------
# Command — toolbar/menu button
# ---------------------------------------------------------------------------
class WindowsPlusCommand:
    """Interactive window command: pick a point/face, then configure.

    Flow:
      1. Activated()  — start box tracker + snapper
      2. update()     — move preview box with mouse
      3. getPoint()   — create window at picked location, open config panel
    """

    # Default dimensions (same as the task panel defaults)
    WIDTH = 1200
    HEIGHT = 1200
    FRAME_W = 50
    SASH_T = 45
    FRAME_D = 100
    SILL = 900       # default sill height above the wall base

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Window",
                "ToolTip": "Place a window, then configure it (WindowsPlus)"}

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
        # A window usually sits at a sill height above the floor, so by default
        # we snap its base to (wall base + sill height). The user then only
        # aims along the wall, not at the exact sill height. The sill height is
        # adjustable in the placement taskbox.
        self.snapBase = True
        self.baseOffset = float(self.SILL)   # sill height above the wall base

        # Box tracker as preview
        self.wp = WorkingPlane.get_working_plane()
        self.tracker = DraftTrackers.boxTracker()
        self.tracker.length(self.width)
        self.tracker.width(self.frameDepth)
        self.tracker.height(self.height)
        self.tracker.on()

        FreeCAD.Console.PrintMessage(
            "WindowsPlus: Click to place the window, then configure it.\n")

        FreeCADGui.Snapper.getPoint(
            callback=self.getPoint,
            movecallback=self.update,
            extradlg=self.taskbox(),
        )

    def update(self, point, info):
        """Move the preview box as the mouse moves.

        The box is positioned from the SAME _windowPlacement used on click, so
        the preview shows exactly where the window will land — centred on the
        cursor and sitting at the sill height — rather than off to one side."""
        if info and "Face" in info.get("Component", ""):
            o = self.doc.getObject(info["Object"])
            try:
                fi = int(info["Component"][4:]) - 1
            except (ValueError, IndexError):
                self.baseFace = None
            else:
                self.baseFace = [o, fi]

        pl = _windowPlacement(point, self.baseFace, self.width,
                              self.snapBase, self.baseOffset)
        _placeTracker(self.tracker, pl, self.width, self.height)

    def getPoint(self, point=None, obj=None):
        """Called when the user clicks: create window, then schedule config panel."""
        FreeCADGui.Snapper.off()
        self.tracker.off()

        if point is None:
            self.tracker.finalize()
            return

        import Draft

        doc = self.doc
        doc.openTransaction("Create Window")

        # Placement: oriented to the picked face, sill-height-snapped, centred
        # on the cursor (shared with reposition so create and move behave
        # identically).
        pl = _windowPlacement(point, self.baseFace, self.width,
                              self.snapBase, self.baseOffset)

        # Build the window geometry at identity, then apply placement
        spec = dict(
            operation="Fixed",
            width=self.width,
            height=self.height,
            frameWidth=self.FRAME_W,
            sashThk=self.SASH_T,
            frameDepth=self.frameDepth,
            swingSide="Left",
            swingDir="Inward",
        )

        sketch, wp_list = _makeWindowGeometry(spec)
        sketch.Placement = pl
        doc.recompute()

        import windowsplus_object
        window = windowsplus_object.makeWindow(sketch, self.width, self.height,
                                                wp_list, name="Window")
        if window is None:
            doc.abortTransaction()
            self.tracker.finalize()
            return

        # Set Frame and Offset to match the geometry.  makeWindow doesn't
        # set these, so do it here (mirrors the panel's _apply).
        window.Frame = self.SASH_T
        window.Offset = 0
        window.Preset = 0

        if window and hasattr(window, "Base") and window.Base:
            try:
                window.Base.ViewObject.DisplayMode = "Wireframe"
                window.Base.ViewObject.hide()
            except Exception:
                pass

        # Try to auto-host if a wall was clicked
        if self.baseFace is not None:
            host = self.baseFace[0]
            if Draft.getType(host) in ("Wall", "Structure", "Roof"):
                window.Hosts = [host]

        doc.recompute()
        self.tracker.finalize()

        # Defer panel opening to the next event-loop tick.
        # showDialog cannot be called from inside a Snapper callback.
        QtCore.QTimer.singleShot(
            0, lambda: FreeCADGui.Control.showDialog(
                WindowsPlusTaskPanel(obj=window, placed=True)))

    def taskbox(self):
        """Minimal widget shown during interactive placement."""
        from PySide import QtGui

        w = QtGui.QWidget()
        w.setWindowTitle("Window placement")
        grid = QtGui.QGridLayout(w)

        label = QtGui.QLabel("Click on a face or in space\nto place the window.")
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

        # Sit-on-base toggle — the window base snaps to (wall base + sill
        # height) so you aim along the wall and the window sits at the right
        # height automatically.
        baseChk = QtGui.QCheckBox("Snap to wall base + sill height")
        baseChk.setChecked(self.snapBase)
        baseChk.setToolTip(
            "Place the window base at (wall base + sill height), so you only "
            "need to aim along the wall — not at the exact sill height.")
        baseChk.toggled.connect(
            lambda checked: setattr(self, "snapBase", bool(checked)))
        grid.addWidget(baseChk, 2, 0, 1, 2)

        # Sill height — place the window above the wall base.
        grid.addWidget(QtGui.QLabel("Sill height"), 3, 0, 1, 1)
        offset_input = FreeCADGui.UiLoader().createWidget("Gui::QuantitySpinBox")
        try:
            offset_input.setProperty("value",
                FreeCAD.Units.Quantity("%.6f mm" % float(self.baseOffset)))
        except Exception:
            offset_input = QtGui.QDoubleSpinBox()
            offset_input.setSuffix(" mm")
            offset_input.setValue(self.baseOffset)
        offset_input.setToolTip(
            "Sill height — height of the window base above the wall base "
            "(floor). 900 mm is typical; 0 places it at the floor.")
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
if "ArchPlus_Windows" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_Windows", WindowsPlusCommand())
