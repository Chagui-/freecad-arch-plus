# SPDX-License-Identifier: LGPL-2.1-or-later
#
# Pure logic for the Walls tool: config inheritance, claim resolution and
# edge matching. No FreeCAD imports, so pytest drives this headlessly;
# object.py converts document objects into the plain data these functions eat.

DEFAULT_CONFIG = {"Width": 300.0, "Height": 2800.0, "Align": "Center", "Offset": 0.0}

INHERIT_ALIGN = "Inherit"


def effective_config(chain, defaults=None):
    """Resolve config over a leaf-first chain of property dicts.

    chain: list of dicts, leaf (self) first, then each ancestor, root last.
    Width/Height: None or 0 means inherit from the next dict. Align: None or
    "Inherit" means inherit. Missing keys inherit too. Falls back to
    DEFAULT_CONFIG after the chain.

    Returns {"Width": float, "Height": float, "Align": str, "Offset": float}.
    """
    defaults = defaults if defaults is not None else DEFAULT_CONFIG
    width = height = align = offset = None
    for props in chain:
        if width is None:
            w = props.get("Width")
            width = float(w) if w not in (None, 0) else None
        if height is None:
            h = props.get("Height")
            height = float(h) if h not in (None, 0) else None
        if align is None:
            a = props.get("Align")
            align = a if a not in (None, INHERIT_ALIGN) else None
        if offset is None:
            offset = props.get("Offset")
    return {
        "Width": width if width is not None else float(defaults["Width"]),
        "Height": height if height is not None else float(defaults["Height"]),
        "Align": align if align is not None else defaults["Align"],
        "Offset": offset if offset is not None else float(defaults["Offset"]),
    }


class ClaimNode:
    """One segment in the claim tree (plain data; node identity is the
    document object, passed in as an opaque handle)."""

    def __init__(self, node, claimed, rest=False):
        self.node = node
        self.claimed = frozenset(claimed)
        self.rest = rest
        self.children = []


def resolve_claims(nodes, sketch_edge_names):
    """Distribute sketch edges over a claim tree.

    nodes: list of ClaimNode roots (direct children of the wall, in order).
    sketch_edge_names: list of edge subnames, in sketch order.

    Returns (built, warnings):
      built: {node: frozenset(subnames)} - edges each node extrudes
      warnings: list[str] - one message per problem found
    """
    warnings = []

    for n in nodes:
        for d in _walk_descendants(n):
            if d.rest:
                warnings.append(
                    "Rest only applies to direct children of the wall; "
                    "segment '%s' treated as normal"
                    % getattr(d.node, "Label", d.node))
                d.rest = False
    for n in nodes:
        if n.rest and n.claimed:
            warnings.append(
                "Rest segment '%s' ignores its explicit edges"
                % getattr(n.node, "Label", n.node))
            n.claimed = frozenset()
    rest_nodes = [n for n in nodes if n.rest]
    if len(rest_nodes) > 1:
        for extra in rest_nodes[1:]:
            warnings.append(
                "Only one rest segment is allowed; '%s' treated as normal"
                % getattr(extra.node, "Label", extra.node))
            extra.rest = False
        rest_nodes = rest_nodes[:1]

    sketch_set = set(sketch_edge_names)

    owners = {}
    for node, subs in _iter_claims(nodes):
        for sub in subs:
            if sub not in sketch_set:
                warnings.append("Claim on missing edge %s ignored" % sub)
                continue
            owners.setdefault(sub, []).append(node)
    ancestors = _ancestor_sets(nodes)
    conflicted = set()
    for sub, ns in owners.items():
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                if a not in ancestors[b] and b not in ancestors[a]:
                    conflicted.add(sub)
    for sub in sorted(conflicted):
        warnings.append(
            "Edge %s claimed by several segments; it builds nowhere" % sub)

    claimed_set = set(owners) - conflicted
    rest_edges = sketch_set - claimed_set if rest_nodes else frozenset()
    rest_node = rest_nodes[0] if rest_nodes else None

    built = {}

    def assign(n):
        below = frozenset().union(*(assign(c) for c in n.children)) \
            if n.children else frozenset()
        edges = (set(n.claimed) & sketch_set) - conflicted - below
        if n is rest_node:
            edges |= (rest_edges - below)
        built[n.node] = frozenset(edges)
        return edges | below

    for n in nodes:
        assign(n)
    return built, warnings


def match_edge(polylines, point, tol=None):
    """Nearest edge index to `point`, within tol, or None.

    polylines: sequence of point lists [(x, y, z), ...] in global coords.
    point: (x, y, z). tol: maximum distance in model units; None (the
    default) always returns the nearest edge, however far it is.
    """
    best = None
    best_d = float("inf")
    for i, poly in enumerate(polylines):
        for a, b in zip(poly, poly[1:]):
            d = _point_seg_dist(point, a, b)
            if d < best_d:
                best_d = d
                best = i
    return best if tol is None or best_d <= tol else None


def _point_seg_dist(p, a, b):
    ax, ay, az = a
    bx, by, bz = b
    px, py, pz = p
    abx, aby, abz = bx - ax, by - ay, bz - az
    apx, apy, apz = px - ax, py - ay, pz - az
    denom = abx * abx + aby * aby + abz * abz
    t = 0.0 if denom == 0 else max(
        0.0, min(1.0, (apx * abx + apy * aby + apz * abz) / denom))
    cx, cy, cz = ax + t * abx, ay + t * aby, az + t * abz
    dx, dy, dz = px - cx, py - cy, pz - cz
    return (dx * dx + dy * dy + dz * dz) ** 0.5


def _ancestor_sets(nodes):
    out = {}

    def walk(node, trail):
        out[node] = set(trail)
        for child in node.children:
            walk(child, trail + [node])

    for node in nodes:
        walk(node, [])
    return out


def _walk_descendants(n):
    for c in n.children:
        yield c
        for d in _walk_descendants(c):
            yield d


def _iter_claims(nodes):
    for n in nodes:
        yield n, n.claimed
        for node, subs in _iter_claims(n.children):
            yield node, subs
