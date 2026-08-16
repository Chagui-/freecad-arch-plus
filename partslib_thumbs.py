# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib thumbnails - offscreen PNG rendering from a bare Part.Shape.
#
# Thumbnails are committed to the repo so a fresh clone opens to a populated
# grid. Runtime rendering is a fallback for a part whose thumbnail is missing,
# and it is never fatal: SoOffscreenRenderer needs a GL context and fails on
# some drivers, so every failure path returns False instead of raising.
#
# The technique follows FreeCAD's own OfflineRenderingUtils.render().
#
# SESSION-LEVEL FAILURE CACHE: where rendering cannot work at all on a
# machine (no GL context, no writable image backend), render_shape() returns
# False on every single call - not an exception, so there is nothing here
# for a caller to catch and remember
# on its own. Without _RENDER_FAILED below, every part lacking a committed
# thumbnail would rebuild its real geometry (booleans, fillets) and retry a
# doomed render on every grid repaint: every keystroke in the search box,
# every breadcrumb click, every panel reopen - unbounded, and with no
# warning printed anywhere to explain why. _RENDER_FAILED remembers a path
# that has already failed once, so both callers (the grid's committed-vs-
# on-demand thumbnail, and the detail pane's per-variant preview) skip
# straight to "no thumbnail" without touching the geometry kernel again,
# for the rest of this FreeCAD session.

import os
import time

# TEMPORARY diagnostic instrumentation (see the "still very slow" thread) -
# prints wall-clock elapsed time with the number embedded in the message
# text itself, not relied on the Report view's own timestamp column: if the
# main thread is blocked, Qt does not repaint the Report view until it
# unblocks, so several messages can appear to share one on-screen timestamp
# even though real time passed between when each was actually printed.
_TIMING = True


def _timelog(message):
    if not _TIMING:
        return
    _warn("ArchPlus: [timing] %s\n" % (message,))


THUMBNAIL_FILENAME = "thumbnail.jpg"
THUMBNAIL_SIZE = 256
_BACKGROUND = (1.0, 1.0, 1.0)

# JPEG quality for saved thumbnails. These are flat-shaded renders on a
# solid white ground - no photographic gradients for JPEG's DCT to smear -
# so 92 is visually lossless here while staying well under a committed
# thumbnail's worth of bytes.
JPEG_QUALITY = 92

_RENDER_FAILED = set()


def render_failed_before(out_path):
    """True if rendering to `out_path` has already failed this session."""
    return out_path in _RENDER_FAILED


def mark_render_failed(out_path, message=None):
    """Remember that `out_path` cannot be rendered, and say so once."""
    _RENDER_FAILED.add(out_path)
    _warn(message or (
        "ArchPlus: cannot render %s; will not retry this session\n"
        % (out_path,)))


def reset_render_failures():
    """Forget every remembered failure - a test/debug hook only. Nothing in
    this module calls it: the whole point of the cache is that a failure
    stays remembered for the rest of the session."""
    _RENDER_FAILED.clear()


# Angular deviation for writeInventor, in radians - how finely a curved
# surface is split around its axis. ~0.2 rad is ~31 facets per full turn:
# smooth at 256px, cheap to mesh.
_ANGULAR_DEVIATION = 0.2

# Linear deviation is scaled to the part instead of fixed. writeInventor's
# signature is (Mode, Deviation, AngularDeviation) and Deviation is an
# ABSOLUTE chord tolerance in mm, so the widely-copied FreeCAD idiom
# `writeInventor(2, 0.01)` asks OCC to mesh every surface to within 0.01mm -
# a hundredth of a millimetre, on parts up to 1.7m long. Planar faces do not
# care (a box is two triangles at any tolerance), which is why every
# box-shaped part in this library rendered in ~0.02s and hid the problem.
# Curved faces care enormously: the toilet's oval bowl is a BSpline surface
# (oval() runs the cone through transformGeometry), and meshing it that
# finely took 17 SECONDS in writeInventor alone. Deviation is derived from
# the shape's own bounding box so a nightstand and a bathtub get comparable
# on-screen smoothness; /400 keeps the chord error under about a pixel at
# THUMBNAIL_SIZE.
_DEVIATION_RATIO = 1.0 / 400.0
_MIN_DEVIATION = 0.05


def _tessellation_for(shape):
    """(Mode, Deviation, AngularDeviation) args for Shape.writeInventor()."""
    try:
        diagonal = shape.BoundBox.DiagonalLength
    except Exception:
        diagonal = 1000.0
    deviation = max(diagonal * _DEVIATION_RATIO, _MIN_DEVIATION)
    return (2, deviation, _ANGULAR_DEVIATION)


def thumbnail_path(part_dir):
    """Where a part's committed thumbnail lives."""
    return os.path.join(part_dir, THUMBNAIL_FILENAME)


def _warn(message):
    """Best-effort console warning. A missing FreeCAD must not turn a
    warning into a crash - the failure paths that call this must stay as
    silent-but-harmless as the rendering failure they are reporting."""
    try:
        import FreeCAD
        FreeCAD.Console.PrintWarning(message)
    except Exception:
        pass


def scene_from_shape(shape):
    """Build a Coin scene graph from a bare Part.Shape - no document needed."""
    from pivy import coin

    buf = shape.writeInventor(*_tessellation_for(shape))
    reader = coin.SoInput()
    reader.setBuffer(buf)
    return coin.SoDB.readAll(reader)


def _image_format_for(out_path):
    """(Qt format name, quality) to save `out_path` as, from its extension.

    Driving this off the extension rather than a constant keeps the two
    callers - the grid's thumbnail.jpg and the detail pane's per-variant
    cache - honest about what they actually asked for, and lets a caller
    ask for a PNG without a second code path."""
    extension = os.path.splitext(out_path)[1].lower()
    if extension in (".jpg", ".jpeg"):
        return "JPEG", JPEG_QUALITY
    return "PNG", -1


def _save_buffer_as_image(renderer, out_path, size):
    """Save the renderer's frame buffer to `out_path` through Qt.

    SoOffscreenRenderer.writeToFile() can only emit the image formats Coin
    was BUILT with, and Coin gets PNG/JPEG only from the optional simage
    library. This FreeCAD build ships pivy without it: writeToFile() returns
    0 and silently writes nothing, even though render() succeeded - which is
    exactly what every part in this library did. (FreeCAD's own CAM
    ImageBuilder guards the same call with isWriteSupported() for this
    reason; its getQImage() fallback is not available in this pivy build
    either, so go through the raw buffer.)

    Qt is always present in a GUI session and always writes both PNG and
    JPEG, so this is the primary path, not the fallback."""
    from PySide import QtGui

    buf = renderer.getBuffer()
    if buf is None:
        return False
    if not isinstance(buf, (bytes, bytearray)):
        buf = bytes(bytearray(buf))

    # Derive the component count from the buffer itself rather than trusting
    # getComponents(): a mismatch here reads past the end of the buffer.
    pixels = size * size
    components = len(buf) // pixels if pixels else 0
    if components == 4:
        image_format = QtGui.QImage.Format_RGBA8888
    elif components == 3:
        image_format = QtGui.QImage.Format_RGB888
    else:
        _timelog("_save_buffer_as_image(%s): unexpected buffer: %d bytes for "
                  "%dx%d" % (out_path, len(buf), size, size))
        return False

    image = QtGui.QImage(buf, size, size, size * components, image_format)
    # OpenGL's frame buffer starts at the BOTTOM-left row, QImage's at the
    # top - without this the thumbnail comes out upside down. mirrored()
    # also deep-copies, which detaches the QImage from `buf`'s lifetime.
    if hasattr(image, "mirrored"):
        image = image.mirrored(False, True)
    else:
        image = image.transformed(QtGui.QTransform().scale(1.0, -1.0))
    image_type, quality = _image_format_for(out_path)
    # JPEG has no alpha channel. Qt drops it on conversion, and since the
    # renderer paints _BACKGROUND behind everything the discarded alpha
    # cannot leave black where the background should be.
    return bool(image.save(out_path, image_type, quality))


def render_shape(shape, out_path, size=THUMBNAIL_SIZE):
    """Render `shape` to an image file, in the format `out_path`'s extension
    asks for. Returns True on success, False otherwise."""
    _t_total = time.perf_counter()
    try:
        _t = time.perf_counter()
        from pivy import coin
        _timelog("render_shape(%s): `from pivy import coin` took %.3fs"
                  % (out_path, time.perf_counter() - _t))

        _t = time.perf_counter()
        node = scene_from_shape(shape)
        _timelog("render_shape(%s): scene_from_shape() took %.3fs"
                  % (out_path, time.perf_counter() - _t))

        root = coin.SoSeparator()
        root.addChild(coin.SoDirectionalLight())
        camera = coin.SoPerspectiveCamera()
        root.addChild(camera)
        root.addChild(node)

        region = coin.SbViewportRegion(size, size)
        camera.viewAll(root, region)

        renderer = coin.SoOffscreenRenderer(region)
        renderer.setBackgroundColor(coin.SbColor(*_BACKGROUND))

        root.ref()
        try:
            _t = time.perf_counter()
            ok = renderer.render(root)
            _timelog("render_shape(%s): renderer.render() took %.3fs (ok=%r)"
                      % (out_path, time.perf_counter() - _t, ok))
        finally:
            root.unref()

        if not ok:
            _timelog("render_shape(%s): TOTAL %.3fs (renderer.render()==False)"
                      % (out_path, time.perf_counter() - _t_total))
            return False

        folder = os.path.dirname(out_path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)

        image_type, _ = _image_format_for(out_path)
        _t = time.perf_counter()
        saved = _save_buffer_as_image(renderer, out_path, size)
        _timelog("render_shape(%s): Qt %s save returned %r, took %.3fs"
                  % (out_path, image_type, saved, time.perf_counter() - _t))
        if not saved and renderer.isWriteSupported(image_type):
            # Only worth trying where Coin actually claims support for the
            # format - otherwise it returns 0 and writes nothing, which is
            # the bug this whole path exists to work around.
            renderer.writeToFile(out_path, image_type)

        result = os.path.exists(out_path)
        _timelog("render_shape(%s): TOTAL %.3fs (wrote file=%r)"
                  % (out_path, time.perf_counter() - _t_total, result))
        return result
    except Exception as exc:
        _warn("ArchPlus: thumbnail render failed: %s\n" % (exc,))
        _timelog("render_shape(%s): TOTAL %.3fs (raised %r)"
                  % (out_path, time.perf_counter() - _t_total, exc))
        return False


def ensure_thumbnail(entry, resolved):
    """Path to the part's thumbnail, rendering one if it is missing.

    Checks the session failure cache BEFORE building anything: the build
    step (real Part booleans/fillets) is exactly the expensive half of this,
    so a part already known to fail must skip it entirely, not just skip
    the render call."""
    import partslib_geometry

    _t0 = time.perf_counter()
    path = thumbnail_path(entry["dir"])
    if os.path.exists(path):
        return path
    if render_failed_before(path):
        _timelog("ensure_thumbnail(%r): short-circuited (marked failed "
                  "earlier this session), took %.3fs"
                  % (entry["id"], time.perf_counter() - _t0))
        return None
    try:
        shape = partslib_geometry.build_shape(resolved, entry["dir"])
    except Exception as exc:
        mark_render_failed(path, (
            "ArchPlus: cannot build %r for a thumbnail; will not retry "
            "this session: %s\n" % (entry["id"], exc)))
        return None
    _t1 = time.perf_counter()
    _timelog("ensure_thumbnail(%r): build_shape() took %.3fs"
              % (entry["id"], _t1 - _t0))

    if render_shape(shape, path):
        _timelog("ensure_thumbnail(%r): TOTAL %.3fs (rendered)"
                  % (entry["id"], time.perf_counter() - _t0))
        return path
    mark_render_failed(path, (
        "ArchPlus: cannot render a thumbnail for %r (render_shape() "
        "returned False - see the [timing] lines above for which stage "
        "failed); will not retry this session\n" % (entry["id"],)))
    _timelog("ensure_thumbnail(%r): TOTAL %.3fs (render failed)"
              % (entry["id"], time.perf_counter() - _t0))
    return None
