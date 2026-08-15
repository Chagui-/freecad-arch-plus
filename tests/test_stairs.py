# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Tests for the Stairs tool. Stairs round-trips through native ArchStairs
# properties (it has no JSON spec), and _loadFromObject carries the non-trivial
# break/turn reconstruction, so these drive the real load -> collect path.

import types

import stairsplus_gui as sg
from conftest import FakeCombo, FakeNum, FakeCheck, quantity

_TURN = ("HalfTurnLeft", "HalfTurnRight")


def _panel(obj):
    p = object.__new__(sg.StairsPlusTaskPanel)
    p.obj, p._building = obj, True
    p._turnFlights = _TURN
    p._quarterFlights = ("QuarterTurnLeft", "QuarterTurnRight")
    p.width = FakeNum(); p.height = FakeNum(); p.length = FakeNum()
    p.steps = FakeNum(); p.tread = FakeNum(); p.nosing = FakeNum()
    p.treadTh = FakeNum(); p.riserTh = FakeNum()
    p.flight = FakeCombo(); p.landingChk = FakeCheck(); p.turnSteps = FakeNum()
    p.atStep = FakeNum(); p.align = FakeCombo(); p.structure = FakeCombo()
    p.structTh = FakeNum(); p.stringerW = FakeNum()
    return p


def _obj(**over):
    values = dict(
        Width=1000.0, Height=3000.0, Length=4000.0, NumberOfSteps=18,
        TreadDepthEnforce=280.0, Nosing=25.0, TreadThickness=50.0,
        RiserThickness=50.0, Flight="HalfTurnLeft", Landings="None",
        WinderSteps=3, LandingStep=9, Align="Left", Structure="Massive",
        StructureThickness=150.0, StringerWidth=120.0,
    )
    values.update(over)
    ns = types.SimpleNamespace()
    for k, v in values.items():
        # Length-like properties expose a .Value; counts/strings are plain.
        if k in ("NumberOfSteps", "WinderSteps", "LandingStep",
                 "Flight", "Landings", "Align", "Structure"):
            setattr(ns, k, v)
        else:
            setattr(ns, k, quantity(v))
    return ns


def test_editing_a_half_turn_restores_every_field():
    p = _panel(_obj())
    p._loadFromObject()
    assert p._collect() == dict(
        width=1000.0, height=3000.0, length=4000.0, numberOfSteps=18,
        treadDepth=280.0, nosing=25.0, treadThickness=50.0,
        riserThickness=50.0, flight="HalfTurnLeft",
        breakSteps=3,           # reconstructed from WinderSteps
        breakAtStep=9,          # from LandingStep
        align="Left", structure="Massive",
        structureThickness=150.0, stringerWidth=120.0,
    )


def test_editing_a_straight_flight_with_landing():
    p = _panel(_obj(Flight="Straight", Landings="At center",
                    NumberOfSteps=17, LandingStep=8))
    p._loadFromObject()
    spec = p._collect()
    assert spec["flight"] == "Straight"
    assert spec["breakSteps"] == 1        # "At center" -> a flat landing
    assert spec["breakAtStep"] == 8


def test_editing_one_field_leaves_the_rest_unchanged():
    p = _panel(_obj())
    p._loadFromObject()
    before = p._collect()
    p.steps.setValue(20)                  # user edits only the step count
    after = p._collect()
    assert after == dict(before, numberOfSteps=20)
