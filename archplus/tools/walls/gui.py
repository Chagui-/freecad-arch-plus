# SPDX-License-Identifier: LGPL-2.1-or-later
#
# WallsPlus GUI: commands, the two task panels (wall root and segment) and
# the split command's selection gate with its pick-point recorder. Follows
# the stairs/windows panel pattern: docked form, debounced live preview,
# reference diagrams, description lines. The view provider lives in
# object.py; gui.py only consumes it.

import os

import FreeCAD
import FreeCADGui
from FreeCAD import Vector

from PySide import QtCore, QtGui

from archplus.common import widgets
from archplus.tools.walls import object as walls_object
from archplus.tools.walls import model
from archplus.tools.walls import dims

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
        self.fallback = QtGui.QComboBox()
        skForm.addRow("Sketch", self.sketch)
        skV.addLayout(skForm)
        skV.addWidget(_desc("The base sketch. Shared freely — other walls can "
                            "use it too."))
        fallbackForm = QtGui.QFormLayout()
        fallbackForm.addRow("Fallback segment", self.fallback)
        skV.addLayout(fallbackForm)
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
        self.fallback.currentIndexChanged.connect(self._schedule)

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
            fallback=self.fallback.currentData(),
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
        self.fallback.clear()
        self.fallback.addItem("None", None)
        if self.obj is not None:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    self.fallback.addItem(o.Label, o)
            fallback = [o for o in self.obj.Group
                        if walls_object.is_segment(o)
                        and getattr(o, "Fallback", False)]
            if fallback:
                idx = self.fallback.findData(fallback[0])
                if idx >= 0:
                    self.fallback.setCurrentIndex(idx)
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
        self._apply()
        try:
            FreeCADGui.SendMsgToActiveView("ViewFit")
        except Exception:
            pass

    def accept(self):
        self._timer.stop()
        self._apply()
        vals = self._collect()
        if vals["fallback"] is not None:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    o.Fallback = (o is vals["fallback"])
        else:
            for o in self.obj.Group:
                if walls_object.is_segment(o):
                    o.Fallback = False
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


class _WallSelectionObserver:
    """Native selection behavior for wall segments.

    A tree click on a segment selects all of its faces, and a 3D pick of
    wall geometry — which FreeCAD attributes to the wall root, the claim
    parent — is redirected to the segment owning the picked point, so the
    tree highlights the right item. Face and edge picks alike resolve by
    point, never by the root's aggregate child index. FreeCAD's face tint
    is unreliable for a selected group child, so every selected face of a
    segment carries the highlight overlay; edge selections keep the
    native edge tint and are not overlaid. All actions run deferred on
    the event loop."""

    def __init__(self):
        self._lit = {}

    def addSelection(self, doc, obj, sub, pnt):
        try:
            from PySide import QtCore
            QtCore.QTimer.singleShot(
                0, lambda: self._run(doc, obj, sub, pnt))
        except Exception:
            pass

    def removeSelection(self, *_args):
        self._deferSync()

    def clearSelection(self, *_args):
        self._deferSync()

    def setSelection(self, *_args):
        self._deferSync()

    def _deferSync(self):
        try:
            from PySide import QtCore
            QtCore.QTimer.singleShot(0, self._syncOverlaysSafe)
        except Exception:
            pass

    def _run(self, doc, obj, sub, pnt):
        try:
            import FreeCADGui
            document = FreeCAD.getDocument(doc) if doc else None
            target = document.getObject(obj) if document else None
            if target is None:
                return
            if walls_object.is_segment(target) and not sub:
                self._selectFaces(FreeCADGui, target)
            elif walls_object.is_root(target) and sub.startswith("Face"):
                self._redirect(FreeCADGui, target, sub, pnt)
            elif walls_object.is_root(target) and sub.startswith("Edge"):
                self._redirectEdge(FreeCADGui, target, sub, pnt)
        except Exception:
            pass
        finally:
            self._syncOverlaysSafe()

    def _key(self, obj):
        return (obj.Document.Name, obj.Name)

    def _selectFaces(self, gui, seg):
        shape = getattr(seg, "Shape", None)
        if shape is None or shape.isNull() or not shape.Faces:
            return
        names = None
        for sel in gui.Selection.getSelectionEx():
            if sel.Object is seg:
                names = sel.SubElementNames
                break
        if names is None or names:
            return
        for i in range(len(shape.Faces)):
            gui.Selection.addSelection(seg, "Face%d" % (i + 1))

    def _redirect(self, gui, root, sub, pnt):
        still = False
        for sel in gui.Selection.getSelectionEx():
            if sel.Object is root and sub in (sel.SubElementNames or ()):
                still = True
                break
        if not still:
            return
        point = _asVector(pnt)
        resolved = walls_object.resolveRootFace(root, sub, point)
        if resolved is None:
            return
        seg, locals_ = resolved
        gui.Selection.removeSelection(root, sub)
        try:
            gui.Selection.addSelection(seg, locals_[0],
                                       point.x, point.y, point.z)
        except Exception:
            gui.Selection.addSelection(seg, locals_[0])

    def _redirectEdge(self, gui, root, sub, pnt):
        """The segment owning a rerouted edge pick. The point resolves the
        segment through its faces, and the segment's own edge nearest the
        point supplies the local subname: the root's reported edge index
        spans all claimed children, so it need not exist on one segment."""
        still = False
        for sel in gui.Selection.getSelectionEx():
            if sel.Object is root and sub in (sel.SubElementNames or ()):
                still = True
                break
        if not still:
            return
        point = _asVector(pnt)
        resolved = (walls_object.resolveRootFace(root, sub, point)
                    if point is not None else None)
        if resolved is None:
            return
        seg = resolved[0]
        local = _nearestEdgeName(seg, point)
        if local is None:
            return
        gui.Selection.removeSelection(root, sub)
        try:
            gui.Selection.addSelection(seg, local,
                                       point.x, point.y, point.z)
        except Exception:
            gui.Selection.addSelection(seg, local)

    def _syncOverlaysSafe(self):
        try:
            self._syncOverlays()
        except Exception:
            pass

    def _syncOverlays(self):
        """Draw the face overlay under every selected face of a segment —
        FreeCAD's own tint is unreliable for a selected group child — and
        drop overlays whose selection moved on. Edge selections keep the
        native edge tint; the overlay is not stacked for them."""
        import FreeCADGui
        lit = {}
        for sel in FreeCADGui.Selection.getSelectionEx():
            obj = sel.Object
            if not walls_object.is_segment(obj):
                continue
            subs = [s for s in (sel.SubElementNames or ())
                    if s.startswith("Face")]
            if not subs:
                continue
            key = self._key(obj)
            sig = ",".join(sorted(subs))
            if self._lit.get(key) == sig:
                lit[key] = sig
                continue
            try:
                if walls_object.addFaceHighlight(obj.ViewObject,
                                                 subs=subs):
                    lit[key] = sig
            except Exception:
                pass
        for key in set(self._lit) - set(lit):
            self._unlight(key)
        self._lit = lit

    def _unlight(self, key):
        self._lit.pop(key, None)
        try:
            import FreeCAD
            doc = FreeCAD.getDocument(key[0]) if key[0] else None
            obj = doc.getObject(key[1]) if doc else None
            if obj is None:
                return
            walls_object.removeFaceHighlight(
                obj.ViewObject, walls_object.FACE_HIGHLIGHT)
        except Exception:
            pass

    def refresh(self, obj):
        """Re-light a lit overlay after the shape was rebuilt under it."""
        try:
            key = self._key(obj)
            if key not in self._lit:
                return
            self._unlight(key)
            self._syncOverlaysSafe()
        except Exception:
            pass


def _nearestEdgeName(seg, point):
    """The segment-local subname of the edge nearest the pick point."""
    import Part
    try:
        vertex = Part.Vertex(point)
    except Exception:
        return None
    best = None
    best_dist = None
    for i, edge in enumerate(seg.Shape.Edges):
        try:
            dist = vertex.distToShape(edge)[0]
        except Exception:
            continue
        if best_dist is None or dist < best_dist:
            best, best_dist = i, dist
    return None if best is None else "Edge%d" % (best + 1)


_selobs = getattr(FreeCADGui, "_ArchPlusWallSelObs", None)
if _selobs is None:
    _selobs = _WallSelectionObserver()
    try:
        FreeCADGui.Selection.addObserver(_selobs)
        FreeCADGui._ArchPlusWallSelObs = _selobs
    except Exception:
        pass


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
        clV.addWidget(_desc("Split / reassign edges with \"Split / move "
                            "segment…\" after picking wall faces in the 3D "
                            "view. Fallback and Sketch are set in the wall panel."))
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
        if self._building:
            return
        self.width.setEnabled(checked)
        if self.obj is None:
            return
        if checked:
            widgets.set_mm(self.width, self._inherited()["Width"])
        else:
            self.obj.Width = 0
            self._loadFromObject()

    def _onOverrideH(self, checked):
        if self._building:
            return
        self.height.setEnabled(checked)
        if self.obj is None:
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
            auto = len(mine) if getattr(o, "Fallback", False) else 0
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


def _projectToSketchPlane(point, sketch):
    """The point projected onto the sketch's global plane along the
    plane's normal."""
    if sketch is None or not hasattr(sketch, "getGlobalPlacement"):
        return point
    placement = sketch.getGlobalPlacement()
    normal = placement.Rotation.multVec(Vector(0, 0, 1))
    return point - normal * (point - placement.Base).dot(normal)


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


NEW_SEGMENT = object()


class _PickPointRecorder:
    """Selection observer keeping each picked face's last pick points.

    FreeCAD attributes a 3D pick of a claimed child's face to the top claim
    parent, so a clicked wall face arrives as a root selection carrying a
    segment-local face index. Resolving that face to its owning segment
    needs the face subname together with the 3D point, which only this
    observer sees. Points are kept per (document, object, subname) as an
    ordered list: two segments' faces can share one subname on the root
    selection, and the k-th pick of a subname matches the k-th occurrence
    of that subname in the selection."""

    def __init__(self):
        self.picks = {}

    def addSelection(self, doc, obj, sub, pnt):
        try:
            key = (_name(doc), _name(obj), sub)
            self.picks.setdefault(key, []).append(_asVector(pnt))
        except Exception:
            pass

    def removeSelection(self, doc, obj, sub):
        try:
            key = (_name(doc), _name(obj), sub)
            picks = self.picks.get(key)
            if picks:
                picks.pop(0)
            if picks is not None and not picks:
                del self.picks[key]
        except Exception:
            pass

    def clearSelection(self, doc):
        try:
            keys = list(self.picks) if not doc else [
                k for k in self.picks if k[0] == _name(doc)]
            for key in keys:
                del self.picks[key]
        except Exception:
            pass

    def setSelection(self, doc):
        self.clearSelection(doc)


def _asVector(pnt):
    """The pick point as a Vector (None when there is none)."""
    if pnt is None:
        return None
    try:
        return Vector(pnt.x, pnt.y, pnt.z)
    except Exception:
        pass
    try:
        return Vector(pnt[0], pnt[1], pnt[2])
    except Exception:
        return None


def _name(obj):
    return getattr(obj, "Name", obj)


def _lastPick(doc, obj, sub, occurrence=0):
    """The recorded pick point for a face of a selection member: the
    occurrence-th pick of that subname, or None."""
    try:
        picks = _recorder.picks.get((_name(doc), _name(obj), sub))
        if picks and occurrence < len(picks):
            return picks[occurrence]
        return None
    except Exception:
        return None


_recorder = getattr(FreeCADGui, "_ArchPlusPickRecorder", None)
if _recorder is None:
    _recorder = _PickPointRecorder()
    try:
        FreeCADGui.Selection.addObserver(_recorder)
        FreeCADGui._ArchPlusPickRecorder = _recorder
    except Exception:
        pass
dims.install()


def wall_segment_selected():
    """True when any selection member is a wall segment or the wall root.

    Clicking a wall face selects the root (FreeCAD attributes picks of
    claimed children to the top claim parent), so root selections count;
    the split command resolves them to the owning segments when it runs."""
    for sel in FreeCADGui.Selection.getSelectionEx():
        obj = sel.Object
        if walls_object.is_segment(obj) or walls_object.is_root(obj):
            return True
    return False


class _FaceSelection:
    """Minimal selection stand-in for one picked face of a segment."""

    def __init__(self, obj, sub, point):
        self.Object = obj
        self.SubElementNames = [sub]
        self.PickedPoints = [point] if point is not None else []
        self.HasSubObjects = True


class WallSplitCommand:
    def GetResources(self):
        return {"Pixmap": ICON, "MenuText": "Split / move segment…",
                "ToolTip": "Move the selected wall faces into a new or an "
                           "existing segment"}

    def IsActive(self):
        if FreeCAD.ActiveDocument is None:
            return False
        return wall_segment_selected()

    def Activated(self):
        doc = FreeCAD.ActiveDocument
        sources = []
        had_faces = False
        for sel in FreeCADGui.Selection.getSelectionEx():
            obj = sel.Object
            if walls_object.is_segment(obj):
                subs = self._pickedEdges(obj, sel)
                if subs:
                    had_faces = True
                    sources.append((obj, subs))
            elif walls_object.is_root(obj):
                if sel.SubElementNames:
                    had_faces = True
                sources.extend(self._rootSources(doc, sel))
        if not sources:
            if not had_faces:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: Click one or more wall faces in the 3D view, "
                    "then choose Split / move segment\n")
            return
        roots = []
        for obj, _subs in sources:
            root = walls_object.wall_root(obj) or obj
            if not any(root is r for r in roots):
                roots.append(root)
        if len(roots) > 1:
            FreeCAD.Console.PrintWarning(
                "ArchPlus: Selected segments belong to several walls; "
                "split or move one wall at a time\n")
            return
        choice = self._chooseTarget(sources)
        if choice is None:
            return
        doc.openTransaction("Split / move wall segment")
        for obj, subs in sources:
            if choice is NEW_SEGMENT:
                walls_object.splitSegment(obj, subs)
            else:
                walls_object.moveSegmentEdges(obj, choice, subs)
        doc.recompute()
        doc.commitTransaction()

    def _rootSources(self, doc, sel):
        """(segment, subs) sources for a wall-root selection member.

        Clicking a wall face selects the root (FreeCAD claims-children pick
        behavior) with a segment-local face index, so each picked face is
        resolved to its owning segment through its own recorded pick point
        and then mapped to its claimed run like a direct segment pick."""
        root = sel.Object
        doc_key = getattr(root, "Document", None) or doc
        names = [n for n in (sel.SubElementNames or ())
                 if n.startswith("Face")]
        sources = []
        seen = {}
        for name in names:
            occurrence = seen.get(name, 0)
            seen[name] = occurrence + 1
            point = _lastPick(doc_key, root, name, occurrence)
            resolved = walls_object.resolveRootFace(root, name, point)
            if resolved is None:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: could not resolve face '%s' of '%s'; click "
                    "the face again\n" % (name, root.Label))
                continue
            segment, locals_ = resolved
            subs = self._pickedEdges(segment, _FaceSelection(segment,
                                                             locals_[0],
                                                             point))
            if subs:
                sources.append((segment, subs))
        return sources

    def _chooseTarget(self, sources):
        """The dialog choice for the picked faces: NEW_SEGMENT (split into
        a new sibling per source), an existing target segment, or None when
        the dialog is cancelled. Rows map one-to-one to the options
        (repeated labels get a " (n)" suffix), so a choice always binds to
        the exact segment it listed."""
        options = self._targetOptions(sources)
        rows = ["<new segment>"] + self._targetLabels(options)
        segs = [NEW_SEGMENT] + list(options)
        choice = self._runPicker(rows, segs)
        for seg in options:
            try:
                walls_object.removeFaceHighlight(
                    seg.ViewObject, walls_object.PREVIEW_HIGHLIGHT)
            except Exception:
                pass
        return choice

    def _targetLabels(self, options):
        """Display labels for the target options; repeats get a " (n)"
        suffix so every row stays distinguishable."""
        labels = []
        seen = set()
        for seg in options:
            label = seg.Label
            n = 2
            while label in seen:
                label = "%s (%d)" % (seg.Label, n)
                n += 1
            seen.add(label)
            labels.append(label)
        return labels

    def _runPicker(self, rows, segs):
        """Modal picker over the target rows: NEW_SEGMENT, a segment, or
        None when cancelled. Hovering a row previews that segment in the
        3D view."""
        from PySide import QtGui

        class _Picker(QtGui.QDialog):
            def __init__(self, parent=None):
                QtGui.QDialog.__init__(self, parent)
                self.setWindowTitle("Split / move segment")
                self.choice = None
                self._previewed = None
                outer = QtGui.QVBoxLayout(self)
                outer.addWidget(QtGui.QLabel("Move the selected faces to:"))
                self.listw = QtGui.QListWidget()
                self.listw.addItems(rows)
                self.listw.setCurrentRow(0)
                outer.addWidget(self.listw)
                hint = QtGui.QLabel("Hover a segment to preview it in the "
                                    "3D view; double-click to choose.")
                hint.setWordWrap(True)
                outer.addWidget(hint)
                buttons = QtGui.QDialogButtonBox(
                    QtGui.QDialogButtonBox.Ok
                    | QtGui.QDialogButtonBox.Cancel)
                outer.addWidget(buttons)
                buttons.accepted.connect(self.accept)
                buttons.rejected.connect(self.reject)
                self.listw.itemDoubleClicked.connect(self.accept)
                self.listw.currentRowChanged.connect(self._preview)
                self.listw.itemEntered.connect(self._previewItem)

            def _previewAt(self, row):
                try:
                    if self._previewed is not None:
                        walls_object.removeFaceHighlight(
                            self._previewed,
                            walls_object.PREVIEW_HIGHLIGHT)
                        self._previewed = None
                    seg = segs[row]
                    if seg is not NEW_SEGMENT:
                        vobj = seg.ViewObject
                        if walls_object.addFaceHighlight(
                                vobj, walls_object.PREVIEW_HIGHLIGHT,
                                (0.95, 0.55, 0.10), 0.55):
                            self._previewed = vobj
                except Exception:
                    pass

            def _preview(self, row):
                self._previewAt(int(row))

            def _previewItem(self, item):
                self._previewAt(self.listw.row(item))

            def accept(self):
                self._clearPreview()
                self.choice = segs[self.listw.currentRow()]
                QtGui.QDialog.accept(self)

            def reject(self):
                self._clearPreview()
                self.choice = None
                QtGui.QDialog.reject(self)

            def _clearPreview(self):
                try:
                    if self._previewed is not None:
                        walls_object.removeFaceHighlight(
                            self._previewed,
                            walls_object.PREVIEW_HIGHLIGHT)
                except Exception:
                    pass
                self._previewed = None

        parent = (FreeCADGui.getMainWindow()
                  if hasattr(FreeCADGui, "getMainWindow") else None)
        dlg = _Picker(parent)
        dlg.exec_()
        return dlg.choice

    def _targetOptions(self, sources):
        """The wall's other top-level segments, excluding the sources and
        their ancestors: moving into the source's own ancestor would empty
        the source into its parent group, the degenerate empty-segment
        outcome this rework removes."""
        skip = set()
        for obj, _subs in sources:
            skip.add(obj.Name)
            node = walls_object.parent_group(obj)
            while node is not None and node.Name not in skip:
                skip.add(node.Name)
                node = walls_object.parent_group(node)
        root = walls_object.wall_root(sources[0][0]) or sources[0][0]
        options = []
        for seg in root.Group:
            if not walls_object.is_segment(seg) or seg.Name in skip:
                continue
            options.append(seg)
        return options

    def _pickedEdges(self, obj, sel):
        """The claimed subnames under the selection's picked faces.

        Each picked face maps through the user's actual click point —
        projected onto the sketch plane and matched to the nearest claimed
        edge within one effective wall width, since a point inside the
        wall band can never be farther than that from its baseline. When
        FreeCAD recorded no pick point the face centroid is projected and
        matched instead. Splitting requires picked faces: a selection
        without subelements maps to nothing. A face that maps to no claimed
        edge is reported in the Report view instead of splitting nothing."""
        polys = _claimedEdgePolylines(obj)
        if not sel.HasSubObjects or not polys:
            return []
        names = list(sel.SubElementNames)
        points = list(sel.PickedPoints)
        paired = points if len(points) == len(names) else [None] * len(names)
        tol = walls_object.effectiveValues(obj)["Width"]
        picked = []
        for i, name in enumerate(names):
            if not name.startswith("Face"):
                continue
            point = paired[i]
            if point is None:
                try:
                    point = obj.Shape.getElement(name).CenterOfGravity
                except Exception:
                    continue
            sub = self._nearestEdge(polys, _projectToSketchPlane(point,
                                                                obj.Base),
                                    tol)
            if sub is not None:
                picked.append(sub)
            else:
                FreeCAD.Console.PrintWarning(
                    "ArchPlus: face '%s' of segment '%s' is not on any "
                    "claimed run; nothing to split there\n"
                    % (name, obj.Label))
        return sorted(set(picked))

    def _nearestEdge(self, polys, point, tol):
        idx = model.match_edge([pts for _sub, pts in polys],
                               (point.x, point.y, point.z), tol)
        return None if idx is None else polys[idx][0]


FreeCADGui.addCommand("ArchPlus_WallSplit", WallSplitCommand())
