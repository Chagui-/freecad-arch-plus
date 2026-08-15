# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib manifest - the part.json standard and its validation.
#
# This module is deliberately FREE OF FreeCAD IMPORTS so that manifest
# parsing, facet resolution and variant merging can be unit-tested headlessly
# under plain pytest. Do not add FreeCAD, Part or PySide dependencies here.

SCHEMA_VERSION = 1
DEFAULT_IFC_TYPE = "Building Element Proxy"

# Order in which facets are consulted for an IfcType mapping when the part
# does not declare one explicitly.
IFC_TYPE_FACET_ORDER = ("element", "function")


def validate_facets(doc):
    """Validate a facets.json document. Returns a list of error strings."""
    errors = []
    if not isinstance(doc, dict):
        return ["facets document must be an object"]
    for name, facet in doc.items():
        if not isinstance(facet, dict):
            errors.append("facet %r must be an object" % name)
            continue
        values = facet.get("values")
        if values is None:
            errors.append("facet %r has no 'values'" % name)
        elif not isinstance(values, dict):
            errors.append("facet %r 'values' must be an object" % name)
        multi = facet.get("multi", False)
        if not isinstance(multi, bool):
            errors.append("facet %r 'multi' must be a boolean" % name)
    return errors


def facet_is_multi(doc, facet):
    """True if the facet accepts several values per part."""
    return bool(doc.get(facet, {}).get("multi", False))


def facet_values(doc, facet):
    """Sorted list of allowed values for a facet."""
    return sorted(doc.get(facet, {}).get("values", {}))
