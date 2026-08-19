# SPDX-License-Identifier: LGPL-2.1-or-later
#
# PartsLib display units - which unit a Length field is SHOWN in.
#
# Nothing here changes what a part is made of. Every value on the wire -
# manifest defaults, ParamForm.values(), build_shape() overrides, the
# App::PropertyLength on a placed part - stays in millimetres, FreeCAD's
# base unit. This module only decides how those millimetres are spelled in
# the browser panel, and converts back at the edge.
#
# Why the panel is opinionated at all: every Length default in the bundled
# library sits between 50 mm and 2200 mm, so in centimetres the whole
# catalogue reads 5 to 220 - two or three digits, the way a furniture
# drawing is dimensioned. Following the user's unit schema instead would
# show a bed as 2000 under "Standard" and as 2.0 under "Meter decimal";
# neither is how anyone measures a bed. So the panel picks cm (or inches
# under an imperial schema) and a part may override PER FIELD when its own
# dimensions genuinely live at another scale.
#
# This module is FREE OF FreeCAD IMPORTS except inside is_imperial(), whose
# import is function-local so the table, the resolution rules and the
# parser stay importable and unit-testable under plain pytest.

import re


# unit key -> (millimetres per unit, decimal places shown)
#
# The decimals are chosen so one whole millimetre stays expressible in every
# unit (test_decimals_keep_a_whole_millimetre_expressible): a field that
# cannot represent 1 mm silently rounds a dimension the builder can still
# receive.
LENGTH_UNITS = {
    "mm": (1.0, 0),
    "cm": (10.0, 1),
    "m": (1000.0, 3),
    "in": (25.4, 2),
    "ft": (304.8, 3),
}

METRIC_UNITS = ("mm", "cm", "m")
IMPERIAL_UNITS = ("in", "ft")

DEFAULT_METRIC = "cm"
DEFAULT_IMPERIAL = "in"


def display_unit(spec, imperial=False):
    """The unit one Length field is shown in.

    A part may declare {"unit": {"metric": "mm", "imperial": "in"}} on a
    param; both halves are required so a user who switches schema never
    lands on a field with no opinion. Anything malformed falls back to the
    family default rather than refusing to draw - validate_manifest() is
    where a bad override is reported."""
    family = IMPERIAL_UNITS if imperial else METRIC_UNITS
    default = DEFAULT_IMPERIAL if imperial else DEFAULT_METRIC
    override = (spec or {}).get("unit")
    if not isinstance(override, dict):
        return default
    wanted = override.get("imperial" if imperial else "metric")
    return wanted if wanted in family else default


def factor(unit):
    """Millimetres in one of `unit`."""
    return LENGTH_UNITS[unit][0]


def decimals(unit):
    """Decimal places a field in `unit` should show."""
    return LENGTH_UNITS[unit][1]


def to_mm(value, unit):
    """A value the user typed or a widget holds -> millimetres."""
    return float(value) * factor(unit)


def from_mm(value, unit):
    """Millimetres -> the number a field in `unit` displays."""
    return float(value) / factor(unit)


def format_length(value, unit):
    """Millimetres -> a labelled string, e.g. "105.0 cm"."""
    return "%.*f %s" % (decimals(unit), from_mm(value, unit), unit)


# Spellings a user may type into a length field. The keys are matched after
# lowercasing; the prime/double-prime characters are folded onto ' and " so
# a value pasted from a PDF parses too.
_ALIASES = {
    "mm": "mm", "millimetre": "mm", "millimetres": "mm",
    "millimeter": "mm", "millimeters": "mm",
    "cm": "cm", "centimetre": "cm", "centimetres": "cm",
    "centimeter": "cm", "centimeters": "cm",
    "m": "m", "metre": "m", "metres": "m", "meter": "m", "meters": "m",
    "in": "in", "inch": "in", "inches": "in", '"': "in",
    "ft": "ft", "foot": "ft", "feet": "ft", "'": "ft",
}

# One "<number><unit?>" run, with the whitespace that follows it. Coverage of
# the whole string is checked by the caller, so trailing junk cannot be
# quietly ignored.
_TOKEN = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*([a-z\"']*)\s*")

# Characters that can appear in something still being typed. Anything else
# can never complete into a length, so the keystroke is refused outright.
_PARTIAL = re.compile(r"[0-9a-z.,\"'\s]*")


def _clean(text):
    if not isinstance(text, str):
        return None
    return (text.strip().lower()
            .replace("″", '"').replace("′", "'"))


def parse_length(text, unit):
    """Millimetres from what a user typed, or None if it is not a length.

    `unit` is the field's own unit, used for a bare number. A typed unit
    wins over it, and units may be combined ("5' 6\"", "1 m 5 cm") because
    that is how imperial dimensions are written. None is a REFUSAL, not a
    zero: the caller keeps the value the field already had.

    Deliberately strict. A length field is the one place in the panel where
    a misread number silently builds the wrong part, so every case that
    could mean two things - a bare number beside a united one, a comma in
    front of exactly three digits - is refused rather than guessed."""
    cleaned = _clean(text)
    if not cleaned:
        return None

    tokens = []
    position = 0
    for match in _TOKEN.finditer(cleaned):
        if match.start() != position:
            return None          # junk between numbers, e.g. "1..5"
        tokens.append((match.group(1), match.group(2)))
        position = match.end()
    if not tokens or position != len(cleaned):
        return None              # junk before or after, e.g. "$18", "18mm)"

    total = 0.0
    for number, suffix in tokens:
        if "," in number and len(number.split(",")[1]) == 3:
            return None          # "1,500" is 1500 or 1.5 depending on locale
        if suffix:
            key = _ALIASES.get(suffix)
        elif len(tokens) == 1:
            key = unit
        else:
            key = None           # "5' 6" - 6 inches, or 6 of the field's unit?
        if key not in LENGTH_UNITS:
            return None
        total += float(number.replace(",", ".")) * factor(key)
    return total


def is_partial_length(text):
    """True if `text` could still become a length as the user keeps typing.

    Qt asks this on every keystroke: a field that answers "invalid" to "2 f"
    never lets the user reach "2 ft"."""
    cleaned = _clean(text)
    if cleaned is None:
        return False
    return _PARTIAL.fullmatch(cleaned) is not None


def unit_errors(name, spec):
    """Validate one param's optional display-unit override.

    Called from manifest.py's _validate_params, so a library author hears
    about a broken override when the part is scanned rather than seeing a
    field quietly drawn in the default unit."""
    spec = spec or {}
    if "unit" not in spec:
        return []
    if spec.get("type") != "Length":
        return ['param %r: a "unit" override is only meaningful on a Length '
                'param, and %r is a %s'
                % (name, name, spec.get("type"))]

    override = spec.get("unit")
    if not isinstance(override, dict):
        return ['param %r: "unit" must be an object declaring a "metric" and '
                'an "imperial" unit, got %r' % (name, override)]

    errors = []
    for half, allowed in (("metric", METRIC_UNITS),
                          ("imperial", IMPERIAL_UNITS)):
        if half not in override:
            errors.append(
                'param %r: "unit" is missing its %r half; both are required '
                'so switching unit schema can never leave the field with no '
                'unit' % (name, half))
            continue
        value = override[half]
        if value not in allowed:
            errors.append(
                'param %r: %r is not a valid %s unit (expected one of: %s)'
                % (name, value, half, ", ".join(allowed)))
    return errors


# Length units that mean the user is working in imperial, as FreeCAD spells
# them when its schema formats a length.
_IMPERIAL_SPELLINGS = ("in", '"', "ft", "'", "yd", "thou", "mil")

# ... and the same answer numerically: millimetres per displayed unit, which
# is what getUserPreferred() reports alongside the string.
_IMPERIAL_FACTORS = (25.4, 304.8, 914.4, 0.0254)


def is_imperial():
    """True when the user's FreeCAD unit schema measures length in imperial.

    Asked of FreeCAD rather than read from the schema INDEX in preferences:
    the numbering of that enum is FreeCAD's internal business, while the unit
    it picks to print a length in is the user-visible answer we actually want.

    Three layers, because this is the one thing here that cannot be proven
    headlessly: the factor from getUserPreferred() (numeric, no parsing), the
    unit string beside it, then the formatted UserString for builds where
    getUserPreferred() is absent. Anything unexpected means metric - the
    default schema, and the safe answer for a panel whose defaults are cm."""
    try:
        import FreeCAD
        quantity = FreeCAD.Units.Quantity(1000.0, FreeCAD.Units.Length)
    except Exception:
        return False

    try:
        preferred = quantity.getUserPreferred()
        for item in preferred:
            if isinstance(item, float) and any(
                    abs(item - known) < 1e-9 for known in _IMPERIAL_FACTORS):
                return True
            if isinstance(item, str) and _clean(item) in _IMPERIAL_SPELLINGS:
                return True
        if any(isinstance(item, (float, str)) for item in preferred):
            return False
    except Exception:
        pass

    printed = _clean(getattr(quantity, "UserString", None)) or ""
    # Whole unit tokens only: "millimeter" contains "mil", and a substring
    # match would read a metric schema as imperial.
    tokens = re.findall(r"[a-z]+|[\"']", printed)
    return any(token in _IMPERIAL_SPELLINGS for token in tokens)


def is_readable(value, unit):
    """True if `value` millimetres reads as a drawing dimension in `unit`.

    Two or three digits, the way a dimension is written by hand. A field
    showing 2000 or 0.5 has the wrong unit, not an unusual part - which is
    why this is enforced over the shipped library rather than left as advice.
    Zero is readable everywhere: a Length default of 0 means "none", and it
    spells the same in every unit."""
    shown = abs(from_mm(value, unit))
    if shown == 0.0:
        return True
    return 1.0 <= shown < 1000.0
