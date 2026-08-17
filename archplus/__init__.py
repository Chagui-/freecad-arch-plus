# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Everything this add-on ships lives under this one package, and that is the
# whole reason the package exists — do not flatten `tools/` and `common/` back
# up to the add-on root.
#
# FreeCAD appends EVERY installed `Mod/<addon>/` directory to a single shared
# `sys.path`. Every add-on's top-level package names therefore land in one
# process-wide namespace with no separation between them. `tools` and `common`
# are about the most collision-prone names available: any other add-on that
# ships either one and happens to sort earlier on `sys.path` would capture the
# name, our `import tools.doors.gui` would resolve into their package, and the
# ArchPlus toolbar would silently fail to appear during BIM workbench
# `Initialize()` — with nothing in the Report view pointing at the cause. The
# reverse is just as true: claiming `common` process-wide would break any
# add-on that expects its own.
#
# `archplus` is distinctive enough that only ArchPlus will ever claim it, so
# exactly one name enters the shared namespace. The tool/non-tool split that
# matters to us lives one level down, where it costs nobody else anything.
#
# Deliberately contains no code. The add-on's entry point is InitGui.py at the
# add-on root (FreeCAD requires it there), and importing this package must stay
# free of side effects.
