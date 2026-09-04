# SPDX-License-Identifier: LGPL-2.1-or-later
"""Walk-mode state machine: input dicts in, camera pose out.

Pure Python — no FreeCAD/PySide/pivy imports. `on_event` consumes the event
dicts that `View3DInventorPy.addEventCallback("SoEvent", ...)` delivers
(Type/State/Key/Button/Position/ShiftDown — see src/Gui/View3DPy.cpp
eventCallback), and `advance` integrates one timer tick.

Keyboard letters arrive through FreeCAD's printable-character default
branch ("w", or "W" when Shift is held), so lookups normalize case; named
constants ("UP_ARROW", "ESCAPE") pass through unchanged. Shift is reported
as ShiftDown on every event and tracked regardless of event type.
"""

from . import kinematics as kin

KEYMAP = {
    "W": "forward", "UP_ARROW": "forward",
    "S": "back", "DOWN_ARROW": "back",
    "A": "left",
    "D": "right",
    "RIGHT_ARROW": "turn_right",
    "LEFT_ARROW": "turn_left",
}


class WalkController:
    """Holds the walking pose and converts events + ticks into motion."""

    def __init__(self, position, yaw=0.0, pitch=0.0):
        self.position = tuple(float(v) for v in position)  # (x, y, z) mm
        self.yaw = float(yaw)
        self.pitch = kin.clamp_pitch(float(pitch))
        self.active = set()       # semantic actions currently held
        self.run = False          # Shift held (from ShiftDown)
        self.looking = False      # right mouse button held
        self.exited = False       # set on Escape, read by the tick
        self._mdx = 0             # unconsumed mouse drag delta, px
        self._mdy = 0
        self._last_mouse = None   # last Location2 position, for deltas

    def on_event(self, ev):
        """Consume one event dict; never raises on unknown events."""
        etype = ev.get("Type")
        if etype == "SoKeyboardEvent":
            kstate = ev.get("State")
            key = ev.get("Key")
            if key == "ESCAPE":
                if kstate == "DOWN":
                    self.exited = True
            else:
                action = KEYMAP.get(str(key).upper()) if key else None
                if action is not None:
                    if kstate == "DOWN":
                        self.active.add(action)
                    elif kstate == "UP":
                        self.active.discard(action)
        elif etype == "SoMouseButtonEvent":
            if ev.get("Button") == "BUTTON3":
                self.looking = ev.get("State") == "DOWN"
                if not self.looking:
                    self._last_mouse = None
                    self._mdx = 0
                    self._mdy = 0
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
        # ShiftDown is carried on every event; track it regardless of type.
        self.run = bool(ev.get("ShiftDown"))

    def advance(self, dt, ground_z=None):
        """Integrate one tick (`dt` seconds, clamped by the caller).

        `ground_z` is the floor height under the eye from the down-ray pick,
        or None when nothing was hit / the snap was refused (height held).
        """
        if self.exited:
            return
        if self.looking:
            self.yaw += self._mdx * kin.LOOK_SENS
            self.pitch = kin.clamp_pitch(self.pitch - self._mdy * kin.LOOK_SENS)
        self._mdx = 0
        self._mdy = 0
        self.yaw += kin.turn_step(self.active, dt)
        vx, vy = kin.move_vector(self.active, self.yaw, self.run)
        dx, dy = kin.clamp_step(vx * dt, vy * dt)
        x, y, z = self.position
        x += dx
        y += dy
        if ground_z is not None:
            target = kin.snap_target(z, ground_z)
            if target is not None:
                z = target
        self.position = (x, y, z)
