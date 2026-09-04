# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless tests for the Walk Through controller (event dicts -> pose)."""

import pytest

from archplus.tools.walk import kinematics as kin
from archplus.tools.walk import state


def key(k, st="DOWN"):
    return {"Type": "SoKeyboardEvent", "Key": k, "State": st}


def motion(x, y):
    return {"Type": "SoLocation2Event", "Position": (x, y)}


def button(st, btn="BUTTON3"):
    return {"Type": "SoMouseButtonEvent", "Button": btn, "State": st}


def test_wasd_forward_moves_toward_look_direction():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.advance(0.05)
    x, y, z = c.position
    assert (x, y) == pytest.approx((0.0, 70.0))
    assert z == pytest.approx(1650.0)


def test_uppercase_w_with_shift_runs_forward():
    # Reality model: Shift held -> printable char arrives uppercase AND
    # ShiftDown is set, so "W" + ShiftDown is run-speed forward.
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event({"Type": "SoKeyboardEvent", "Key": "W", "State": "DOWN",
                "ShiftDown": True})
    c.advance(0.05)
    assert c.position[1] == pytest.approx(225.0)


def test_arrow_key_is_forward():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("UP_ARROW"))
    c.advance(0.05)
    assert c.position[1] == pytest.approx(70.0)


def test_key_release_stops_motion():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.advance(0.05)
    c.on_event(key("w", "UP"))
    c.advance(0.05)
    assert c.position[1] == pytest.approx(70.0)


def test_arrow_turn_rotates_heading():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("RIGHT_ARROW"))
    c.advance(0.5)
    assert c.yaw == pytest.approx(0.5 * kin.TURN_SPEED)


def test_escape_sets_exit_flag_and_freezes_pose():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("ESCAPE"))
    assert c.exited is True
    c.advance(1.0)
    assert c.position == (0.0, 0.0, 1650.0)


def test_rmb_drag_right_and_up():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(button("DOWN"))
    c.on_event(motion(100, 100))
    c.on_event(motion(200, 50))
    c.advance(0.03)
    assert c.yaw == pytest.approx(100 * kin.LOOK_SENS)
    assert c.pitch == pytest.approx(50 * kin.LOOK_SENS)


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
    assert c.pitch == pytest.approx(-kin.PITCH_LIMIT)


def test_shift_down_runs():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.on_event({"Type": "SoKeyboardEvent", "Key": "SHIFT", "State": "DOWN",
                "ShiftDown": True})
    c.advance(0.05)
    assert c.position[1] == pytest.approx(225.0)


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


def test_max_step_clamped_in_advance():
    c = state.WalkController((0.0, 0.0, 1650.0))
    c.on_event(key("w"))
    c.advance(10.0)                # absurd dt must not teleport
    assert c.position[1] == pytest.approx(kin.MAX_STEP)
