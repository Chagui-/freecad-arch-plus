# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk Through — interactive first-person walk mode (ArchPlus).

Click the tool, click a point on 3D geometry to place your eyes (point +
1.65 m along the picked face normal), then walk: WASD/arrows move, hold the
right mouse button and move to look, Shift runs, Esc (or clicking the tool
again) exits and restores the saved camera.

Input capture: the viewer's normal dispatch routes every event except ESC/Q
keys straight to the navigation style, so walk mode enables the viewer's
scene-graph event redirection and swallows events on a scene-level
SoEventCallback node — the input callback sees the full stream and native
orbit/zoom never fight the per-tick camera rewrite (see
_start_input_capture). The tick still integrates the pose and rewrites the
Coin camera each frame; the ground under the eye is found with
ActiveView.getObjectInfoRay() (a vertical down-ray), so the eye rides
floors and stairs.
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

_MODE = None  # the active WalkSession, or None

PICK_HINT = ("ArchPlus Walk Through: click a point in the 3D view to start "
             "walking.")
ACTIVE_HINT = ("ArchPlus Walk Through: WASD/arrows or wheel to move, hold "
               "right-mouse to look, Shift run, Esc exit.")

# Live settings, shared between the task panel and every session in this
# FreeCAD run. Defaults honour the user's tested preferences.
_SETTINGS = {"eye_height": 1650.0, "invert_y": True, "invert_x": False}


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
        self._key_filter = None
        self._key_filter_widget = None

    def start(self):
        self.view.setCameraType(1)  # perspective (0 = orthographic)
        self.view.addEventCallback("SoEvent", self._on_event)
        self._start_input_capture()
        self._install_key_filter()
        self._last_t = time.monotonic()
        self._timer.start()
        self._apply_camera()
        FreeCAD.Console.PrintMessage(ACTIVE_HINT + "\n")

    def stop(self):
        global _MODE
        if _MODE is not self:
            return
        self._stop_input_capture()
        self._remove_key_filter()
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
            if self.controller.exited:
                # Removing the callback from inside its own callback is not
                # safe; defer the teardown to the next event-loop pass.
                QtCore.QTimer.singleShot(0, self.stop)
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)
            self.controller.exited = True
            QtCore.QTimer.singleShot(0, self.stop)

    def _start_input_capture(self):
        """Route 3D-view events through the scene graph and swallow them.

        The viewer's normal dispatch hands EVERY event except ESC/Q keys
        straight to the navigation style, bypassing scene-graph callbacks
        entirely (View3DInventorViewer::processSoEvent) — walk input would
        never arrive and the native orbit would fight the per-tick camera
        rewrite. With event redirection enabled, our scene-level
        SoEventCallback node marks every event handled: the input callback
        above receives the full stream (keys, Shift, mouse), and the
        navigation style is never triggered while walking.
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

    def qt_key(self, event, state):
        """Feed one Qt key event to the controller as a FreeCAD-style dict.

        Returns True when the key belongs to the walk mode (the filter must
        consume it), False when FreeCAD should handle it normally.
        """
        key = _WalkKeyFilter._KEYS.get(event.key())
        if key is None:
            return False
        self.controller.on_event({
            "Type": "SoKeyboardEvent", "Key": key, "State": state,
            "ShiftDown": bool(event.modifiers() & QtCore.Qt.ShiftModifier),
        })
        if self.controller.exited:
            QtCore.QTimer.singleShot(0, self.stop)
        return True

    def _install_key_filter(self):
        """Capture keyboard at the APPLICATION level while walking.

        A FreeCAD application filter consumes plain key presses before any
        per-widget filter or the 3D view can react (verified live: a probe
        on the viewer widget never saw KeyPress). Our application-level
        filter is called before that one, so it sees and consumes mapped
        keys first — scoped to the walked view only.
        """
        self._key_filter_widget = self._find_viewer_widget()
        if self._key_filter_widget is None:
            return
        self._key_filter = _WalkKeyFilter(self, self._key_filter_widget)
        QtGui.QApplication.instance().installEventFilter(self._key_filter)

    @staticmethod
    def _find_viewer_widget():
        best = None
        for w in QtGui.QApplication.allWidgets():
            if (w.isVisible()
                    and w.metaObject().className() == "Gui::View3DInventorViewer"):
                if (best is None
                        or w.width() * w.height() > best.width() * best.height()):
                    best = w
        return best

    def _remove_key_filter(self):
        if self._key_filter is not None:
            try:
                QtGui.QApplication.instance().removeEventFilter(self._key_filter)
            except Exception:
                pass  # app already gone
        self._key_filter = None
        self._key_filter_widget = None
    @staticmethod
    def _find_viewer_widget():
        best = None
        for w in QtGui.QApplication.allWidgets():
            if (w.isVisible()
                    and w.metaObject().className() == "Gui::View3DInventorViewer"):
                if (best is None
                        or w.width() * w.height() > best.width() * best.height()):
                    best = w
        return best


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
        now = time.monotonic()
        dt = min(now - self._last_t, kin.DT_MAX)
        self._last_t = now
        try:
            x, y, z = self.controller.position
            info = self.view.getObjectInfoRay(
                FreeCAD.Vector(x, y, z), FreeCAD.Vector(0, 0, -1))
            ground = info["PickedPoint"].z if info else None
            self.controller.advance(dt, ground)
            if self.controller.exited:
                self.stop()
                return
            self._apply_camera()
        except RuntimeError:
            # The view wrapper died (document closed / workbench switch).
            self._teardown_only()
        except Exception as exc:
            FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)
            self.stop()

    def _teardown_only(self):
        """Stop the mode WITHOUT touching the (possibly dead) view."""
        self._timer.stop()
        global _MODE
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


class _WalkKeyFilter(QtCore.QObject):
    """Application-level keyboard capture for walk mode.

    A FreeCAD application filter consumes plain key presses before any
    per-widget filter or the 3D view can react (verified live: a probe
    installed on the viewer widget never sees KeyPress). Installing ours
    at the application level puts it in front; it acts ONLY on keys aimed
    at the walked view's widgets while walk mode is active, so the rest of
    the application behaves exactly as before.
    """

    _KEYS = {
        QtCore.Qt.Key_W: "W", QtCore.Qt.Key_S: "S",
        QtCore.Qt.Key_A: "A", QtCore.Qt.Key_D: "D",
        QtCore.Qt.Key_Up: "UP_ARROW", QtCore.Qt.Key_Down: "DOWN_ARROW",
        QtCore.Qt.Key_Left: "LEFT_ARROW",
        QtCore.Qt.Key_Right: "RIGHT_ARROW",
    }

    def __init__(self, session, viewer_widget):
        super().__init__()
        self._session = session
        self._viewer_widget = viewer_widget

    def eventFilter(self, obj, event):
        session = self._session
        if session is None or session.controller.exited:
            return False
        etype = event.type()
        if etype not in (QtCore.QEvent.KeyPress, QtCore.QEvent.KeyRelease):
            return False
        # Only keys aimed at the walked view (the viewer widget, its GL
        # canvas child, or the focus holder); the whole rest of the app
        # passes through untouched. Native delivery may target a bare
        # QWindow or other non-widget object — treat anything that is not
        # a widget as not-ours instead of crashing on it.
        try:
            aimed = (obj is self._viewer_widget
                     or (isinstance(obj, QtGui.QWidget)
                         and obj.parentWidget() is self._viewer_widget)
                     or QtGui.QApplication.focusWidget() is self._viewer_widget)
        except Exception:
            aimed = False
        if not aimed:
            return False
        if event.isAutoRepeat():
            return True            # held-key repeats must not toggle state
        state = "DOWN" if etype == QtCore.QEvent.KeyPress else "UP"
        return session.qt_key(event, state)


class _HumanPreview:
    """Basic standing figure shown at the pick cursor during placement.

    Plain Coin primitives (cylinder body, sphere head), marked unpickable
    so it never interferes with the Snapper pick; attached to the scene
    graph while picking and removed when the walk starts or is cancelled.
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
        body = coin.SoTransform()
        body.translation.setValue(0.0, 0.0, 600.0)
        body.rotation.setValue(coin.SbVec3f(1.0, 0.0, 0.0), math.pi / 2)
        cyl = coin.SoCylinder()
        cyl.radius.setValue(160.0)
        cyl.height.setValue(1200.0)
        head = coin.SoTransform()
        head.translation.setValue(0.0, 0.0, 1340.0)
        headSphere = coin.SoSphere()
        headSphere.radius.setValue(140.0)
        self._root.addChild(body)
        self._root.addChild(cyl)
        self._root.addChild(head)
        self._root.addChild(headSphere)

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
    doubles as the documentation. No OK/Cancel: FreeCAD's close (X or Esc)
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
            "<b>W/S</b> or <b>Up/Down</b> forward/back · <b>A/D</b> strafe ·"
            " <b>Left/Right</b> turn<br>"
            "<b>Hold Right-mouse + move</b> look · <b>Wheel</b> step "
            "forward/back<br><b>Shift</b> run · <b>Esc</b> exit")
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

    The ground is locked to the implied feet level (click z - eye height):
    on a storey whose slab does not exist under the click, the down-ray
    would otherwise find the floor one storey below and drop the eye.
    """
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
    global _MODE
    _MODE = WalkSession(view, (eye.x, eye.y, eye.z), yaw=yaw)
    _MODE.controller.ground_level = point.z - eye_height
    _MODE.start()
    QtCore.QTimer.singleShot(0, _show_panel)


def _show_panel():
    """Show the walk task panel (deferred: never inside a Snapper callback)."""
    if _MODE is None:
        return
    try:
        FreeCADGui.Control.showDialog(WalkTaskPanel(_MODE))
    except Exception as exc:
        FreeCAD.Console.PrintError("ArchPlus Walk Through: %s\n" % exc)


class WalkThroughCommand:
    """Toolbar/menu command: toggles the walk mode."""

    def GetResources(self):
        return {"Pixmap": ICON,
                "MenuText": "Walk Through",
                "ToolTip": ("First-person walk: click a point to place your "
                            "eyes, WASD to move, hold right-mouse to look, "
                            "Esc to exit")}

    def IsActive(self):
        window = FreeCADGui.getMainWindow().getActiveWindow()
        return hasattr(window, "getSceneGraph")

    def Activated(self):
        if _MODE is not None:
            _MODE.stop()
            return
        if FreeCAD.ActiveDocument is None:
            FreeCAD.Console.PrintError(
                "ArchPlus Walk Through: no active document.\n")
            return
        gui_doc = FreeCADGui.ActiveDocument
        view = gui_doc.ActiveView if gui_doc is not None else None
        if view is None or not hasattr(view, "getObjectInfoRay"):
            FreeCAD.Console.PrintError(
                "ArchPlus Walk Through: no active 3D view.\n")
            return

        doc = FreeCAD.ActiveDocument
        picked = {"face": None}
        human = _HumanPreview(view)
        human.on()
        # The Draft Snapper projects picks onto the working plane and snaps
        # to vertices/grid — after placing doors on floor 1 the plane sits
        # there, so a click on the 2nd-floor slab would come back at
        # floor-1 height. For walk placement the raw cursor ray is the
        # semantic you want: aim where you click. Save and restore the
        # user's snap modes around the pick.
        snapper = FreeCADGui.Snapper
        saved_snaps = list(snapper.active_snaps)
        snapper.active_snaps = []

        def _move(point, info):
            if info and "Face" in info.get("Component", ""):
                o = doc.getObject(info["Object"])
                try:
                    fi = int(info["Component"][4:]) - 1
                except (ValueError, IndexError):
                    picked["face"] = None
                else:
                    picked["face"] = [o, fi]
            else:
                picked["face"] = None
            if point is not None:
                human.move(point)

        def _place(point=None, obj=None):
            FreeCADGui.Snapper.off()
            snapper.active_snaps = saved_snaps
            human.off()
            if point is None:
                return  # cancelled
            _start_walk(view, point, picked["face"])

        FreeCAD.Console.PrintMessage(PICK_HINT + "\n")
        FreeCADGui.Snapper.getPoint(callback=_place, movecallback=_move)


# Register (FreeCAD 1.1 has no removeCommand; guard to stay reload-safe,
# same as ArchPlus_Doors).
if "ArchPlus_WalkThrough" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_WalkThrough", WalkThroughCommand())
