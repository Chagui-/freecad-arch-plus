import sys

import partslib_thumbs as pt


def test_render_shape_returns_false_rather_than_raising_without_pivy(tmp_path):
    # pivy is not installed here, so the very first import inside
    # render_shape's try block fails - exercising the exact "no GL context /
    # no dependency" degrade path the module promises never raises.
    ok = pt.render_shape(object(), str(tmp_path / "out.png"))
    assert ok is False


def test_render_shape_survives_freecad_being_unimportable(tmp_path, monkeypatch):
    # The test harness installs a fake FreeCAD into sys.modules (see
    # conftest), which is enough to satisfy a naive `import FreeCAD` in an
    # error handler. The bug this guards against was exactly that: the
    # handler imported FreeCAD in order to log, so a missing FreeCAD made the
    # handler itself raise, escaping the try it was supposed to close.
    #
    # Binding the name to None in sys.modules makes `import FreeCAD` raise
    # ImportError, restoring the real-world condition the fake hides. Without
    # this, the test passes against the pre-fix code and guards nothing.
    monkeypatch.setitem(sys.modules, "FreeCAD", None)
    assert pt.render_shape(object(), str(tmp_path / "out.png")) is False


def test_ensure_thumbnail_returns_none_when_freecad_is_unimportable(tmp_path, monkeypatch):
    # Same guarantee on the other failure path: a build failure must degrade
    # to "no thumbnail", never to an exception reaching the caller.
    monkeypatch.setitem(sys.modules, "FreeCAD", None)
    entry = {"id": "nope", "dir": str(tmp_path)}
    resolved = {"geometry": {"builder": "demo.box"}, "params": {}}
    assert pt.ensure_thumbnail(entry, resolved) is None
