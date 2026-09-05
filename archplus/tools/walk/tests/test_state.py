# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless tests for the Walk Through controller (event dicts -> pose)."""

import math

import pytest

from archplus.tools.walk import kinematics as kin
from archplus.tools.walk import state


def motion(x, y):
    return {"Type": "SoLocation2Event", "Position": (x, y)}


def button(st, btn="BUTTON3"):
    return {"Type": "SoMouseButtonEvent", "Button": btn, "State": st}


def wheel(delta):
    return {"Type": "SoMouseWheelEvent", "Delta": delta}


def test_wheel_steps_walk_forward_along_heading():
    c = state.WalkController((0.0, 0.0, 1650.0))
    for _ in range(3):                 # one notch (Delta 1) per event/tick
        c.on_event(wheel(1))
        c.advance(0.03)
    assert c.position[:2] == pytest.approx((0.0, 3 * kin.WHEEL_STEP))
    assert c.position[2] == pytest.approx(1650.0)


def test_wheel_back_steps_toward_view():
    c = state.WalkController((0.0, 0.0, 1650.0))
    for _ in range(2):
        c.on_event(wheel(-1))
        c.advance(0.03)
    assert c.position[1] == pytest.approx(-2 * kin.WHEEL_STEP)


def test_wheel_accumulates_and_respects_clamp():
    # A fast scroll piles up notches between ticks; the per-tick
    # displacement clamp still bounds the step.
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(wheel(10))
    c.advance(0.03)
    assert c.position[1] == pytest.approx(kin.MAX_STEP)


def test_wheel_walks_along_current_yaw():
    c = state.WalkController((0.0, 0.0, 1650.0), yaw=0.0)
    c.yaw = -0.63                      # as after a look drag
    c.on_event(wheel(1))
    c.advance(0.03)
    x, y = c.position[:2]
    assert x == pytest.approx(math.sin(-0.63) * kin.WHEEL_STEP, abs=1e-6)
    assert y == pytest.approx(math.cos(-0.63) * kin.WHEEL_STEP, abs=1e-6)


def test_rmb_drag_right_and_up():
    # Defaults (invert_y=True, invert_x=False): drag right turns right,
    # drag up looks DOWN — the user-requested inverted vertical.
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(100, 100))
    c.on_event(motion(200, 50))
    c.advance(0.03)
    assert c.yaw == pytest.approx(100 * kin.LOOK_SENS)
    assert c.pitch == pytest.approx(-50 * kin.LOOK_SENS)


def test_invert_toggles_restore_standard_directions():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.invert_y = False
    c.invert_x = True
    c.on_event(button("DOWN"))
    c.on_event(motion(100, 100))
    c.on_event(motion(200, 50))
    c.advance(0.03)
    assert c.yaw == pytest.approx(-100 * kin.LOOK_SENS)   # invert_x: drag right looks left
    assert c.pitch == pytest.approx(50 * kin.LOOK_SENS)   # standard: drag up looks up


def test_drag_without_rmb_does_not_look():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(motion(100, 100))
    c.on_event(motion(300, 40))
    c.advance(0.03)
    assert c.yaw == 0.0
    assert c.pitch == 0.0


def test_released_rmb_leaves_no_stale_jump():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(0, 0))
    c.on_event(motion(500, 0))
    c.on_event(button("UP"))
    c.on_event(motion(900, 0))     # moves while not looking: ignored
    c.on_event(button("DOWN"))
    c.advance(0.03)
    assert c.yaw == 0.0


def test_hover_before_rmb_press_does_not_jump():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(motion(100, 100))
    c.on_event(motion(300, 40))          # hover while not looking
    c.on_event(button("DOWN"))
    c.on_event(motion(360, 40))          # first drag after the press
    c.advance(0.03)
    assert c.yaw == pytest.approx(60 * kin.LOOK_SENS)
    assert c.pitch == 0.0


def test_pitch_clamped_at_limit():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(0, 0))
    c.on_event(motion(0, 100000))
    c.advance(0.03)
    assert c.pitch == pytest.approx(kin.PITCH_LIMIT)


def test_ground_snap_rides_stairs():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.advance(0.03, ground_z=170.0)
    assert c.position[2] == pytest.approx(1820.0)


def test_ground_none_holds_height():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.advance(0.03, ground_z=None)
    assert c.position[2] == pytest.approx(1650.0)


def test_ground_outside_tolerance_holds_height():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.advance(0.03, ground_z=-5000.0)
    assert c.position[2] == pytest.approx(1650.0)


def test_eye_height_parameter_sets_snap_target():
    c = state.WalkController((0.0, 0.0, 1500.0))
    c.eye_height = 1000.0
    c.advance(0.03, ground_z=500.0)
    assert c.position[2] == pytest.approx(1500.0)


def test_ground_lock_holds_storey_without_slab():
    # Clicked a storey-2 wall face at z=3500 (eye lands there); gui locks
    # the ground at the implied feet level 1850. The down-ray finds the
    # floor-1 slab at z=200 — far below, so the eye holds instead of
    # snapping down to the first floor.
    c = state.WalkController((0.0, 0.0, 3500.0))
    c.ground_level = 1850.0
    c.advance(0.03, ground_z=200.0)
    assert c.position[2] == pytest.approx(3500.0)
    assert c.ground_level == 1850.0


def test_ground_lock_releases_when_geometry_reaches_the_level():
    # Floor pick at 2800: lock = 2800 - 1650 = 1150; the down-ray hit is
    # the slab top itself, so the lock releases immediately and normal
    # following keeps the eye at hit + eye height.
    c = state.WalkController((0.0, 0.0, 4450.0))
    c.ground_level = 1150.0
    c.advance(0.03, ground_z=2800.0)
    assert c.ground_level is None
    assert c.position[2] == pytest.approx(4450.0)
