# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk Through — interactive first-person walk mode (ArchPlus).

Mouse-only by user decision: click the tool, aim the human figure at a
point on 3D geometry (left click places your eyes there, point + 1.65 m
along the picked face normal), then walk with the mouse wheel (each notch
steps forward/back along the view heading) and look by holding the right
mouse button. The toolbar toggle or the panel's Exit button ends the walk
and restores the saved camera.

Input capture: the viewer's normal dispatch hands every event straight to
the navigation style, bypassing scene-graph callbacks — so walk mode
enables the viewer's scene-graph event redirection and swallows events on
a scene-level SoEventCallback node; the input callback sees the full mouse
stream and native orbit/zoom never fight the per-tick camera rewrite (see
_start_input_capture). The tick still integrates the pose and rewrites the
Coin camera each frame; the ground under the eye is found with
ActiveView.getObjectInfoRay() (a vertical down-ray), so the eye rides
floors and stairs.

Placement does NOT use Draft's Snapper: the Snapper projects the cursor
ray onto the working plane unconditionally (getApparentPoint), which pins
picks to the plane's height — after placing doors on floor 1, a click on
the 2nd-floor slab would land at floor-1 height. _WalkPickFilter instead
reads the true scene hit under the cursor via ActiveView.getObjectInfo().

Session invariant: exactly ONE WalkSession (the one in _MODE) may run.
_start_walk stops any prior session, and every tick self-checks it is the
registered session — a replaced session tears itself down instead of
leaving a zombie timer rewriting the camera after exit.
"""

import math
import os
import time

import FreeCAD
import FreeCADGui
from PySide import QtGui, QtCore

from . import kinematics as kin
from . import state as walk_state

_DIR = os.path.dirname(__file__)     # archplus/tools/walk/, for resources/
ICON = os.path.join(_DIR, "resources", "icons", "WalkThrough.svg")

_MODE = None   # the active WalkSession, or None
_PICK = None   # the active _WalkPickFilter (placement phase), or None

PICK_HINT = ("ArchPlus Walk Through: aim the figure and left-click a point "
             "in the 3D view to start walking.")
ACTIVE_HINT = ("ArchPlus Walk Through: wheel to move, hold right-mouse to "
               "look, click the tool again to exit.")

# Live settings, shared between the task panel and every session in this
# FreeCAD run. Defaults honour the user's tested preferences.
_SETTINGS = {"eye_height": 1650.0, "invert_y": True, "invert_x": False}


def _find_viewer_widget():
    best = None
    for w in QtGui.QApplication.allWidgets():
        if (w.isVisible()
                and w.metaObject().className() == "Gui::View3DInventorViewer"):
            if (best is None
                    or w.width() * w.height() > best.width() * best.height()):
                best = w
    return best


class WalkSession:
    """One walk-mode session bound to one 3D view."""

    def __init__(self, view, eye, yaw, pitch=0.0):
        self.view = view
        self.controller = walk_state.WalkController(eye, yaw=yaw, pitch=pitch)
        self.controller.eye_height = _SETTINGS["eye_height"]
        self.controller.invert_y = _SETTINGS["invert_y"]
        self.controller.invert_x = _SETTINGS["invert_x"]
        self._saved_camera = view.getCamera()
        self._saved_type = view.getCameraType()
        self._timer = QtCore.QTimer()
        self._timer.setInterval(int(round(1000.0 * kin.TICK_INTERVAL)))
        self._timer.timeout.connect(self._tick)
        self._last_t = time.monotonic()

    def start(self):
        self.view.setCameraType(1)  # perspective (0 = orthographic)
        self.view.addEventCallback("SoEvent", self._on_event)
        self._start_input_capture()
        self._last_t = time.monotonic()
        self._timer.start()
        self._apply_camera()
        FreeCAD.Console.PrintMessage(ACTIVE_HINT + "\n")

    def stop(self):
        global _MODE
        if _MODE is not self:
            return
        self._stop_input_capture()
        try:
            self.view.removeEventCallback("SoEvent", self._on_event)
        except Exception:
            pass  # view already gone
        try:
            FreeCADGui.Control.closeDialog()
        except Exception:
            pass  # no task dialog open
        try:
            self.view.setCamera(self._saved_camera)
            self.view.setCameraType(self._saved_type)
        except Exception:
            pass  # view already gone
        _MODE = None
        FreeCAD.Console.PrintMessage("ArchPlus Walk Through: exited.\n")

    def _on_event(self, ev):
        try:
            self.controller.on_event(ev)
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)

    def _start_input_capture(self):
        """Route 3D-view events through the scene graph and swallow them.

        The viewer's normal dispatch hands EVERY event straight to the
        navigation style, bypassing scene-graph callbacks entirely
        (View3DInventorViewer::processSoEvent) — walk input would never
        arrive and the native orbit would fight the per-tick camera
        rewrite. With event redirection enabled, our scene-level
        SoEventCallback node marks every event handled: the input callback
        above receives the full mouse stream (buttons, motion, wheel), and
        the navigation style is never triggered while walking.
        """
        from pivy import coin

        viewer = self.view.getViewer()
        self._saved_redir = viewer.isRedirectedToSceneGraph()
        viewer.setRedirectToSceneGraph(True)
        self._swallow = coin.SoEventCallback()
        self._swallow.addEventCallback(
            coin.SoEvent.getClassTypeId(), self._swallow_event)
        viewer.getSceneGraph().addChild(self._swallow)

    def _swallow_event(self, userdata, node):
        """Scene-graph callback: mark every event handled while walking.

        Fires AFTER the input-recording callback (the viewer's own event
        node sits earlier in the traversal), so marking the event handled
        only stops the navigation style from reacting to it.
        """
        node.setHandled()

    def _stop_input_capture(self):
        try:
            self.view.getViewer().getSceneGraph().removeChild(self._swallow)
        except Exception:
            pass  # view/scene already gone
        try:
            self.view.getViewer().setRedirectToSceneGraph(self._saved_redir)
        except Exception:
            pass  # view already gone
        self._swallow = None

    def _tick(self):
        if _MODE is not self:
            # A zombie: _start_walk replaced this session but its timer
            # kept running and kept rewriting the camera, which made the
            # walk impossible to exit. Only the registered session lives.
            self._teardown_only()
            return
        now = time.monotonic()
        dt = min(now - self._last_t, kin.DT_MAX)
        self._last_t = now
        try:
            x, y, z = self.controller.position
            info = self.view.getObjectInfoRay(
                FreeCAD.Vector(x, y, z), FreeCAD.Vector(0, 0, -1))
            ground = info["PickedPoint"].z if info else None
            self.controller.advance(dt, ground)
            self._apply_camera()
        except RuntimeError:
            # The view wrapper died (document closed / workbench switch).
            self._teardown_only()
    def _teardown_only(self):
        """Stop the mode WITHOUT touching the (possibly dead) view."""
        self._timer.stop()
        global _MODE
        if _MODE is self:
            _MODE = None
        FreeCAD.Console.PrintMessage("ArchPlus Walk Through: exited.\n")

    def _apply_camera(self):
        from pivy import coin

        x, y, z = self.controller.position
        dx, dy, dz = kin.look_direction(self.controller.yaw,
                                        self.controller.pitch)
        cam = self.view.getCameraNode()
        cam.position.setValue(x, y, z)
        cam.pointAt(coin.SbVec3f(x + dx * 1000.0,
                                 y + dy * 1000.0,
                                 z + dz * 1000.0),
                    coin.SbVec3f(0.0, 0.0, 1.0))


class _WalkPickFilter(QtCore.QObject):
    """Application-level pick capture for placement (replaces Draft's Snapper).

    Draft's Snapper projects the cursor ray onto the working plane
    unconditionally (getApparentPoint), pinning every pick to the plane's
    height — after placing doors on floor 1, a click on the 2nd-floor slab
    lands at floor-1 height. This filter instead reads the TRUE scene hit
    under the cursor (ActiveView.getObjectInfo) on every move, drives the
    human preview with it, and starts the walk on left click. One-shot:
    the first left click wins, so double-clicks cannot start two walks.
    """

    def __init__(self, view, human, on_move, on_place):
        super().__init__()
        self._view = view
        self._human = human
        self._on_move = on_move
        self._on_place = on_place
        self._done = False
        self._viewer = _find_viewer_widget()

    def resume(self):
        """Re-arm after a click that did not hit geometry."""
        self._done = False

    def cancel(self):
        """Stop aiming: hide the human figure and ignore further input."""
        self._done = True
        self._human.off()

    def _aimed(self, obj):
        return (obj is self._viewer
                or (isinstance(obj, QtGui.QWidget)
                    and obj.parentWidget() is self._viewer))

    def eventFilter(self, obj, event):
        t = event.type()
        if t == QtCore.QEvent.MouseMove and self._aimed(obj) and not self._done:
            self._on_move(int(event.position().x()),
                          int(event.position().y()))
            return False           # observe only: FreeCAD keeps the cursor
        if (t == QtCore.QEvent.MouseButtonPress
                and event.button() == QtCore.Qt.LeftButton
                and self._aimed(obj)):
            done = self._done
            self._done = True
            self._human.off()
            self._on_place(int(event.position().x()),
                           int(event.position().y()))
            return True            # consumed: no selection drag
        return False


class _HumanPreview:
    """Basic standing figure shown at the pick cursor during placement.

    Plain Coin primitives (cylinder body, sphere head), marked unpickable
    so it never interferes with the scene pick; attached to the scene
    graph while picking and removed when the walk starts or is cancelled.
    Each limb group uses its own SoTransformSeparator — Coin transforms
    accumulate inside one separator, which used to fling the head away
    from the body.
    """

    def __init__(self, view):
        from pivy import coin

        self._view = view
        self._attached = False
        self._root = coin.SoSeparator()
        pick = coin.SoPickStyle()
        pick.style.setValue(coin.SoPickStyle.UNPICKABLE)
        self._root.addChild(pick)
        mat = coin.SoMaterial()
        mat.diffuseColor.setValue(0.10, 0.37, 0.71)   # the tool icon's blue
        self._root.addChild(mat)
        self._base = coin.SoTransform()
        self._root.addChild(self._base)

        body = coin.SoTransformSeparator()
        rot = coin.SoTransform()
        rot.rotation.setValue(coin.SbVec3f(1.0, 0.0, 0.0), math.pi / 2)
        lift = coin.SoTransform()
        lift.translation.setValue(0.0, 0.0, 600.0)
        body.addChild(rot)
        body.addChild(lift)
        cyl = coin.SoCylinder()
        cyl.radius.setValue(160.0)
        cyl.height.setValue(1200.0)
        body.addChild(cyl)
        self._root.addChild(body)

        head = coin.SoTransformSeparator()
        at = coin.SoTransform()
        at.translation.setValue(0.0, 0.0, 1340.0)
        head.addChild(at)
        headSphere = coin.SoSphere()
        headSphere.radius.setValue(140.0)
        head.addChild(headSphere)
        self._root.addChild(head)

    def on(self):
        if not self._attached:
            self._view.getSceneGraph().addChild(self._root)
            self._attached = True

    def off(self):
        if self._attached:
            try:
                self._view.getSceneGraph().removeChild(self._root)
            except Exception:
                pass  # scene already gone
            self._attached = False

    def move(self, point):
        self._base.translation.setValue(point.x, point.y, point.z)


class WalkTaskPanel:
    """Docked panel shown while walking.

    Person height and mouse inversion apply live; the control legend
    doubles as the documentation. No OK/Cancel: FreeCAD's close (X)
    and the Exit button both end the walk.
    """

    def __init__(self, session):
        self._session = session
        self.form = QtGui.QWidget()
        self.form.setWindowTitle("Walk Through")
        outer = QtGui.QVBoxLayout(self.form)

        person = QtGui.QGroupBox("Person")
        pform = QtGui.QFormLayout(person)
        self.height = QtGui.QDoubleSpinBox()
        self.height.setRange(500.0, 2500.0)
        self.height.setDecimals(0)
        self.height.setSuffix(" mm")
        self.height.setValue(_SETTINGS["eye_height"])
        self.height.setToolTip(
            "Eye height above the ground. Applies to the ground snap "
            "immediately and to the next placement pick.")
        pform.addRow("Person height", self.height)
        outer.addWidget(person)

        mouse = QtGui.QGroupBox("Mouse")
        mform = QtGui.QFormLayout(mouse)
        self.invertY = QtGui.QCheckBox(
            "Invert up/down (drag up looks down)")
        self.invertY.setChecked(_SETTINGS["invert_y"])
        self.invertX = QtGui.QCheckBox("Invert left/right")
        self.invertX.setChecked(_SETTINGS["invert_x"])
        mform.addRow(self.invertY)
        mform.addRow(self.invertX)
        outer.addWidget(mouse)

        controls = QtGui.QLabel(
            "<b>Wheel</b> step forward/back along the view heading<br>"
            "<b>Hold Right-mouse + move</b> look around<br>"
            "<b>Click the tool again</b> or <b>Exit</b> stop the walk")
        controls.setWordWrap(True)
        outer.addWidget(controls)

        self.exitBtn = QtGui.QPushButton("Exit walk")
        self.exitBtn.clicked.connect(self._exit)
        outer.addWidget(self.exitBtn)

        self.height.valueChanged.connect(self._on_height)
        self.invertY.toggled.connect(self._on_invert_y)
        self.invertX.toggled.connect(self._on_invert_x)

    def _apply(self):
        if self._session is not None:
            self._session.controller.eye_height = _SETTINGS["eye_height"]
            self._session.controller.invert_y = _SETTINGS["invert_y"]
            self._session.controller.invert_x = _SETTINGS["invert_x"]

    def _on_height(self, value):
        _SETTINGS["eye_height"] = float(value)
        self._apply()

    def _on_invert_y(self, checked):
        _SETTINGS["invert_y"] = bool(checked)
        self._apply()

    def _on_invert_x(self, checked):
        _SETTINGS["invert_x"] = bool(checked)
        self._apply()

    def _exit(self):
        if _MODE is not None:
            _MODE.stop()

    def accept(self):
        self._exit()
        return True

    def reject(self):
        self._exit()
        return True

    def getStandardButtons(self):
        return 0  # no OK/Cancel; the panel carries its own Exit button


def _face_normal(face_obj, point):
    """Normal of the picked face ([obj, face_index]) at `point`, or None."""
    if face_obj is None:
        return None
    obj, fi = face_obj
    try:
        face = obj.Shape.Faces[fi]
        u, v = face.Surface.parameter(FreeCAD.Vector(point))
        return face.normalAt(u, v)
    except Exception:
        return None


def _start_walk(view, point, face):
    """Start the session with the eye at `point` + eye height along normal.

    Stops any session still running first (re-entrant activation), then
    locks the ground at the implied feet level (click z - eye height): on
    a storey whose slab does not exist under the click, the down-ray
    would otherwise find the floor one storey below and drop the eye.
    """
    global _MODE
    if _MODE is not None:
        _MODE.stop()
    normal = _face_normal(face, point)
    if normal is None:
        normal = FreeCAD.Vector(0, 0, 1)
    if normal.Length > 0:
        normal.normalize()
    eye_height = _SETTINGS["eye_height"]
    eye = FreeCAD.Vector(point) + normal * eye_height
    # Keep the current heading: yaw from the view direction, pitch level.
    d = view.getViewDirection()
    yaw = math.atan2(d[0], d[1])
    _MODE = WalkSession(view, (eye.x, eye.y, eye.z), yaw=yaw)
    _MODE.controller.ground_level = point.z - eye_height
    _MODE.start()
    QtCore.QTimer.singleShot(0, _show_panel)


def _show_panel():
    """Show the walk task panel (deferred: FreeCAD schedules dialogs)."""
    if _MODE is None:
        return
    try:
        FreeCADGui.Control.showDialog(WalkTaskPanel(_MODE))
    except Exception as exc:
        FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)


def _cancel_pick():
    global _PICK
    if _PICK is not None:
        _PICK.cancel()
        try:
            QtGui.QApplication.instance().removeEventFilter(_PICK)
        except Exception:
            pass  # app already gone
        _PICK = None


class WalkThroughCommand:
    """Toolbar/menu command: toggles the walk mode."""

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Walk Through",
                "ToolTip": ("First-person walk: click a point to place your "
                            "eyes, wheel to move, hold right-mouse to look")}

    def IsActive(self):
        window = FreeCADGui.getMainWindow().getActiveWindow()
        return hasattr(window, "getSceneGraph")

    def Activated(self):
        global _PICK
        if _MODE is not None:
            _MODE.stop()
            return
        if _PICK is not None:
            _cancel_pick()
            FreeCAD.Console.PrintMessage(
                "ArchPlus Walk Through: placement cancelled.\n")
            return
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "ArchPlus Walk Through: no active document.\n")
            return
        gui_doc = FreeCADGui.ActiveDocument
        view = gui_doc.ActiveView if gui_doc is not None else None
        if view is None or not hasattr(view, "getObjectInfo"):
            FreeCAD.Console.PrintError(
                "ArchPlus Walk Through: no active 3D view.\n")
            return

        doc = FreeCAD.ActiveDocument
        picked = {"face": None}
        human = _HumanPreview(view)
        human.on()

        def face_from(info):
            if info and "Face" in info.get("Component", ""):
                o = doc.getObject(info["Object"])
                try:
                    fi = int(info["Component"][4:]) - 1
                except (ValueError, IndexError):
                    return None
                return [o, fi]
            return None

        def point_from(info):
            # getObjectInfo reports the hit as separate x/y/z values.
            return FreeCAD.Vector(info["x"], info["y"], info["z"])

        def on_move(x, y):
            info = view.getObjectInfo((x, y))
            if info:
                human.move(point_from(info))
                picked["face"] = face_from(info)

        def on_place(x, y):
            info = view.getObjectInfo((x, y))
            if info is None:
                # Clicked empty space (or the NaviCube): keep aiming.
                FreeCAD.Console.PrintMessage(
                    "ArchPlus Walk Through: no geometry there — keep "
                    "aiming.\n")
                _PICK.resume()
                return
            _cancel_pick()
            _start_walk(view, point_from(info), face_from(info))

        FreeCAD.Console.PrintMessage(PICK_HINT + "\n")
        _PICK = _WalkPickFilter(view, human, on_move, on_place)
        QtGui.QApplication.instance().installEventFilter(_PICK)


# Register (FreeCAD 1.1 has no removeCommand; guard to stay reload-safe,
# same as ArchPlus_Doors).
if "ArchPlus_WalkThrough" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_WalkThrough", WalkThroughCommand())
