# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk Through — interactive first-person walk mode (ArchPlus).

Click the tool, click a point on 3D geometry to place your eyes (point +
1.65 m along the picked face normal), then walk: WASD/arrows move, hold the
right mouse button and move to look, Shift runs, Esc (or clicking the tool
again) exits and restores the saved camera.

Architecture: a per-view event callback only RECORDS input into a pure
WalkController (see state.py); a 30 Hz QTimer tick integrates the pose and
rewrites the Coin camera each frame — the tick's camera overwrite is what
masks FreeCAD's own right-mouse orbit while RMB is repurposed for looking.
The ground under the eye is found with ActiveView.getObjectInfoRay() (a
vertical down-ray), so the eye rides floors and stairs.
"""

import math
import time

import FreeCAD
import FreeCADGui
from PySide import QtCore

from . import kinematics as kin
from . import state as walk_state

_MODE = None  # the active WalkSession, or None

PICK_HINT = ("ArchPlus Walk Through: click a point in the 3D view to start "
             "walking.")
ACTIVE_HINT = ("ArchPlus Walk Through: WASD/arrows move, hold right-mouse "
               "to look, Shift run, Esc exit.")


class WalkSession:
    """One walk-mode session bound to one 3D view."""

    def __init__(self, view, eye, yaw, pitch=0.0):
        self.view = view
        self.controller = walk_state.WalkController(eye, yaw=yaw, pitch=pitch)
        self._saved_camera = view.getCamera()
        self._saved_type = view.getCameraType()
        self._timer = QtCore.QTimer()
        self._timer.setInterval(int(round(1000.0 * kin.TICK_INTERVAL)))
        self._timer.timeout.connect(self._tick)
        self._last_t = time.monotonic()

    def start(self):
        self.view.setCameraType(1)  # perspective (0 = orthographic)
        self.view.addEventCallback("SoEvent", self._on_event)
        self._last_t = time.monotonic()
        self._timer.start()
        self._apply_camera()
        FreeCAD.Console.PrintMessage(ACTIVE_HINT + "\n")

    def stop(self):
        self._timer.stop()
        try:
            self.view.removeEventCallback("SoEvent", self._on_event)
        except Exception:
            pass  # view already gone
        try:
            self.view.setCamera(self._saved_camera)
            self.view.setCameraType(self._saved_type)
        except Exception:
            pass  # view already gone
        global _MODE
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
            self._teardown_only()

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
    """Start the session with the eye at `point` + eye height along normal."""
    normal = _face_normal(face, point)
    if normal is None:
        normal = FreeCAD.Vector(0, 0, 1)
    if normal.Length > 0:
        normal.normalize()
    eye = FreeCAD.Vector(point) + normal * kin.EYE_HEIGHT
    # Keep the current heading: yaw from the view direction, pitch level.
    d = view.getViewDirection()
    yaw = math.atan2(d[0], d[1])
    global _MODE
    _MODE = WalkSession(view, (eye.x, eye.y, eye.z), yaw=yaw)
    _MODE.start()


class WalkThroughCommand:
    """Toolbar/menu command: toggles the walk mode."""

    def GetResources(self):
        return {"MenuText": "Walk Through",
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

        def _move(point, info):
            if info and "Face" in info.get("Component", ""):
                o = doc.getObject(info["Object"])
                try:
                    fi = int(info["Component"][4:]) - 1
                except (ValueError, IndexError):
                    picked["face"] = None
                else:
                    picked["face"] = [o, fi]

        def _place(point=None, obj=None):
            FreeCADGui.Snapper.off()
            if point is None:
                return  # cancelled
            _start_walk(view, point, picked["face"])

        FreeCAD.Console.PrintMessage(PICK_HINT + "\n")
        FreeCADGui.Snapper.getPoint(callback=_place, movecallback=_move)


# Register (FreeCAD 1.1 has no removeCommand; guard to stay reload-safe,
# same as ArchPlus_Doors).
if "ArchPlus_WalkThrough" not in FreeCADGui.listCommands():
    FreeCADGui.addCommand("ArchPlus_WalkThrough", WalkThroughCommand())
