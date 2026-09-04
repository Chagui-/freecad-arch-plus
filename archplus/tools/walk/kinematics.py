# SPDX-License-Identifier: LGPL-2.1-or-later
"""Pure math for the Walk Through mode.

Units are FreeCAD internal: millimetres (speeds in mm/s); angles are radians.
No FreeCAD/PySide/pivy imports here — everything must run headless under
pytest.

Conventions
-----------
yaw    0 looks toward +Y; increasing yaw turns right (clockwise seen from
       above: at yaw 90 deg the look direction is +X).
pitch  positive looks up; clamped to +-85 deg so `pointAt` can keep +Z up.
mouse  screen y grows downward, so dragging up (dy < 0) raises the pitch.
"""

import math

# Parameters — spec: docs/superpowers/specs/2026-09-04-walk-through-design.md
EYE_HEIGHT = 1650.0        # mm above the ground the eye sits
WALK_SPEED = 1400.0        # mm/s
RUN_SPEED = 4500.0         # mm/s
STEP_UP = 600.0            # max instant rise while following ground, mm
STEP_DOWN = 2000.0         # max instant drop while following ground, mm
MAX_STEP = 300.0           # max horizontal displacement per tick, mm
PITCH_LIMIT = math.radians(85.0)
TURN_SPEED = math.radians(120.0)  # rad/s for the arrow turn keys
LOOK_SENS = 0.0035         # rad per pixel of right-mouse drag
TICK_INTERVAL = 1.0 / 30.0  # s; the Qt timer period (30 Hz)
DT_MAX = 0.1               # s; clamp so a stall cannot teleport the camera
WHEEL_STEP = 300.0        # mm per wheel notch (mouse-only walking)

def look_direction(yaw, pitch):
    """Unit look direction (x, y, z) for a yaw/pitch pair."""
    c = math.cos(pitch)
    return (math.sin(yaw) * c, math.cos(yaw) * c, math.sin(pitch))


def clamp_pitch(pitch):
    """Clamp pitch to +-PITCH_LIMIT."""
    return max(-PITCH_LIMIT, min(PITCH_LIMIT, pitch))


def move_vector(active, yaw, run=False):
    """Horizontal world velocity (vx, vy) in mm/s for the held actions.

    `active` holds semantic actions: 'forward', 'back', 'left' (strafe),
    'right' (strafe). Running comes in as the `run` flag.
    """
    speed = RUN_SPEED if run else WALK_SPEED
    f = (1 if "forward" in active else 0) - (1 if "back" in active else 0)
    s = (1 if "right" in active else 0) - (1 if "left" in active else 0)
    d = math.hypot(f, s)
    if d > 0.0:
        f /= d
        s /= d
    vx = (f * math.sin(yaw) + s * math.cos(yaw)) * speed
    vy = (f * math.cos(yaw) - s * math.sin(yaw)) * speed
    return (vx, vy)


def clamp_step(dx, dy):
    """Limit one tick's horizontal displacement to MAX_STEP mm."""
    d = math.hypot(dx, dy)
    if d <= MAX_STEP or d == 0.0:
        return (dx, dy)
    k = MAX_STEP / d
    return (dx * k, dy * k)


def snap_target(eye_z, ground_z, eye_height=EYE_HEIGHT):
    """Eye z for a ground hit, or None when the snap must be refused.

    Refusal (keep the current height) covers walking off a ledge and any
    ground jump larger than the stair tolerances: the eye then holds its
    height instead of teleporting or sinking.
    """
    target = ground_z + eye_height
    rise = target - eye_z
    if rise > STEP_UP:
        return None
    if -rise > STEP_DOWN:
        return None
    return target


def turn_step(active, dt):
    """Yaw delta (rad) for one tick from the arrow turn keys."""
    t = ((1 if "turn_right" in active else 0)
         - (1 if "turn_left" in active else 0))
    return t * TURN_SPEED * dt
