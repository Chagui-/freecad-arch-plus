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
# on-demand thumbnail, and the detail pane's per-parameter preview) skip
# straight to "no thumbnail" without touching the geometry kernel again,
# for the rest of this FreeCAD session.

import os
import time

# Slow-operation reporting. Anything that blocks the UI for longer than
# this gets one line naming what it was and where the time went; anything
# faster says nothing at all. The point is that a quiet Report view means
# "nothing was slow", so a line appearing is itself the signal.
#
# Elapsed time is printed in the message text rather than read off the
# Report view's own timestamp column: while the main thread is blocked Qt
# does not repaint that view, so a whole run of messages can land on one
# on-screen timestamp even though real time passed between them.
#
# Set at five seconds rather than the half-second it started at. Half a
# second was chosen while hunting a 17-second stall, when anything above
# the noise floor was worth seeing; as ordinary behaviour it just narrated
# work that was already fast enough, and a warning that fires routinely
# stops being read. Five seconds is long enough that a line appearing
# means something actually went wrong.
SLOW_SECONDS = 5.0

# Phases quicker than this are folded away rather than cluttering the
# breakdown of a slow operation.
_PHASE_FLOOR = 0.05


class Timer(object):
    """Times an operation phase by phase, and reports ONE line - only if
    the whole thing turned out to be slow.

    Logging each phase as it happens is what made the Report view
    unreadable: 14 parts x 5 phases of mostly-instant work, burying the one
    part that actually took 17 seconds. Collecting the phases and deciding
    at the end means the breakdown is still there when it matters."""

    def __init__(self, label):
        self.label = label
        self._start = time.perf_counter()
        self._last = self._start
        self._phases = []

    def mark(self, name):
        """Record the time since the previous mark (or since the start)."""
        now = time.perf_counter()
        self._phases.append((name, now - self._last))
        self._last = now

    def elapsed(self):
        return time.perf_counter() - self._start

    def report(self, note=None):
        """Emit one line if this operation was slow. Returns elapsed time."""
        total = self.elapsed()
        if total < SLOW_SECONDS:
            return total
        breakdown = ", ".join(
            "%s %.1fs" % (name, seconds)
            for name, seconds in self._phases if seconds >= _PHASE_FLOOR)
        _warn("ArchPlus: %s took %.1fs%s%s\n" % (
            self.label, total,
            " (%s)" % breakdown if breakdown else "",
            " - %s" % note if note else ""))
        return total


THUMBNAIL_FILENAME = "thumbnail.jpg"
THUMBNAIL_SIZE = 256
_BACKGROUND = (1.0, 1.0, 1.0)

# Where the camera sits relative to the part, for a top-left-front
# isometric. Parts are built to the Arch convention - X wide, Y deep with
# the back at +Y, Z up - so -X is the left side, -Y is the front, and +Z is
# above: the camera looks down the (1, 1, -1) diagonal at the part's front
# left corner. Only the direction matters; viewAll sets the distance.
_VIEW_POSITION = (-1.0, -1.0, 1.0)

# Three-point rig, as (direction the light TRAVELS, intensity). The three
# faces an isometric shows are the top (0, 0, 1), the front (0, -1, 0) and
# the left (-1, 0, 0); a face's brightness is -dot(normal, direction), so
# these are chosen to land at roughly 0.9 / 0.6 / 0.5 respectively - a
# clear "lit from above" reading with enough falloff to tell the vertical
# faces apart.
_LIGHTS = (
    # KEY: essentially straight down, leaning only slightly toward the
    # camera's front-left. Z dominates the other two components, which is
    # what makes the top face unambiguously the brightest.
    ((0.3, 0.4, -1.0), 0.85),
    # FILL: low and from the front left, lifting the two vertical faces
    # that the key light only grazes. Without it they crush to near black,
    # which is what the old single overhead light did.
    ((0.7, 0.7, -0.2), 0.40),
    # RIM: from above and behind. It arrives BEHIND the front and left
    # faces, so it adds nothing there and cannot flatten the gradation the
    # other two establish - it only catches the far edge of curved
    # surfaces, separating a bowl or a leg from the white background.
    ((-0.6, -0.8, -0.3), 0.25),
)

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
    callers - the grid's thumbnail.jpg and the detail pane's per-parameter
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
        _warn("ArchPlus: unexpected render buffer for %s: %d bytes for "
              "%dx%d\n" % (out_path, len(buf), size, size))
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


def render_shape(shape, out_path, size=THUMBNAIL_SIZE, timer=None):
    """Render `shape` to an image file, in the format `out_path`'s extension
    asks for. Returns True on success, False otherwise.

    `timer` lets a caller that already did some of the work (building the
    shape, say) hand in its own Timer so the slow-operation line covers the
    whole job rather than just this half of it."""
    own_timer = timer is None
    if own_timer:
        timer = Timer("rendering %s" % (os.path.basename(out_path),))
    try:
        from pivy import coin
        node = scene_from_shape(shape)
        timer.mark("tessellate")

        root = coin.SoSeparator()
        # CAMERA FIRST, then lights, then geometry - the order FreeCAD's own
        # CAM ImageBuilder uses. A light traversed ahead of the camera is
        # resolved before the viewing transform exists, so its direction
        # ends up interpreted in eye space: it then rides along with the
        # camera instead of staying put in the world, and an overhead light
        # reads as coming from the side.
        #
        # Orthographic, not perspective: an isometric view IS a parallel
        # projection, and it also keeps a 2m wardrobe and a 400mm
        # nightstand looking like the same kind of drawing.
        camera = coin.SoOrthographicCamera()
        root.addChild(camera)
        for direction, intensity in _LIGHTS:
            light = coin.SoDirectionalLight()
            light.direction = coin.SbVec3f(*direction)
            light.intensity = intensity
            root.addChild(light)
        root.addChild(node)

        region = coin.SbViewportRegion(size, size)
        # Only the DIRECTION from position to target matters here: pointAt
        # sets the orientation, then viewAll slides the camera back along
        # that same direction until the whole part fits. So aiming at the
        # origin is fine even though a part's own origin is the corner of
        # its bounding box rather than its centre.
        camera.position = coin.SbVec3f(*_VIEW_POSITION)
        camera.pointAt(coin.SbVec3f(0.0, 0.0, 0.0), coin.SbVec3f(0.0, 0.0, 1.0))
        camera.viewAll(root, region)

        renderer = coin.SoOffscreenRenderer(region)
        renderer.setBackgroundColor(coin.SbColor(*_BACKGROUND))

        root.ref()
        try:
            ok = renderer.render(root)
        finally:
            root.unref()
        timer.mark("render")

        if not ok:
            return False

        folder = os.path.dirname(out_path)
        if folder and not os.path.isdir(folder):
            os.makedirs(folder)

        image_type, _ = _image_format_for(out_path)
        if not _save_buffer_as_image(renderer, out_path, size) \
                and renderer.isWriteSupported(image_type):
            # Only worth trying where Coin actually claims support for the
            # format - otherwise it returns 0 and writes nothing, which is
            # the bug this whole path exists to work around.
            renderer.writeToFile(out_path, image_type)
        timer.mark("save")

        return os.path.exists(out_path)
    except Exception as exc:
        _warn("ArchPlus: thumbnail render failed: %s\n" % (exc,))
        return False
    finally:
        if own_timer:
            timer.report()


def ensure_thumbnail(entry, resolved):
    """Path to the part's thumbnail, rendering one if it is missing.

    Checks the session failure cache BEFORE building anything: the build
    step (real Part booleans/fillets) is exactly the expensive half of this,
    so a part already known to fail must skip it entirely, not just skip
    the render call."""
    from . import geometry as partslib_geometry

    path = thumbnail_path(entry["dir"])
    if os.path.exists(path):
        return path
    if render_failed_before(path):
        return None

    timer = Timer("first thumbnail for %r" % (entry["id"],))
    try:
        shape = partslib_geometry.build_shape(resolved, entry["dir"])
    except Exception as exc:
        mark_render_failed(path, (
            "ArchPlus: cannot build %r for a thumbnail; will not retry "
            "this session: %s\n" % (entry["id"], exc)))
        return None
    timer.mark("build")

    rendered = render_shape(shape, path, timer=timer)
    timer.report()
    if rendered:
        return path
    mark_render_failed(path, (
        "ArchPlus: cannot render a thumbnail for %r; will not retry this "
        "session\n" % (entry["id"],)))
    return None
