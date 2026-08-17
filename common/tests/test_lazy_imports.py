# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Guards the project's most dangerous invariant: `Part`, `Sketcher`,
# `ArchComponent`, `Arch`, `Draft` and `common.geometry` must never be
# imported at MODULE SCOPE in any tools/*/gui.py or in common/widgets.py.
#
# Why this matters, and why nothing else in the suite catches it: the BIM
# workbench imports each tool's gui.py during its own Initialize(), long
# before a document exists and before Part/Sketcher/ArchComponent are
# guaranteed to be safe to touch at that point in FreeCAD's own startup
# sequence. A module-scope import that works fine under pytest (or even
# under a fully-booted FreeCAD session opened interactively) can still break
# add-on *startup* — and every other test here runs against conftest.py's
# fakes, which happily provide a `Part`/`Sketcher` module to import from at
# any time, so a regression of this kind produces zero test failures
# anywhere else. It only manifests as FreeCAD failing to initialize the
# workbench, which is exactly the failure mode that is hardest to diagnose
# from a Report view. This test parses each module's source with `ast` and
# inspects only its top-level statements (not statements nested inside
# function bodies, where these imports belong and are perfectly safe) so a
# regression is caught here instead of in a live FreeCAD session.
#
# common/geometry.py is deliberately exempt from being scanned itself: it
# legitimately imports Part/Sketcher at module scope (that's its whole
# reason to exist as the lazy-import boundary). What matters is that nothing
# *else* imports common.geometry at module scope, since doing so would drag
# Part/Sketcher in transitively at import time.

import ast
import importlib.util

MODULES = (
    "tools.doors.gui",
    "tools.windows.gui",
    "tools.stairs.gui",
    "tools.partslib.gui",
    "common.widgets",
)

BANNED = ("Part", "Sketcher", "ArchComponent", "Arch", "Draft", "common.geometry")


def _module_scope_import_names(modname):
    # Locate the module's source file and parse it WITHOUT importing/executing
    # it. tools.partslib.gui defines `class PartsLibraryPanel(QtGui.QWidget)`
    # at module scope, which only works against a real Qt binding - actually
    # importing it here (under conftest.py's bare-placeholder PySide fakes)
    # would raise AttributeError before we ever get to check the thing this
    # test cares about. Static source inspection sidesteps that entirely.
    spec = importlib.util.find_spec(modname)
    with open(spec.origin, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src)
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    return names


def test_gui_modules_do_not_import_banned_names_at_module_scope():
    for modname in MODULES:
        for name in _module_scope_import_names(modname):
            assert not any(name == b or name.startswith(b + ".")
                            for b in BANNED), \
                "module-scope import of %r in %s" % (name, modname)
