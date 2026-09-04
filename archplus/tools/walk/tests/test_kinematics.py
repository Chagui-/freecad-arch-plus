# SPDX-License-Identifier: LGPL-2.1-or-later
"""Headless tests for the Walk Through kinematics (pure math, mm + radians)."""

import math

import pytest

from archplus.tools.walk import kinematics as kin


def test_look_direction_yaw_zero_faces_plus_y():
    d = kin.look_direction(0.0, 0.0)
    assert d == pytest.approx((0.0, 1.0, 0.0))


def test_look_direction_pitch_up_adds_z():
    d = kin.look_direction(0.0, math.pi / 2)
    assert d[2] == pytest.approx(1.0)


def test_clamp_pitch_bounds():
    assert kin.clamp_pitch(2.0) == pytest.approx(kin.PITCH_LIMIT)
    assert kin.clamp_pitch(-2.0) == pytest.approx(-kin.PITCH_LIMIT)
    assert kin.clamp_pitch(0.3) == pytest.approx(0.3)


def test_move_forward_at_yaw_zero_is_plus_y():
    vx, vy = kin.move_vector({"forward"}, 0.0)
    assert vx == pytest.approx(0.0)
    assert vy == pytest.approx(kin.WALK_SPEED)


def test_move_forward_at_yaw_90_faces_plus_x():
    vx, vy = kin.move_vector({"forward"}, math.pi / 2)
    assert vx == pytest.approx(kin.WALK_SPEED)
    assert vy == pytest.approx(0.0)


def test_strafe_right_at_yaw_zero_is_plus_x():
    vx, vy = kin.move_vector({"right"}, 0.0)
    assert vx == pytest.approx(kin.WALK_SPEED)
    assert vy == pytest.approx(0.0)


def test_back_is_minus_forward():
    vx, vy = kin.move_vector({"back"}, 0.0)
    assert vy == pytest.approx(-kin.WALK_SPEED)


def test_run_multiplies_speed():
    vx, vy = kin.move_vector({"forward"}, 0.0, run=True)
    assert vy == pytest.approx(kin.RUN_SPEED)


def test_diagonal_does_not_exceed_walk_speed():
    vx, vy = kin.move_vector({"forward", "right"}, 0.0)
    assert math.hypot(vx, vy) == pytest.approx(kin.WALK_SPEED)


def test_clamp_step_limits_displacement():
    dx, dy = kin.clamp_step(1000.0, 0.0)
    assert math.hypot(dx, dy) == pytest.approx(kin.MAX_STEP)


def test_clamp_step_passes_small_steps():
    assert kin.clamp_step(30.0, 40.0) == (30.0, 40.0)


def test_snap_target_is_stable_on_flat_ground():
    assert kin.snap_target(1650.0, 0.0) == pytest.approx(1650.0)


def test_snap_target_climbs_stair_riser():
    # ArchPlus stairs: ~170 mm riser up
    assert kin.snap_target(1650.0, 170.0) == pytest.approx(1820.0)


def test_snap_target_descends_stair_riser():
    assert kin.snap_target(1650.0, -170.0) == pytest.approx(1480.0)


def test_snap_target_refuses_big_rise():
    assert kin.snap_target(1650.0, 1000.0) is None


def test_snap_target_refuses_big_drop():
    assert kin.snap_target(1650.0, -5000.0) is None


def test_turn_step_directions():
    assert kin.turn_step({"turn_right"}, 1.0) == pytest.approx(kin.TURN_SPEED)
    assert kin.turn_step({"turn_left"}, 1.0) == pytest.approx(-kin.TURN_SPEED)
    assert kin.turn_step(set(), 1.0) == 0.0
