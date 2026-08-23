# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Docs image generator for ArchPlus.
#
# Renders the tool reference images used in README.md / docs/ into
# docs/images/: doors and windows hosted in a wall segment, leaves open so
# each operation is visually distinct, and stairs in each flight layout.
# Output matches the Parts Library thumbnail look (white background,
# isometric three-light rig, JPEG quality 92) because it reuses the same
# offscreen renderer.
#
# Run inside a FreeCAD GUI session, from the repository root:
#
#   "C:\Program Files\FreeCAD 1.1\bin\freecad.exe" docs/gen_images.py
#
# freecadcmd.exe cannot do this: the offscreen renderer needs a GL context,
# and the tool factories live in the tools' GUI modules. A FreeCAD window
# opens while the script runs and closes itself at the end.

import os
import sys

_MOD_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _MOD_DIR)

import FreeCAD
import Arch
import Part

from archplus.tools.doors import gui as doors_gui
from archplus.tools.partslib import thumbs
from archplus.tools.stairs import gui as stairs_gui
from archplus.tools.windows import gui as windows_gui

OUT_DIR = os.path.join(_MOD_DIR, "docs", "images")
SIZE = 500
OPENING = 50  # leaf opening %, so swing and slide operations look different

# Glass panes render in the Arch glass blue; everything else stays white.
_GLASS_COLOR = (0.70, 0.85, 0.95)

DOORS = [
    ("door_single_swing", dict(operation="Single swing", panelStyle="Solid")),
]

WINDOWS = [
    ("window_single_sliding", dict(operation="Single sliding")),
    ("window_double_casement", dict(operation="Double casement")),
    ("window_round_fixed", dict(operation="Fixed", shape="Round",
                                width=1200.0, height=1200.0)),
]

STAIRS = [
    ("stairs_straight", dict(flight="Straight", breakSteps=0)),
    ("stairs_landing", dict(flight="Straight", breakSteps=1, breakAtStep=8)),
    ("stairs_half_turn", dict(flight="HalfTurnLeft", breakSteps=3)),
    ("stairs_quarter_turn", dict(flight="QuarterTurnLeft", breakSteps=2)),
]

_STAIRS_DEFAULTS = dict(width=1000.0, height=3000.0, length=4000.0,
                        numberOfSteps=17, treadDepth=0.0, nosing=25.0,
                        treadThickness=50.0, riserThickness=50.0,
                        flight="Straight", breakSteps=0, breakAtStep=8,
                        align="Left", structure="Massive",
                        structureThickness=150.0, stringerWidth=120.0)

# The wall segment every door/window image is hosted in. Front face at y=0
# (toward the camera), extending along X, up Z.
_WALL_LENGTH = 1800.0
_WALL_THICKNESS = 200.0
_WALL_HEIGHT = 2600.0
_SILL = 900.0


def _log(message):
    """Report view + stdout line. print() alone is invisible when FreeCAD
    is launched from Windows rather than a shell, so route through the
    FreeCAD console like the tools do."""
    FreeCAD.Console.PrintMessage(message + "\n")


def _snap(items, name):
    """Render the (shape, color) items to OUT_DIR/<name>.jpg; True on success."""
    out = os.path.join(OUT_DIR, name + ".jpg")
    ok = thumbs.render_groups(items, out, size=SIZE)
    _log("%s -> %s" % (name, "OK" if ok else "FAILED"))
    return ok


def _remove_with_base(obj):
    """Remove `obj` and its base sketch from the active document."""
    doc = FreeCAD.ActiveDocument
    base = getattr(obj, "Base", None)
    doc.removeObject(obj.Name)
    if base is not None and hasattr(base, "Name"):
        try:
            doc.removeObject(base.Name)
        except Exception:
            pass


def _make_wall():
    """A real Arch Wall segment along X, centred on the Y axis - the host
    that cuts its own opening when a door/window is hosted in it.

    Returns (wall, base) - the base Part::Feature must be removed with it."""
    doc = FreeCAD.ActiveDocument
    base = doc.addObject("Part::Feature", "WallBase")
    base.Shape = Part.LineSegment(FreeCAD.Vector(0.0, 0.0, 0.0),
                                  FreeCAD.Vector(_WALL_LENGTH, 0.0, 0.0)).toShape()
    wall = Arch.makeWall(base, width=_WALL_THICKNESS, height=_WALL_HEIGHT)
    return wall, base


def _wall_has_opening(wall):
    """The host cut a real opening: less than the solid wall, more than null."""
    solid = _WALL_LENGTH * _WALL_THICKNESS * _WALL_HEIGHT
    return 0.3 * solid < wall.Shape.Volume < 0.999 * solid


def _front_face(wall):
    """Index of the wall's front face - the one facing the camera (-Y)."""
    for index, face in enumerate(wall.Shape.Faces):
        if face.normalAt(0, 0).isEqual(FreeCAD.Vector(0.0, -1.0, 0.0), 1e-6):
            return index
    return 0


def _split_glass(obj):
    """(non-glass, glass) shapes of a door/window object, in world
    coordinates. WindowParts is a flat list of 5-string groups, and
    buildShapes returns one shape per group, in order, so glass panes can
    be picked out and rendered in the glass colour instead of fusing
    everything into one all-white compound."""
    parts = [obj.WindowParts[i:i + 5]
             for i in range(0, len(obj.WindowParts), 5)]
    shapes = obj.Proxy.buildShapes(obj)
    rest = []
    glass = []
    for part, shape in zip(parts, shapes):
        (glass if part[1] == "Glass panel" else rest).append(shape)
    rest_shape = Part.makeCompound(rest)
    glass_shape = Part.makeCompound(glass)
    rest_shape.Placement = obj.Placement
    glass_shape.Placement = obj.Placement
    return rest_shape, glass_shape


def _render_hosted(entries, factory, place, base_offset):
    failures = 0
    doc = FreeCAD.ActiveDocument
    for label, kwargs in entries:
        wall, wall_base = _make_wall()
        obj = factory(**kwargs)
        obj.Opening = OPENING
        point = FreeCAD.Vector(_WALL_LENGTH / 2.0, 0.0, base_offset)
        obj.Base.Placement = place(point, (wall, _front_face(wall)),
                                   obj.Width.Value, baseOffset=base_offset)
        obj.Hosts = [wall]
        doc.recompute()
        if not _wall_has_opening(wall):
            _log("%s -> FAILED (host cut no opening)" % label)
            failures += 1
        else:
            rest, glass = _split_glass(obj)
            items = [(wall.Shape.fuse(rest), None)]
            if not glass.isNull():
                items.append((glass, _GLASS_COLOR))
            if not _snap(items, label):
                failures += 1
        _remove_with_base(obj)
        doc.removeObject(wall.Name)
        doc.removeObject(wall_base.Name)
    return failures


def _render_doors():
    return _render_hosted(DOORS, doors_gui.makeDoor,
                          doors_gui._doorPlacement, 0.0)


def _render_windows():
    return _render_hosted(WINDOWS, windows_gui.makeWindow,
                          windows_gui._windowPlacement, _SILL)


def _render_stairs():
    failures = 0
    doc = FreeCAD.ActiveDocument
    for label, overrides in STAIRS:
        settings = dict(_STAIRS_DEFAULTS)
        settings.update(overrides)
        stairs = stairs_gui.makeStairsPlus()
        stairs_gui.applySettings(stairs, **settings)
        doc.recompute()
        if not _snap([(stairs.Shape, None)], label):
            failures += 1
        doc.removeObject(stairs.Name)
    return failures


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    if FreeCAD.ActiveDocument is None:
        FreeCAD.newDocument("ArchPlusDocsImages")
    _log("Generating docs images into %s" % OUT_DIR)
    try:
        failures = 0
        failures += _render_doors()
        failures += _render_windows()
        failures += _render_stairs()
    except Exception as exc:
        FreeCAD.Console.PrintError(
            "ArchPlus: docs image generation failed: %s\n" % (exc,))
        os._exit(1)
    FreeCAD.closeDocument(FreeCAD.ActiveDocument.Name)
    _log("%d images, %d failed" % (
        len(DOORS) + len(WINDOWS) + len(STAIRS), failures))
    os._exit(1 if failures else 0)


# No __main__ guard: FreeCAD runs command-line scripts with __name__ set to
# the file's name, so a guard here would never fire and the script would
# silently do nothing after "Processing file: ...".
main()
