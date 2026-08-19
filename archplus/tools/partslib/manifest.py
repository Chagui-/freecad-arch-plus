# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib manifest - the part.json standard and its validation.
#
# This module is deliberately FREE OF FreeCAD IMPORTS so that manifest
# parsing, facet resolution and param merging can be unit-tested headlessly
# under plain pytest. Do not add FreeCAD, Part or PySide dependencies here.

import json
import os
import re

# units.py is stdlib-only too - its one FreeCAD touch (is_imperial) imports
# inside the function - so importing it here keeps this module headless.
from . import units as partslib_units

SCHEMA_VERSION = 1
DEFAULT_IFC_TYPE = "Building Element Proxy"

# A param default of "auto" means the builder derives the value. It reaches
# the builder as None, so a builder that forgot to derive it fails loudly on
# int(None) rather than silently building the wrong thing.
AUTO = "auto"

# The closed set of param `type` values. Each one maps to a FreeCAD
# property class in object.py's _PARAM_PROPERTY_TYPES, so a type outside
# the set cannot become a property at all - a validation error, not a
# guess.
PARAM_TYPES = ("Length", "Angle", "Integer", "Bool", "String", "Choice")

# "auto" is only expressible where the builder derives a plain number the
# write-back can measure or compute; a Bool, String or Choice "auto" has
# no meaning to derive (and for Choice the string collides with the AUTO
# sentinel itself).
AUTO_PARAM_TYPES = ("Integer", "Length")

# ...and only on the three dimensions a built shape can actually report.
#
# This is the lesson of the first pass at params, where "auto" was allowed
# on anything. A derived DIMENSION works: the shape has a bounding box, so
# object.py can measure what the builder decided and write it back, and the
# property editor shows a real number. A derived COUNT does not: no shape
# reports how many doors it has, so DoorCount, ShelfCount, FoldCount and
# SeatCount all sat at 0 in the property editor forever - a control that
# looked broken and was.
#
# The counts were not worth rescuing, because they were the wrong shape of
# question. "auto" earns its keep when a count the user KNOWS (a 55" screen,
# a 4-burner hob, a 3-drawer chest) yields a dimension they would otherwise
# have to look up. Running it the other way - deriving a count from a
# dimension the user already set - only shows them arithmetic. So a builder
# that wants a count now simply decides it, with no property involved.
AUTO_PARAM_NAMES = ("Width", "Depth", "Height")

# How many params a part that marks none gets promoted to the browser panel.
PRIMARY_FALLBACK = 3

# Order in which facets are consulted for an IfcType mapping when the part
# does not declare one explicitly.
IFC_TYPE_FACET_ORDER = ("element", "function")

# `id` is NOT required: it is derived from the part's folder path by
# index.scan(). A manifest may still declare one to pin identity across a
# folder rename, and it is validated when present.
REQUIRED_FIELDS = ("schema", "name", "facets", "geometry")

KNOWN_FIELDS = REQUIRED_FIELDS + ("id",) + (
    "description", "keywords", "ifcType", "ifcProperties",
    "params", "placement",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def validate_part_id(part_id):
    """Errors for a part id: '/'-joined lowercase slugs, or [] if valid.

    An id is a part's folder path relative to the library root, so it has one
    segment for a standalone part and two for a family member. Each segment
    must satisfy _ID_RE - which forbids '.', the one character that would
    split the dotted import path used to load the part's builder.py."""
    if not isinstance(part_id, str) or not part_id:
        return ["id %r must be a non-empty string" % (part_id,)]
    segments = part_id.split("/")
    if not all(_ID_RE.match(segment) for segment in segments):
        return ["id %r must be '/'-joined lowercase slugs [a-z0-9-]"
                % (part_id,)]
    return []


def _is_bare_icon_filename(icon):
    """True when `icon` is a plain filename with no path component.

    facets.json is data, not code, so an icon reference must not be able to
    escape the icons folder the UI resolves it under: no separators, no
    parent-directory segments and no absolute paths."""
    if not isinstance(icon, str) or not icon:
        return False
    if "/" in icon or "\\" in icon or ".." in icon:
        return False
    if os.path.isabs(icon):
        return False
    return True


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
        else:
            for value, spec in values.items():
                if not isinstance(spec, dict):
                    continue
                label = spec.get("label")
                if label is not None and not isinstance(label, str):
                    errors.append(
                        "facet %r value %r 'label' must be a string"
                        % (name, value))
                icon = spec.get("icon")
                if icon is not None and not _is_bare_icon_filename(icon):
                    errors.append(
                        "facet %r value %r 'icon' must be a bare filename "
                        "with no path" % (name, value))
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


def facet_label(facets, facet, value):
    """Display label for a facet value; the value itself when none is set.

    The value is the stable id manifests reference and must never be
    renamed; `label` is a purely cosmetic overlay for the UI, same split as
    a part's `id` vs `name`."""
    spec = facets.get(facet, {}).get("values", {}).get(value, {})
    label = spec.get("label")
    return label if label else value


def facet_icon(facets, facet, value):
    """Bare icon filename declared for a facet value, or None."""
    spec = facets.get(facet, {}).get("values", {}).get(value, {})
    icon = spec.get("icon")
    return icon if icon else None


def load_manifest(path):
    """Read a part.json. Raises ValueError if it is missing or malformed."""
    try:
        with open(path, "r", encoding="utf8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ValueError("cannot read manifest %s: %s" % (path, exc))
    if not isinstance(data, dict):
        raise ValueError("manifest %s must be an object" % path)
    return data


def validate_manifest(data, facets):
    """Validate one part manifest against a facet vocabulary.

    Returns (errors, warnings). Unknown top-level fields are warnings so that
    a manifest written against a later schema still loads."""
    errors = []
    warnings = []

    for field in REQUIRED_FIELDS:
        if field not in data:
            errors.append("missing required field %r" % field)

    if data.get("schema") not in (None, SCHEMA_VERSION):
        errors.append("unsupported schema version %r (expected %d)"
                      % (data.get("schema"), SCHEMA_VERSION))

    if data.get("id") is not None:
        errors.extend(validate_part_id(data["id"]))

    errors.extend(_validate_part_facets(data.get("facets"), facets))

    if "variants" in data:
        # Not merely unsupported: a manifest still carrying a variant list is
        # one whose sizes and configuration have not been split into params,
        # so placing it would silently use the wrong defaults. A hard error
        # keeps it out of the index instead of quietly ignoring it.
        errors.append(
            "'variants' was removed; declare params with \"ui\", \"label\", "
            "\"default\": \"auto\" and \"options\" instead")

    geometry = data.get("geometry")
    if geometry is not None and not isinstance(geometry, dict):
        # `geometry` stays required - it carries `assets` and `transform` -
        # but it names no builder. Which code runs is decided by whether the
        # part folder holds a builder.py, so there is nothing here to check.
        errors.append("geometry must be an object")

    errors.extend(_validate_params(data.get("params")))

    for field in data:
        if field not in KNOWN_FIELDS and field != "variants":
            warnings.append("unknown field %r (ignored)" % field)

    return errors, warnings


def _validate_params(declared):
    """Check a manifest's `params` block. Returns a list of error strings.

    `params` is the branch's new public surface: each spec a library
    author writes must be one the property declarer (object.py) and the
    panel (paramform.py) can both represent, or the two sides would
    silently disagree about what a part declares."""
    if declared is None:
        return []
    if not isinstance(declared, dict):
        return ["params must be an object"]

    errors = []
    for name, spec in declared.items():
        if not isinstance(spec, dict):
            errors.append("param %r must be an object" % name)
            continue
        kind = spec.get("type")
        if kind not in PARAM_TYPES:
            errors.append(
                "param %r has unknown type %r (expected one of: %s)"
                % (name, kind, ", ".join(PARAM_TYPES)))
            continue
        errors.extend(partslib_units.unit_errors(name, spec))
        if spec.get("default") == AUTO:
            if kind not in AUTO_PARAM_TYPES:
                errors.append(
                    "param %r: an \"auto\" default is only valid on %s params"
                    % (name, " and ".join(AUTO_PARAM_TYPES)))
            elif name not in AUTO_PARAM_NAMES:
                errors.append(
                    "param %r: an \"auto\" default is only valid on %s, the "
                    "dimensions a built shape can report; derive anything "
                    "else in the builder without declaring a param"
                    % (name, ", ".join(AUTO_PARAM_NAMES)))
        if kind == "Choice":
            options = spec.get("options")
            if not isinstance(options, dict) or not options:
                errors.append(
                    "Choice param %r must declare a non-empty 'options' "
                    "object" % name)
            elif spec.get("default") is not None \
                    and spec["default"] not in options:
                errors.append(
                    "Choice param %r default %r is not a declared option"
                    % (name, spec.get("default")))
    return errors


def _validate_part_facets(declared, facets):
    """Check a manifest's facets block against the vocabulary."""
    if declared is None:
        return []
    if not isinstance(declared, dict):
        return ["facets must be an object"]

    errors = []
    for name, value in declared.items():
        if name not in facets:
            errors.append("unknown facet %r" % name)
            continue
        multi = facet_is_multi(facets, name)
        if isinstance(value, list):
            if not multi:
                errors.append("facet %r is single-valued, got a list" % name)
                continue
            values = value
        else:
            values = [value]
        allowed = facets[name].get("values", {})
        for item in values:
            if item not in allowed:
                errors.append("facet %r has unknown value %r" % (name, item))
    return errors


def derived_metric_names():
    """Measurements computed from the built shape, never authored."""
    return ("Width", "Depth", "Height")


def param_specs(manifest):
    """The manifest's `params` block, or {} if it declares none."""
    return dict(manifest.get("params") or {})


def primary_params(manifest):
    """Ordered names of the params the browser panel shows.

    A part that marks none gets its first PRIMARY_FALLBACK declared params,
    so a panel is never empty and a lazily-authored manifest still works."""
    specs = param_specs(manifest)
    marked = [name for name, spec in specs.items()
              if (spec or {}).get("ui") == "primary"]
    if marked:
        return marked
    return list(specs)[:PRIMARY_FALLBACK]


def choice_options(spec):
    """The ordered options map of a Choice param spec, else {}."""
    if (spec or {}).get("type") != "Choice":
        return {}
    options = spec.get("options")
    return dict(options) if isinstance(options, dict) else {}


def resolve_placement(manifest, params):
    """The effective placement block for one set of param values.

    The part's own `placement` first, then each Choice param's SELECTED
    option's `placement` merged over it per key, in declared order. Merging
    per key is what lets an option say only `host` and keep the part's own
    `offset`.

    This is what a variant's placement override used to do, narrowed to one
    axis: a television on a stand is floor-hosted, the same television on a
    bracket is wall-hosted at a mounting height, and that is a choice the
    user makes rather than a second catalogue entry."""
    resolved = dict(manifest.get("placement") or {})
    params = params or {}
    for name, spec in param_specs(manifest).items():
        options = choice_options(spec)
        if not options:
            continue
        selected = options.get(params.get(name))
        if not isinstance(selected, dict):
            continue
        override = selected.get("placement")
        if isinstance(override, dict):
            resolved.update(override)
    return resolved


def merge_params(manifest, overrides):
    """{name: value} for every param the manifest declares.

    Each name gets its declared default, replaced by overrides[name] only
    when that key is present in `overrides` AND its value is not None - a
    None override (e.g. a property nobody has touched) falls back to the
    default rather than handing a builder a literal None.

    A declared default of "auto" resolves to None, which is the builder's
    signal to derive the value from the other params. An override still
    wins, so typing a number into a derived field pins it.

    Never returns a key the manifest did not declare: an override for an
    undeclared param is silently dropped, so a stale property left behind
    on an object by an old manifest (or a typo) cannot inject a surprise
    argument into a builder."""
    overrides = overrides or {}
    merged = {}
    for name, spec in param_specs(manifest).items():
        default = spec.get("default")
        if default == AUTO:
            default = None
        value = overrides.get(name)
        merged[name] = value if value is not None else default
    return merged


def resolve_ifc_type(manifest, facets):
    """Explicit ifcType, else a facet mapping, else the default."""
    explicit = manifest.get("ifcType")
    if explicit:
        return explicit

    declared = manifest.get("facets") or {}
    for facet in IFC_TYPE_FACET_ORDER:
        value = declared.get(facet)
        if isinstance(value, list):
            value = value[0] if value else None
        if value is None:
            continue
        mapped = facets.get(facet, {}).get("values", {}).get(value, {})
        if mapped.get("ifcType"):
            return mapped["ifcType"]
    return DEFAULT_IFC_TYPE
