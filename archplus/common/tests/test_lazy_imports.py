# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Guards the project's most dangerous invariant: `Part`, `Sketcher`,
# `ArchComponent`, `Arch`, `Draft` and `archplus.common.geometry` must never be
# imported at MODULE SCOPE in any archplus/tools/*/gui.py or in
# archplus/common/widgets.py.
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
# archplus/common/geometry.py is deliberately exempt from being scanned itself: it
# legitimately imports Part/Sketcher at module scope (that's its whole
# reason to exist as the lazy-import boundary). What matters is that nothing
# *else* imports archplus.common.geometry at module scope, since doing so would drag
# Part/Sketcher in transitively at import time.

import ast
import importlib.util

MODULES = (
    "archplus.tools.doors.gui",
    "archplus.tools.windows.gui",
    "archplus.tools.stairs.gui",
    "archplus.tools.partslib.gui",
    "archplus.common.widgets",
)

BANNED = ("Part", "Sketcher", "ArchComponent", "Arch", "Draft",
          "archplus.common.geometry")


def _top_level_import_names(tree):
    # Walk only the module's top-level statements (not statements nested
    # inside function bodies, where these imports belong and are perfectly
    # safe) and collect every name each import statement binds.
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            names.append(mod)
            # `from archplus.common import geometry` binds
            # archplus.common.geometry without ever naming it as such - record
            # the qualified form too, or a banned dotted target spelled this
            # way slips through.
            names.extend("%s.%s" % (mod, alias.name) if mod else alias.name
                         for alias in node.names)
    return names


def _module_scope_import_names(modname):
    # Locate the module's source file and parse it WITHOUT importing/executing
    # it. archplus.tools.partslib.gui defines
    # `class PartsLibraryPanel(QtGui.QWidget)` at module scope, which only
    # works against a real Qt binding - actually
    # importing it here (under conftest.py's bare-placeholder PySide fakes)
    # would raise AttributeError before we ever get to check the thing this
    # test cares about. Static source inspection sidesteps that entirely.
    spec = importlib.util.find_spec(modname)
    with open(spec.origin, encoding="utf-8") as f:
        src = f.read()
    return _top_level_import_names(ast.parse(src))


def _banned_hits(names):
    return [n for n in names
            if any(n == b or n.startswith(b + ".") for b in BANNED)]


def test_gui_modules_do_not_import_banned_names_at_module_scope():
    for modname in MODULES:
        hits = _banned_hits(_module_scope_import_names(modname))
        assert not hits, \
            "module-scope import of %r in %s" % (hits[0], modname)


# The test above only proves these six real files are currently clean - it
# says nothing about whether the checker itself is capable of catching a
# violation if one were introduced. Feed it synthetic source for every
# dangerous import spelling (including the `from archplus.common import geometry as
# ...` form that originally slipped through the ImportFrom branch) and every
# import spelling that must NOT trip it, so a regression in the checker's
# own logic fails loudly here instead of silently passing everything else.
def test_banned_hits_detects_every_dangerous_import_spelling():
    # Each of these MUST be flagged as a module-scope banned import.
    dangerous_snippets = (
        "import Part",
        "import Sketcher",
        "import ArchComponent",
        "from Part import Face",
        "import archplus.common.geometry",
        "from archplus.common.geometry import add_rect",
        "from archplus.common import geometry",
        "from archplus.common import geometry as archplus_geometry",
        "import Part, Sketcher",
    )
    for snippet in dangerous_snippets:
        names = _top_level_import_names(ast.parse(snippet))
        assert _banned_hits(names), \
            "expected %r to be caught as a banned import" % (snippet,)

    # None of these are banned and must NOT be flagged (false positives would
    # make the guard useless by training reviewers to ignore its failures).
    safe_snippets = (
        "import os",
        "from PySide import QtGui, QtCore",
        "from archplus.common import widgets",
        "from archplus.common.spec import storeSpec, readSpec",
        "from . import object as doorsplus_object",
    )
    for snippet in safe_snippets:
        names = _top_level_import_names(ast.parse(snippet))
        assert not _banned_hits(names), \
            "did not expect %r to be caught as a banned import" % (snippet,)
