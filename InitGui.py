# SPDX-License-Identifier: LGPL-2.1-or-later
#
# ArchPlus startup (GUI). Instead of registering its own workbench, this
# add-on injects an "ArchPlus" toolbar and menu into the existing BIM
# workbench by wrapping BIMWorkbench.Initialize().
#
# IMPORTANT: FreeCAD exec()s InitGui.py with SEPARATE globals and locals dicts.
# Module-level def/constants land in locals, but a function invoked later
# (our wrapped Initialize) resolves names via its __globals__ - where those
# names are absent. Only names FreeCAD pre-injects (FreeCAD, FreeCADGui, ...)
# live in globals. Therefore everything the deferred wrapper needs is kept as
# CLOSURE variables inside _injectIntoBIM(), not as module-level names.

import FreeCAD
import FreeCADGui as Gui


def _injectIntoBIM():
    """Wrap BIMWorkbench.Initialize so ArchPlus tools appear inside BIM."""

    toolbar = "ArchPlus"
    commands = ["ArchPlus_Stairs", "ArchPlus_Doors", "ArchPlus_Windows"]

    wb = Gui.getWorkbench("BIMWorkbench")
    if wb is None:
        FreeCAD.Console.PrintWarning(
            "ArchPlus: BIM workbench not found; tools not added.\n")
        return

    # Avoid double-wrapping if InitGui is re-executed.
    if getattr(wb, "_archPlusInjected", False):
        return
    wb._archPlusInjected = True

    def add_ui(workbench):
        # Importing the modules registers the ArchPlus_* commands.
        # FreeCAD has already put this add-on folder on sys.path.
        import stairsplus_gui   # noqa: F401
        import doorsplus_gui    # noqa: F401
        import windowsplus_gui  # noqa: F401
        workbench.appendToolbar(toolbar, commands)
        workbench.appendMenu(toolbar, commands)

    _origInitialize = wb.Initialize

    def _wrappedInitialize(*args, **kwargs):
        _origInitialize(*args, **kwargs)
        try:
            add_ui(wb)
        except Exception as exc:  # never break BIM startup
            FreeCAD.Console.PrintError("ArchPlus: %s\n" % exc)

    wb.Initialize = _wrappedInitialize

    # If BIM was already active this session (e.g. add-on reloaded), add the
    # tools immediately too. At cold startup there is no active workbench yet,
    # so Gui.activeWorkbench() raises "No active workbench" - that is expected
    # and benign here, since the wrapped Initialize above handles the normal
    # startup case. Swallow it silently.
    try:
        active = Gui.activeWorkbench()
    except Exception:
        active = None
    if active is not None and active.__class__.__name__ == "BIMWorkbench":
        add_ui(active)


_injectIntoBIM()
