import ast
import inspect

from partslib import theme as pt


def test_core_module_does_not_import_freecad_at_module_scope():
    # partslib_theme legitimately needs FreeCAD to read the live theme, but
    # that import must live inside read_is_dark_theme(), not at module
    # scope, so is_dark_theme_name() stays importable/testable with no
    # FreeCAD on the path. Walk only the module's TOP-LEVEL statements
    # (not nested inside function defs) looking for the banned imports.
    src = inspect.getsource(pt)
    tree = ast.parse(src)
    banned = ("FreeCAD", "Part", "PySide")
    for node in tree.body:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        else:
            continue
        for name in names:
            assert not any(name == b or name.startswith(b + ".")
                            for b in banned), \
                "module-scope import of %r in partslib.theme" % (name,)


def test_real_user_config_theme_and_stylesheet_both_named_dark():
    # The exact pair reported by the user: FreeCAD 1.1's separate Theme and
    # StyleSheet keys, both naming a dark theme. FreeCAD's own
    # Mod/Tux/NavigationIndicatorGui.py:65-69 checks only StyleSheet, which
    # would get this wrong (StyleSheet alone here is just "FreeCAD.qss",
    # with no "dark" in it) - Theme must also be checked.
    assert pt.is_dark_theme_name("FreeCAD Dark", "FreeCAD.qss") is True


def test_stylesheet_only_dark():
    assert pt.is_dark_theme_name("", "FreeCAD Dark.qss") is True


def test_theme_only_dark():
    assert pt.is_dark_theme_name("FreeCAD Dark", "") is True


def test_neither_dark():
    assert pt.is_dark_theme_name("FreeCAD Light", "FreeCAD.qss") is False


def test_both_none():
    assert pt.is_dark_theme_name(None, None) is False


def test_both_empty_string():
    assert pt.is_dark_theme_name("", "") is False


def test_mixed_case_dark():
    assert pt.is_dark_theme_name("FREECAD DARK", "") is True
    assert pt.is_dark_theme_name("", "SomeThemeDARK.qss") is True
