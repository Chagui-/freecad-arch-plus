import partslib_thumbs as pt


def test_render_shape_returns_false_rather_than_raising_without_pivy(tmp_path):
    # This environment has neither pivy nor FreeCAD installed, so the very
    # first import inside render_shape's try block fails - exercising the
    # exact "no GL context / no dependency" degrade path the module promises
    # never turns into a raised exception.
    ok = pt.render_shape(object(), str(tmp_path / "out.png"))
    assert ok is False
