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
            o.recompute()
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
        o = self.obj
        widgets.set_mm(self.width, o.Width.Value)
        widgets.set_mm(self.height, o.Height.Value)
        self.align.setCurrentText(o.Align)
        widgets.set_mm(self.offset, o.Offset.Value)
        self.tag.setText(getattr(o, "Tag", ""))

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
            if self.editing:
                FreeCAD.ActiveDocument.recompute()
            else:
                FreeCAD.ActiveDocument.commitTransaction()
                FreeCAD.ActiveDocument.recompute()

    def reject(self):
        if FreeCAD.ActiveDocument is not None:
            FreeCAD.ActiveDocument.abortTransaction()


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
    """Edit panel for one segment: overrides with the inherit-checkbox
    pattern plus a read-only claims summary. Implemented in Task 5; this
    stub lets Task 4's imports and _ensureVP wiring stay complete."""

    def __init__(self, obj=None):
        self.obj = obj
        self.form = QtGui.QWidget()

    def accept(self):
        return True

    def reject(self):
        return True


FreeCADGui.addCommand("ArchPlus_Walls", WallPlusCommand())
