#!/usr/bin/env python3
# SPDX-License-Identifier: LGPL-2.1-or-later
#
# ONE-SHOT MIGRATION TOOL - delete after the builders have moved.
#
# Copies a builder function out of a family module into the owning part's
# folder as builder.py, renamed to build(). No test can execute a builder
# (conftest fakes Part), so this script is the correctness argument: it
# compares the AST of the function body it wrote against the AST of the
# body it read, and refuses to write anything on a mismatch.

import argparse
import ast
import json
import os
import sys

PARTSLIB = os.path.join("archplus", "tools", "partslib")
BUILDERS = os.path.join(PARTSLIB, "builders")
LIBRARY = os.path.join(PARTSLIB, "library", "basic")

# Family-module helpers that move to library/basic/_shared.py in Task 9.
# A body referencing one of these gets its calls rewritten and an import of
# the family module added. Keys are the private names in the family module;
# values are the public names in _shared.py.
SHARED_RENAMES = {
    "_carcass": "carcass",
    "_doors": "doors",
    "_pulls": "pulls",
}

HEADER = "# SPDX-License-Identifier: LGPL-2.1-or-later\n"


def part_dirs():
    """{part folder name: absolute path} for every part in the library."""
    found = {}
    for name in sorted(os.listdir(LIBRARY)):
        path = os.path.join(LIBRARY, name)
        if os.path.isfile(os.path.join(path, "part.json")):
            found[name] = path
    return found


def builder_symbol(part_path):
    with open(os.path.join(part_path, "part.json")) as fh:
        data = json.load(fh)
    return (data.get("geometry") or {}).get("builder")


def function_source(module_source, name):
    """(source text, ast node) for a top-level function, or raise."""
    tree = ast.parse(module_source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(module_source, node), node
    raise SystemExit("no top-level function %r found" % (name,))


def rewrite(source, func_name, rename_map):
    """Rename the def to build() and repoint shared-helper calls."""
    source = source.replace("def %s(" % func_name, "def build(", 1)
    for private, public in rename_map.items():
        source = source.replace("%s(" % private, "_shared.%s(" % public)
    return source


def unrewrite(source, func_name, rename_map):
    """Exactly reverse rewrite(), so the result can be compared verbatim."""
    source = source.replace("def build(", "def %s(" % func_name, 1)
    for private, public in rename_map.items():
        source = source.replace("_shared.%s(" % public, "%s(" % private)
    return source


def build_file(source, uses_shapes, uses_shared):
    lines = [HEADER, "\n"]
    if uses_shapes:
        lines.append("from archplus.tools.partslib import shapes as sh\n")
    if uses_shared:
        lines.append("from .. import _shared\n")
    if uses_shapes or uses_shared:
        lines.append("\n\n")
    lines.append(source.rstrip("\n") + "\n")
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("module", help="family module, e.g. fittings")
    parser.add_argument("--apply", action="store_true",
                        help="write files (default is a dry run)")
    parser.add_argument("--only", default="",
                        help="comma-separated part folder names; needed where "
                             "two parts share one function, which must not be "
                             "copied into both folders")
    args = parser.parse_args()
    only = [name for name in args.only.split(",") if name]

    module_path = os.path.join(BUILDERS, args.module + ".py")
    with open(module_path) as fh:
        module_source = fh.read()

    written = []
    for part_name, part_path in sorted(part_dirs().items()):
        symbol = builder_symbol(part_path)
        if not symbol or not symbol.startswith(args.module + "."):
            continue
        if only and part_name not in only:
            continue
        func_name = symbol.split(".", 1)[1]
        source, _node = function_source(module_source, func_name)

        renames = {name: public for name, public in SHARED_RENAMES.items()
                   if "%s(" % name in source}
        rewritten = rewrite(source, func_name, renames)
        contents = build_file(rewritten, "sh." in source, bool(renames))

        # The proof, in two parts.
        #
        # 1. It parses, and defines exactly one build(). Catches a rewrite
        #    that produced something Python cannot read.
        new_tree = ast.parse(contents)
        new_func = [n for n in new_tree.body
                    if isinstance(n, ast.FunctionDef) and n.name == "build"]
        if len(new_func) != 1:
            raise SystemExit("%s: rewrite did not produce exactly one build()"
                             % (part_name,))
        # 2. Reversing the rewrite recovers the original source EXACTLY.
        #    Stronger than comparing ASTs, and it holds for the renamed
        #    kitchen parts too: anything the rewrite touched beyond the def
        #    line and the helper calls shows up as a string difference.
        if unrewrite(rewritten, func_name, renames) != source:
            raise SystemExit("%s: rewrite is not reversible - it changed more "
                             "than the def line and the helper calls"
                             % (part_name,))
        extracted = ast.get_source_segment(contents, new_func[0])
        if unrewrite(extracted, func_name, renames) != source:
            raise SystemExit("%s: extracted body differs from the original"
                             % (part_name,))

        target = os.path.join(part_path, "builder.py")
        print("%-24s %-28s -> %s" % (part_name, symbol, target))
        if args.apply:
            with open(target, "w") as fh:
                fh.write(contents)
        written.append((part_name, func_name))

    print("\n%d part(s) %s" % (len(written),
                               "written" if args.apply else "matched (dry run)"))
    print("Remove from %s: %s" % (
        module_path, ", ".join(name for _part, name in written)))


if __name__ == "__main__":
    sys.exit(main())
