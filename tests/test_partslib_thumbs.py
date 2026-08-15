import sys

import pytest

import partslib_geometry as pg
import partslib_thumbs as pt


@pytest.fixture(autouse=True)
def _clean_render_failure_cache():
    # _RENDER_FAILED is a module-level global shared by every test in this
    # file (and by every part in a real session) - reset it before each test
    # so one test's failure marking cannot leak into the next.
    pt.reset_render_failures()
    yield
    pt.reset_render_failures()


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


def test_render_failed_before_and_mark_render_failed_roundtrip(tmp_path):
    out_path = str(tmp_path / "out.png")
    assert pt.render_failed_before(out_path) is False
    pt.mark_render_failed(out_path)
    assert pt.render_failed_before(out_path) is True
    pt.reset_render_failures()
    assert pt.render_failed_before(out_path) is False


def test_ensure_thumbnail_does_not_rebuild_a_part_already_marked_failed(
        tmp_path, monkeypatch):
    # This is the bug the session failure cache exists to fix: without it,
    # a part whose render can never succeed on this machine gets its real
    # geometry rebuilt on every single call (every grid repaint). Marking
    # the path failed up front must short-circuit BEFORE build_shape runs -
    # asserting inside the monkeypatched build_shape proves it is never
    # even attempted, not just that the render is skipped.
    entry = {"id": "always-fails", "dir": str(tmp_path)}
    resolved = {"geometry": {"builder": "demo.box"}, "params": {}}
    path = pt.thumbnail_path(entry["dir"])
    pt.mark_render_failed(path)

    def _must_not_be_called(*args, **kwargs):
        raise AssertionError("build_shape must not run for a known-failed part")

    monkeypatch.setattr(pg, "build_shape", _must_not_be_called)
    assert pt.ensure_thumbnail(entry, resolved) is None


def test_ensure_thumbnail_marks_failure_after_a_failed_render(
        tmp_path, monkeypatch):
    # pivy is not installed in this test environment, so render_shape()
    # fails "naturally" here - this proves ensure_thumbnail records that
    # failure (rather than silently returning None every time with nothing
    # to show for it), so a second call would take the short-circuit path
    # above instead of rebuilding again.
    entry = {"id": "renders-nowhere", "dir": str(tmp_path)}
    resolved = {"geometry": {"builder": "demo.box"}, "params": {}}
    path = pt.thumbnail_path(entry["dir"])

    monkeypatch.setattr(pg, "build_shape", lambda *a, **k: object())
    assert pt.render_failed_before(path) is False
    assert pt.ensure_thumbnail(entry, resolved) is None
    assert pt.render_failed_before(path) is True
