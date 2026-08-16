# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Backward-compatibility shim — DO NOT DELETE.
#
# Documents saved with ArchPlus before the per-tool-folder reorganization
# pickle their Door object's Proxy by this exact module path
# ("doorsplus_object._Window" / "_ViewProviderWindow"). FreeCAD's unpickler
# resolves the class via plain getattr(import(module), name), regardless of
# that class's own __module__ attribute — so this module must keep
# existing and keep exposing these two names for as long as any such
# document might still be opened. The real implementation lives in
# doors/object.py now; nothing here does anything but re-export.
#
# Windows keeps its own separate copy of these same two class names under
# windowsplus_object.py / windows.object — the two stay distinct because
# they resolve through different module names, exactly as they already do
# today.

from doors.object import _Window, _ViewProviderWindow  # noqa: F401
