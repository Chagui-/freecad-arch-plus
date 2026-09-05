# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk-mode state machine: input dicts in, camera pose out.

Pure Python — no FreeCAD/PySide/pivy imports. `on_event` consumes the event
dicts that `View3DInventorPy.addEventCallback("SoEvent", ...)` delivers
(Type/Button/Position — see src/Gui/View3DPy.cpp eventCallback), and
`advance` integrates one timer tick.

Movement is mouse-only (the user removed WASD): the mouse wheel steps
forward/back along the view heading, the right mouse button looks around.
The ground under the eye comes from the caller's down-ray pick; the ground
lock lets a storey without a slab keep the clicked level.
"""

import math

from . import kinematics as kin


class WalkController:
    """Holds the walking pose and converts events + ticks into motion."""

    def __init__(self, position, yaw=0.0, pitch=0.0):
        self.position = tuple(float(v) for v in position)  # (x, y, z) mm
        self.yaw = float(yaw)
        self.pitch = kin.clamp_pitch(float(pitch))
        self.looking = False      # right mouse button held
        self.eye_height = kin.EYE_HEIGHT   # live-settable from the panel
        self.invert_y = True      # drag up looks down (user preference)
        self.invert_x = False     # drag right looks right
        self.ground_level = None  # clicked level governs until real ground
        self._mdx = 0             # unconsumed mouse drag delta, px
        self._mdy = 0
        self._last_mouse = None   # last Location2 position, for deltas
        self._wheel = 0           # unconsumed wheel notches (mouse walking)

    def on_event(self, ev):
        """Consume one event dict; never raises on unknown events."""
        etype = ev.get("Type")
        if etype == "SoMouseButtonEvent":
            # Coin's mouse-button numbering is platform-dependent (the
            # right button is BUTTON2 on Windows, BUTTON3 on X11); during a
            # walk both mean "look" — pan and zoom are meaningless anyway.
            if ev.get("Button") in ("BUTTON2", "BUTTON3"):
                self.looking = ev.get("State") == "DOWN"
                if not self.looking:
                    self._last_mouse = None
                    self._mdx = 0
                    self._mdy = 0
        elif etype == "SoMouseWheelEvent":
            # Mouse-only walking: each notch steps forward/back along the
            # current view heading.
            delta = ev.get("Delta")
            if delta:
                self._wheel += 1 if delta > 0 else -1
        elif etype == "SoLocation2Event":
            pos = ev.get("Position")
            if not pos:
                return
            x, y = int(pos[0]), int(pos[1])
            # Accumulate drag deltas only while looking; still track the
            # position so a fresh RMB press starts measuring from where it
            # happened (no jump from hover movement before the press).
            if self.looking and self._last_mouse is not None:
                self._mdx += x - self._last_mouse[0]
                self._mdy += y - self._last_mouse[1]
            self._last_mouse = (x, y)

    def set_eye_height(self, mm):
        """Change the eye height and shift the eye so the feet stay put.

        The snap tolerances (STEP_UP/STEP_DOWN) are stair-sized, so a
        person-height change can exceed them and the snap would then
        refuse the target for as long as the person stands still. The
        shift applies immediately; later snaps use the new height.
        """
        delta = float(mm) - self.eye_height
        self.eye_height = float(mm)
        x, y, z = self.position
        self.position = (x, y, z + delta)


    def advance(self, dt, ground_z=None):
        """Integrate one tick (`dt` seconds, clamped by the caller).

        `ground_z` is the floor height under the eye from the down-ray pick,
        or None when nothing was hit / the snap was refused (height held).
        """
        if self.looking:
            yaw_dir = -1 if self.invert_x else 1
            pitch_dir = 1 if self.invert_y else -1
            self.yaw += yaw_dir * self._mdx * kin.LOOK_SENS
            self.pitch = kin.clamp_pitch(
                self.pitch + pitch_dir * self._mdy * kin.LOOK_SENS)
        self._mdx = 0
        self._mdy = 0
        # Mouse-only movement: wheel notches step along the view heading.
        wx = math.sin(self.yaw) * self._wheel * kin.WHEEL_STEP
        wy = math.cos(self.yaw) * self._wheel * kin.WHEEL_STEP
        self._wheel = 0
        dx, dy = kin.clamp_step(wx, wy)
        x, y, z = self.position
        x += dx
        y += dy
        if ground_z is not None:
            # A storey without a slab: the down-ray finds the floor one or
            # two storeys below the clicked level. The pick therefore locks
            # the ground at the implied feet level (click z - eye height);
            # while locked, snapping is refused, and the lock releases once
            # real geometry comes within one step of the implied level.
            if self.ground_level is not None:
                if ground_z >= self.ground_level - kin.STEP_UP:
                    self.ground_level = None
                else:
                    ground_z = None
            if ground_z is not None:
                target = kin.snap_target(z, ground_z, self.eye_height)
                if target is not None:
                    z = target
        self.position = (x, y, z)
