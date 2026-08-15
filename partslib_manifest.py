# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib manifest - the part.json standard and its validation.
#
# This module is deliberately FREE OF FreeCAD IMPORTS so that manifest
# parsing, facet resolution and variant merging can be unit-tested headlessly
# under plain pytest. Do not add FreeCAD, Part or PySide dependencies here.

import copy
import json
import re

SCHEMA_VERSION = 1
DEFAULT_IFC_TYPE = "Building Element Proxy"

# Order in which facets are consulted for an IfcType mapping when the part
# does not declare one explicitly.
IFC_TYPE_FACET_ORDER = ("element", "function")

REQUIRED_FIELDS = ("schema", "id", "name", "facets", "geometry")

KNOWN_FIELDS = REQUIRED_FIELDS + (
    "description", "keywords", "ifcType", "ifcProperties",
    "params", "placement", "variants",
)

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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

    part_id = data.get("id")
    if part_id is not None and not (
            isinstance(part_id, str) and _ID_RE.match(part_id)):
        errors.append("id %r must be a lowercase slug [a-z0-9-]" % (part_id,))

    errors.extend(_validate_part_facets(data.get("facets"), facets))

    geometry = data.get("geometry")
    if geometry is not None:
        if not isinstance(geometry, dict):
            errors.append("geometry must be an object")
        elif not isinstance(geometry.get("builder"), str):
            errors.append("geometry has no 'builder'")

    for field in data:
        if field not in KNOWN_FIELDS:
            warnings.append("unknown field %r (ignored)" % field)

    return errors, warnings


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


DEFAULT_VARIANT_LABEL = "Default"


def derived_metric_names():
    """Measurements computed from the built shape, never authored."""
    return ("Width", "Depth", "Height")


def variant_labels(manifest):
    """Ordered variant labels. A part with none gets one implicit default."""
    variants = manifest.get("variants") or []
    if not variants:
        return [DEFAULT_VARIANT_LABEL]
    return [v.get("label", "Variant %d" % i) for i, v in enumerate(variants)]


def resolve_variant(manifest, label):
    """Return a manifest-shaped dict with one variant's overrides applied.

    Merges variant-over-part for `geometry.assets`, `params` and
    `ifcProperties`. The input manifest is never mutated."""
    resolved = copy.deepcopy(manifest)
    variants = resolved.pop("variants", None) or []

    if not variants:
        if label != DEFAULT_VARIANT_LABEL:
            raise KeyError("unknown variant %r" % (label,))
        return resolved

    labels = variant_labels(manifest)
    if label not in labels:
        raise KeyError("unknown variant %r" % (label,))
    variant = copy.deepcopy(variants[labels.index(label)])

    if "assets" in variant:
        resolved.setdefault("geometry", {}).setdefault("assets", {}).update(
            variant["assets"])
    for key in ("params", "ifcProperties"):
        if key in variant:
            resolved.setdefault(key, {}).update(variant[key])
    resolved["variantLabel"] = label
    return resolved


def param_specs(resolved):
    """The resolved variant's `params` block, or {} if it declares none."""
    return dict(resolved.get("params") or {})


def merge_params(resolved, overrides):
    """{name: value} for every param the manifest declares.

    Each name gets its declared default, replaced by overrides[name] only
    when that key is present in `overrides` AND its value is not None - a
    None override (e.g. a property nobody has touched) falls back to the
    default rather than handing a builder a literal None.

    Never returns a key the manifest did not declare: an override for an
    undeclared param is silently dropped, so a stale property left behind
    on an object by an old manifest (or a typo) cannot inject a surprise
    argument into a builder."""
    overrides = overrides or {}
    merged = {}
    for name, spec in param_specs(resolved).items():
        value = overrides.get(name)
        merged[name] = value if value is not None else spec.get("default")
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
