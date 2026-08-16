# SPDX-License-Identifier: LGPL-2.1-or-later
#
# partslib_theme - decide whether the ACTIVE FreeCAD theme is dark, so
# partslib_gui.py can pick an explicit dark/light colour token set instead
# of trusting QPalette (FreeCAD applies its themes as a global Qt
# STYLESHEET, not a palette, so palette().color(Base) stays the default
# white regardless of how dark the active theme actually is).
#
# This module is split in two on purpose, so the decision logic can be unit
# tested with no FreeCAD/Qt process at all:
#
#   - is_dark_theme_name() is a pure string function, no imports beyond the
#     standard library, tested directly in tests/test_partslib_theme.py.
#   - read_is_dark_theme() is the only place that touches FreeCAD, kept as
#     a thin wrapper around the pure function so it stays untestable-but-
#     trivial rather than untested-and-complicated.
#
# FreeCAD 1.1 keeps Theme and StyleSheet as SEPARATE parameter-group keys.
# A real reported config is Theme="FreeCAD Dark", StyleSheet="FreeCAD.qss" -
# FreeCAD's own Mod/Tux/NavigationIndicatorGui.py:65-69 checks StyleSheet
# only, which would call that pair light. Both keys must be checked here.


def is_dark_theme_name(theme, stylesheet):
    """True if `theme` or `stylesheet` names a dark theme.

    Pure string check, case-insensitive, tolerant of None/"" for either
    argument (both may be unset - see read_is_dark_theme's palette
    fallback for that case)."""
    for name in (theme, stylesheet):
        if name and "dark" in name.lower():
            return True
    return False


def read_is_dark_theme():
    """Read FreeCAD's active Theme/StyleSheet preference and decide whether
    it is dark.

    If BOTH are empty (the classic no-stylesheet case, where the palette
    itself is meaningful rather than the FreeCAD-default white), fall back
    to comparing the application palette's Window colour lightness against
    a mid threshold instead."""
    import FreeCAD
    from PySide import QtGui

    group = FreeCAD.ParamGet(
        "User parameter:BaseApp/Preferences/MainWindow")
    theme = group.GetString("Theme", "")
    stylesheet = group.GetString("StyleSheet", "")

    if not theme and not stylesheet:
        window = QtGui.QApplication.palette().color(QtGui.QPalette.Window)
        return window.lightness() < 128

    return is_dark_theme_name(theme, stylesheet)
