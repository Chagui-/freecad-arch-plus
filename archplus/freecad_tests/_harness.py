# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Shared plumbing for the FreeCAD-only verification scripts in this folder.
#
# These checks run INSIDE a FreeCAD GUI session (they drive the real Qt
# panel), so they live apart from the headless pytest suite: files here are
# named verify_*.py, never test_*.py, and pytest.ini never collects them.
#
# Run everything with:
#
#   "C:\Program Files\FreeCAD 1.1\bin\freecad.exe" archplus/freecad_tests/run_all.py

import os
import sys
import tempfile
import traceback

_MOD_DIR = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _MOD_DIR not in sys.path:
    sys.path.insert(0, _MOD_DIR)

import FreeCAD
import FreeCADGui

from PySide import QtCore

# Every line is mirrored here, flushed per line: FreeCAD's own stdout buffer
# is lost when the process is killed or os._exit()s, so the log file is what
# an automated run reads its results from.
LOG_PATH = os.path.join(tempfile.gettempdir(), "archplus_verify.log")


def reset_log():
    """Start a fresh log; without this the log appends across sessions and
    stale FAIL lines from older runs masquerade as current ones."""
    with open(LOG_PATH, "w") as log:
        log.write("ArchPlus FreeCAD verification\n")

_FAILURES = []
_EXCEPTIONS = []
_ORIG_HOOK = sys.excepthook


def _log_file(line):
    with open(LOG_PATH, "a") as log:
        log.write(line + "\n")


def _hook(exc_type, value, tb):
    _EXCEPTIONS.append("".join(traceback.format_exception(exc_type, value, tb)))
    FreeCAD.Console.PrintError(_EXCEPTIONS[-1])
    _log_file("EXCEPTION " + _EXCEPTIONS[-1])


sys.excepthook = _hook


def check(name, condition, detail=""):
    """Record and print one PASS/FAIL line. Returns the condition."""
    if condition:
        line = "PASS " + name
        FreeCAD.Console.PrintMessage(line + "\n")
    else:
        line = "FAIL " + name
        if detail:
            line += " - " + detail
        FreeCAD.Console.PrintError(line + "\n")
        _FAILURES.append(name)
    _log_file(line)
    return bool(condition)


def mark(label):
    """A progress checkpoint, logged to the file only (keeps the console
    clean while still pinning down where a run stops)."""
    _log_file("... " + label)


def process_events(ms):
    """Run the Qt event loop for `ms` so debounce timers and recomputes fire."""
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec_()


def fresh_doc(name="ArchPlusVerify"):
    """Close every document and start one clean one."""
    for doc in list(FreeCAD.listDocuments().values()):
        FreeCAD.closeDocument(doc.Name)
    return FreeCAD.newDocument(name)


def failures():
    return list(_FAILURES)


def report_exceptions():
    """One check covering the whole run: did anything raise uncaught?"""
    if _EXCEPTIONS:
        check("no exceptions during run", False,
              "%d exception(s); first: %s"
              % (len(_EXCEPTIONS), _EXCEPTIONS[0].splitlines()[-1]))
    else:
        check("no exceptions during run", True)
