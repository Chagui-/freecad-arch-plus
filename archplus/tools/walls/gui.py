# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WallsPlus GUI: commands, ViewProvider and the two task panels (wall root
# and segment). Follows the stairs/windows panel pattern: docked form,
# debounced live preview, reference diagrams, description lines.

import os

import FreeCAD
import FreeCADGui

from PySide import QtCore, QtGui

from archplus.common import widgets
from archplus.tools.walls import object as walls_object
from archplus.tools.walls import model

_DIR = os.path.dirname(__file__)
ICON = os.path.join(_DIR, "resources", "icons", "WallPlus.svg")
_ICON_DIR = os.path.join(_DIR, "resources", "icons")

WIDTH_DESC = "Thickness of the wall, perpendicular to its baseline."
HEIGHT_DESC = "Vertical height, measured from the sketch plane."
ALIGN_DESC = "Which side of the baseline the wall extends from."
OFFSET_DESC = "Extra distance between the baseline and the wall (Left/Right only)."


def _desc(text):
    lbl = QtGui.QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet("color: #8a8783; font-size: 10px;")
    return lbl


def _sketches_in_doc(doc):
    out = []
    for o in doc.Objects:
        if o.isDerivedFrom("Sketcher::SketchObject"):
            out.append(o)
    return out


class _ViewProviderWall:
    def __init__(self, vobj):
        vobj.Proxy = self

    def getIcon(self):
        return ICON

    def setEdit(self, vobj, mode=0):
        obj = vobj.Object
        if getattr(getattr(obj, "Proxy", None), "Type", None) == walls_object.TYPE_WALL:
            showWallPanel(obj)
        else:
            showSegmentPanel(obj)
        return True

    def unsetEdit(self, vobj, mode=0):
        FreeCADGui.Control.closeDialog()
        return False


def _ensureVP(obj):
    vp = obj.ViewObject
    if getattr(getattr(vp, "Proxy", None), "__class__", None) is not _ViewProviderWall:
        _ViewProviderWall(vp)


class WallPlusTaskPanel:
    """Edit/create panel for the wall root."""

    def __init__(self, obj=None):
        self.obj = obj
        self.editing = obj is not None
        self._building = True

        title = "Edit Wall" if self.editing else "Wall"
        self.form = QtGui.QWidget()
        self.form.setWindowTitle(title)
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))
        outer = QtGui.QVBoxLayout(self.form)

        dimBox = QtGui.QGroupBox("Dimensions")
        dimV = QtGui.QVBoxLayout(dimBox)
        dimV.addWidget(widgets.ref_image(_ICON_DIR, "dimensions_ref_plan",
                                         QtCore.QSize(290, 110)))
        dimV.addWidget(widgets.ref_image(_ICON_DIR, "align_offset_ref",
                                         QtCore.QSize(290, 80)))
        dimForm = QtGui.QFormLayout()
        self.width = widgets.length_input(300)
        self.height = widgets.length_input(2800)
        self.align = QtGui.QComboBox()
        self.align.addItems(["Center", "Left", "Right"])
        self.offset = widgets.length_input(0)
        dimForm.addRow("W · Width", self.width)
        dimV.addWidget(_desc(WIDTH_DESC))
        dimForm.addRow("H · Height", self.height)
        dimV.addWidget(_desc(HEIGHT_DESC))
        dimForm.addRow("Align", self.align)
        dimV.addWidget(_desc(ALIGN_DESC))
        dimForm.addRow("Offset", self.offset)
        dimV.addWidget(_desc(OFFSET_DESC))
        dimV.addLayout(dimForm)
        dimV.addWidget(_desc("These are the defaults — children follow them "
                             "unless they override."))
        outer.addWidget(dimBox)

        skBox = QtGui.QGroupBox("Sketch & claims")
        skV = QtGui.QVBoxLayout(skBox)
        skForm = QtGui.QFormLayout()
        self.sketch = QtGui.QComboBox()
        self.rest = QtGui.QComboBox()
        skForm.addRow("Sketch", self.sketch)
        skV.addLayout(skForm)
        skV.addWidget(_desc("The base sketch. Shared freely — other walls can "
                            "use it too."))
        restForm = QtGui.QFormLayout()
        restForm.addRow("Rest segment", self.rest)
        skV.addLayout(restForm)
        skV.addWidget(_desc("This segment auto-claims any new sketch edge. "
                            "\"None\" = new edges build nothing."))
        self.stats = QtGui.QLabel()
        self.stats.setStyleSheet("color: #2e7d32;")
        skV.addWidget(self.stats)
        outer.addWidget(skBox)

        metaBox = QtGui.QGroupBox("Metadata")
        metaForm = QtGui.QFormLayout(metaBox)
        self.tag = QtGui.QLineEdit()
        self.tag.setPlaceholderText("e.g. W01")
        metaForm.addRow("Tag / Mark", self.tag)
        outer.addWidget(metaBox)

        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        for w in (self.width, self.height, self.offset):
            w.valueChanged.connect(self._schedule)
        self.align.currentIndexChanged.connect(self._schedule)
        self.tag.textChanged.connect(self._schedule)
        self.sketch.currentIndexChanged.connect(self._schedule)
        self.rest.currentIndexChanged.connect(self._schedule)

        self._building = False
        if self.obj is not None:
            self._loadFromObject()
            FreeCAD.ActiveDocument.openTransaction("Edit Wall")
        else:
            self._startPreview()
        self._updateCombos()
        self._updateStats()

    def _schedule(self, *args):
        if not self._building and self.obj is not None:
            self._timer.start()

    def _apply(self):
        try:
            vals = self._collect()
            o = self.obj
            o.Width = "%s mm" % vals["width"]
            o.Height = "%s mm" % vals["height"]
            o.Align = vals["align"]
            o.Offset = "%s mm" % vals["offset"]
            o.Tag = vals["tag"]
            if vals["base"] is not None:
                o.Base = vals["base"]
            FreeCAD.ActiveDocument.recompute()
            self._updateStats()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus: %s\n" % exc)

    def _collect(self):
        return dict(
            width=widgets.mm(self.width),
            height=widgets.mm(self.height),
            align=self.align.currentText(),
            offset=widgets.mm(self.offset),
            tag=self.tag.text(),
            base=self.sketch.currentData(),
            rest=self.rest.currentData(),
        )

    def _loadFromObject(self):
        self._building = True
        o = self.obj
        widgets.set_mm(self.width, o.Width.Value)
        widgets.set_mm(self.height, o.Height.Value)
        self.align.setCurrentText(o.Align)
        widgets.set_mm(self.offset, o.Offset.Value)
        self.tag.setText(getattr(o, "Tag", ""))
        self._building = False

    def _updateCombos(self):
        doc = FreeCAD.ActiveDocument
        self._building = True
        self.sketch.clear()
        for sk in _sketches_in_doc(doc):
            self.sketch.addItem(sk.Label, sk)
        base = self.obj.Base if self.obj is not None else None
        if base is not None:
            idx = self.sketch.findData(base)
            if idx >= 0:
                self.sketch.setCurrentIndex(idx)
        self.rest.clear()
        self.rest.addItem("None", None)
        if self.obj is not None:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    self.rest.addItem(o.Label, o)
            rest = [o for o in self.obj.Group
                    if walls_object.is_segment(o) and getattr(o, "Rest", False)]
            if rest:
                idx = self.rest.findData(rest[0])
                if idx >= 0:
                    self.rest.setCurrentIndex(idx)
        self._building = False

    def _updateStats(self):
        try:
            o = self.obj
            if o is None or o.Base is None:
                self.stats.setText("")
                return
            nodes = [walls_object._claimNode(n) for n in o.Group
                     if walls_object.is_segment(n)]
            built, _warnings = model.resolve_claims(
                nodes, walls_object._sketchEdgeNames(o.Base))
            claimed = set().union(*built.values()) if built else set()
            total = len(walls_object._sketchEdgeNames(o.Base))
            self.stats.setText("%d edges claimed · %d unclaimed"
                               % (len(claimed), total - len(claimed)))
        except Exception:
            self.stats.setText("")

    def _startPreview(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            doc = FreeCAD.newDocument()
        doc.openTransaction("Create Wall")
        sel = FreeCADGui.Selection.getSelection()
        sketch = sel[0] if sel and sel[0].isDerivedFrom("Sketcher::SketchObject") else None
        self.obj = walls_object.makeWall(doc, sketch=sketch)
        _ensureVP(self.obj)
        _ensureVP(self.obj.Group[0])
        self._apply()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    def accept(self):
        self._timer.stop()
        self._apply()
        vals = self._collect()
        if vals["rest"] is not None:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    o.Rest = (o is vals["rest"])
        else:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    o.Rest = False
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
        self.obj = None
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        self._timer.stop()
        self.obj = None
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.abortTransaction()
            FreeCAD.ActiveDocument.recompute()
        FreeCADGui.Control.closeDialog()
        return True


class WallPlusCommand:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Wall",
                "ToolTip": "Build walls from a shared sketch"}

    def IsActive(self):
        doc = FreeCAD.ActiveDocument
        if doc is None:
            return False
        sel = FreeCADGui.Selection.getSelection()
        return bool(sel) and sel[0].isDerivedFrom("Sketcher::SketchObject")

    def Activated(self):
        FreeCADGui.Control.showDialog(WallPlusTaskPanel())


def showWallPanel(obj):
    FreeCADGui.Control.showDialog(WallPlusTaskPanel(obj))


def showSegmentPanel(obj):
    FreeCADGui.Control.showDialog(WallSegmentTaskPanel(obj))


class WallSegmentTaskPanel:
    """Edit panel for one segment: W/H/Align overrides with the
    inherit-checkbox pattern, plus a read-only claims summary."""

    def __init__(self, obj=None):
        self.obj = obj
        self.editing = obj is not None
        self._building = True

        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Edit Segment")
        if os.path.exists(ICON):
            self.form.setWindowIcon(QtGui.QIcon(ICON))
        outer = QtGui.QVBoxLayout(self.form)

        ovBox = QtGui.QGroupBox("Override")
        ovV = QtGui.QVBoxLayout(ovBox)
        ovV.addWidget(widgets.ref_image(_ICON_DIR, "dimensions_ref_plan",
                                        QtCore.QSize(290, 110)))
        ovForm = QtGui.QFormLayout()
        self.overrideW = QtGui.QCheckBox("W · Width")
        self.overrideH = QtGui.QCheckBox("H · Height")
        self.width = widgets.length_input(0)
        self.height = widgets.length_input(0)
        self.align = QtGui.QComboBox()
        self.align.addItems(["Inherit", "Left", "Right", "Center"])
        ovForm.addRow(self.overrideW, self.width)
        ovV.addWidget(_desc("Checked = this segment overrides the wall default."))
        ovForm.addRow(self.overrideH, self.height)
        ovV.addWidget(_desc("Inherited from the wall/group. Check to override, "
                            "pre-filled with the inherited value."))
        ovForm.addRow("Align", self.align)
        ovV.addLayout(ovForm)
        outer.addWidget(ovBox)

        clBox = QtGui.QGroupBox("Claims")
        clV = QtGui.QVBoxLayout(clBox)
        self.stats = QtGui.QLabel()
        self.stats.setStyleSheet("color: #2e7d32;")
        clV.addWidget(self.stats)
        clV.addWidget(_desc("Split / reassign edges with \"Split from "
                            "selection…\" in the 3D view. Rest and Sketch are "
                            "set in the wall panel."))
        outer.addWidget(clBox)

        self._timer = QtCore.QTimer()
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._apply)

        for w in (self.width, self.height):
            w.valueChanged.connect(self._schedule)
        self.align.currentIndexChanged.connect(self._schedule)
        self.overrideW.toggled.connect(self._onOverrideW)
        self.overrideH.toggled.connect(self._onOverrideH)

        self._building = False
        self._loadFromObject()
        self._updateStats()
        if self.editing:
            FreeCAD.ActiveDocument.openTransaction("Edit Segment")

    def _schedule(self, *args):
        if not self._building and self.obj is not None:
            self._timer.start()

    def _inherited(self):
        try:
            return walls_object.effectiveValues(self.obj)
        except Exception:
            return dict(model.DEFAULT_CONFIG)

    def _onOverrideW(self, checked):
        if self._building or self.obj is None:
            return
        if checked:
            widgets.set_mm(self.width, self._inherited()["Width"])
        else:
            self.obj.Width = 0
            self._loadFromObject()

    def _onOverrideH(self, checked):
        if self._building or self.obj is None:
            return
        if checked:
            widgets.set_mm(self.height, self._inherited()["Height"])
        else:
            self.obj.Height = 0
            self._loadFromObject()

    def _apply(self):
        try:
            vals = self._collect()
            o = self.obj
            o.Width = "%s mm" % vals["width"]
            o.Height = "%s mm" % vals["height"]
            o.Align = vals["align"]
            FreeCAD.ActiveDocument.recompute()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus: %s\n" % exc)

    def _collect(self):
        return dict(
            width=widgets.mm(self.width) if self.overrideW.isChecked() else 0.0,
            height=widgets.mm(self.height) if self.overrideH.isChecked() else 0.0,
            align=self.align.currentText(),
        )

    def _loadFromObject(self):
        self._building = True
        o = self.obj
        w = getattr(o, "Width", None)
        wv = w.Value if w is not None else 0.0
        self.overrideW.setChecked(wv != 0.0)
        inherited = self._inherited()
        widgets.set_mm(self.width, wv if wv else inherited["Width"])
        h = getattr(o, "Height", None)
        hv = h.Value if h is not None else 0.0
        self.overrideH.setChecked(hv != 0.0)
        widgets.set_mm(self.height, hv if hv else inherited["Height"])
        self.align.setCurrentText(getattr(o, "Align", "Inherit"))
        self.width.setEnabled(self.overrideW.isChecked())
        self.height.setEnabled(self.overrideH.isChecked())
        self._building = False

    def _updateStats(self):
        try:
            o = self.obj
            root = walls_object.wall_root(o) or o
            if root.Base is None:
                self.stats.setText("")
                return
            nodes = [walls_object._claimNode(n) for n in root.Group
                     if walls_object.is_segment(n)]
            built, _warnings = model.resolve_claims(
                nodes, walls_object._sketchEdgeNames(root.Base))
            mine = built.get(o, frozenset())
            auto = len(mine) if getattr(o, "Rest", False) else 0
            self.stats.setText("%d edges claimed · %d auto"
                               % (len(mine), auto))
        except Exception:
            self.stats.setText("")

    def accept(self):
        self._timer.stop()
        self._apply()
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.commitTransaction()
            FreeCAD.ActiveDocument.recompute()
        self.obj = None
        FreeCADGui.Control.closeDialog()
        return True

    def reject(self):
        self._timer.stop()
        self.obj = None
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.abortTransaction()
            FreeCAD.ActiveDocument.recompute()
        FreeCADGui.Control.closeDialog()
        return True


FreeCADGui.addCommand("ArchPlus_Walls", WallPlusCommand())


def _claimedEdgePolylines(segment):
    """[(subname, [global points])] for each claimed edge, for matching."""
    sketch = segment.Base
    out = []
    if sketch is None or not hasattr(sketch, "Shape"):
        return out
    for sub in sorted(segment.Proxy._claimedEdges(segment)):
        try:
            edge = sketch.Shape.getElement(sub)
            pts = [edge.Vertexes[0].Point]
            for p in edge.discretize(16)[1:]:
                pts.append(p)
            out.append((sub, pts))
        except Exception:
            continue
    return out


class WallSplitCommand:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Split segment",
                "ToolTip": "Move selected wall faces into a new segment group"}

    def IsActive(self):
        for sel in FreeCADGui.Selection.getSelectionEx():
            if walls_object.is_segment(sel.Object):
                return True
        return False

    def Activated(self):
        from archplus.tools.walls import object as walls_object
        doc = FreeCAD.ActiveDocument
        doc.openTransaction("Split wall segment")
        for sel in FreeCADGui.Selection.getSelectionEx():
            obj = sel.Object
            if not walls_object.is_segment(obj):
                continue
            if sel.HasSubObjects:
                picked = []
                for name in sel.SubElementNames:
                    if not name.startswith("Face"):
                        continue
                    try:
                        face = obj.Shape.getElement(name)
                    except Exception:
                        continue
                    idx = model.match_edge(
                        [pts for _sub, pts in _claimedEdgePolylines(obj)],
                        tuple(face.CenterOfGravity), tol=5.0)
                    if idx is not None:
                        picked.append(_claimedEdgePolylines(obj)[idx][0])
                if picked:
                    walls_object.splitSegment(obj, sorted(set(picked)))
            else:
                subs = [sub for sub in obj.Proxy._claimedEdges(obj)]
                if subs:
                    walls_object.splitSegment(obj, subs)
        doc.recompute()
        doc.commitTransaction()


FreeCADGui.addCommand("ArchPlus_WallSplit", WallSplitCommand())
