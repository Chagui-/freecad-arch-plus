# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Entry point for the FreeCAD-only verification scripts. Run inside a
# FreeCAD GUI session, from the repository root:
#
#   "C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py
#
# Prints PASS/FAIL lines and exits non-zero if anything failed.

import os
import sys
import tempfile
import traceback

_MOD_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MOD_DIR not in sys.path:
    sys.path.insert(0, _MOD_DIR)

import FreeCAD

from archplus.freecad_tests import _harness as h
from archplus.freecad_tests import verify_browser
from archplus.freecad_tests import verify_panel
from archplus.freecad_tests import verify_parameters
from archplus.freecad_tests import verify_placement
from archplus.freecad_tests import verify_edit
from archplus.freecad_tests import verify_reload
from archplus.freecad_tests import verify_rendering
from archplus.freecad_tests import verify_openings
from archplus.freecad_tests import verify_sketch_visibility

# FreeCAD can process the command-line script more than once per session.
# The first pass creates this marker; later passes skip the work (and exit),
# so duplicate lines never appear in the report.
_MARKER = os.path.join(tempfile.gettempdir(), "archplus_verify.marker")


def _run_one(label, func):
    FreeCAD.Console.PrintMessage("=== %s ===\n" % label)
    h._log_file("=== %s ===" % label)
    try:
        func()
    except Exception:
        h._log_file("CRASH in %s:\n%s" % (label, traceback.format_exc()))
        FreeCAD.Console.PrintError(
            "CRASH in %s: %s\n" % (label, sys.exc_info()[1]))
        h._FAILURES.append(label + " crashed")


def main():
    if os.path.exists(_MARKER):
        FreeCAD.Console.PrintError(
            "ArchPlus verification already ran this session; skipping\n")
        os._exit(0)
    with open(_MARKER, "w") as marker:
        marker.write("running\n")

    FreeCAD.Console.PrintMessage("ArchPlus FreeCAD verification\n")
    h._log_file("ArchPlus FreeCAD verification")
    _run_one("verify_browser", verify_browser.run)
    _run_one("verify_parameters", verify_parameters.run)
    _run_one("verify_placement", verify_placement.run)
    _run_one("verify_edit", verify_edit.run)
    _run_one("verify_panel", verify_panel.run)
    _run_one("verify_reload", verify_reload.run)
    _run_one("verify_rendering", verify_rendering.run)
    _run_one("verify_openings", verify_openings.run)
    _run_one("verify_sketch_visibility", verify_sketch_visibility.run)
    h.report_exceptions()

    failed = h.failures()
    # PrintError too: the console's stdout buffer can be lost when the
    # process exits abruptly, and the summary must always be visible.
    summary = "%d check(s) failed\n" % len(failed)
    FreeCAD.Console.PrintMessage(summary)
    FreeCAD.Console.PrintError(summary)
    os._exit(1 if failed else 0)


# No __main__ guard: FreeCAD runs command-line scripts with __name__ set to
# the file's name, so a guard here would never fire.
main()
