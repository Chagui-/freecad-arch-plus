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


def test_snap_target_uses_eye_height_parameter():
    assert kin.snap_target(1500.0, 500.0, eye_height=1000.0) == pytest.approx(1500.0)
