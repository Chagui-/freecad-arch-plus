# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Backward-compatibility shim — DO NOT DELETE.
#
# Documents saved with ArchPlus before the per-tool-folder reorganization
# pickle their Stairs object's Proxy by this exact module path
# ("stairsplus_object._StairsPlus" / "_ViewProviderStairsPlus"). FreeCAD's
# unpickler resolves the class via plain getattr(import(module), name),
# regardless of that class's own __module__ attribute — so this module
# must keep existing and keep exposing these two names for as long as any
# such document might still be opened. The real implementation lives in
# stairs/object.py now; nothing here does anything but re-export.

from stairs.object import _StairsPlus, _ViewProviderStairsPlus  # noqa: F401
