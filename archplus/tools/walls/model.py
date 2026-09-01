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

    def __init__(self, node, claimed, fallback=False):
        self.node = node
        self.claimed = frozenset(claimed)
        self.fallback = fallback
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
            if d.fallback:
                warnings.append(
                    "Fallback only applies to direct children of the wall; "
                    "segment '%s' treated as normal"
                    % getattr(d.node, "Label", d.node))
                d.fallback = False
    for n in nodes:
        if n.fallback and n.claimed:
            warnings.append(
                "Fallback segment '%s' ignores its explicit edges"
                % getattr(n.node, "Label", n.node))
            n.claimed = frozenset()
    fallback_nodes = [n for n in nodes if n.fallback]
    if len(fallback_nodes) > 1:
        for extra in fallback_nodes[1:]:
            warnings.append(
                "Only one fallback segment is allowed; '%s' treated as normal"
                % getattr(extra.node, "Label", extra.node))
            extra.fallback = False
        fallback_nodes = fallback_nodes[:1]

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

    fallback_edges = sketch_set - set(owners) if fallback_nodes else frozenset()
    fallback_node = fallback_nodes[0] if fallback_nodes else None

    built = {}

    def assign(n):
        below = frozenset().union(*(assign(c) for c in n.children)) \
            if n.children else frozenset()
        edges = (set(n.claimed) & sketch_set) - conflicted - below
        if n is fallback_node:
            edges |= (fallback_edges - below)
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


def _sub3(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _point_dist(a, b):
    d = _sub3(a, b)
    return (d[0] * d[0] + d[1] * d[1] + d[2] * d[2]) ** 0.5


def _unit3(a):
    length = (a[0] * a[0] + a[1] * a[1] + a[2] * a[2]) ** 0.5
    if length < 1e-12:
        return None
    return (a[0] / length, a[1] / length, a[2] / length)


def _continues_straight(pts, next_pts):
    """True when next_pts continues pts as the same straight run: the
    next link is a straight edge pointing the same way and lying on one
    line with pts."""
    a0, a1 = pts[0], pts[-1]
    b0, b1 = next_pts[0], next_pts[-1]
    d = _unit3(_sub3(a1, a0))
    e = _unit3(_sub3(b1, b0))
    if d is None or e is None:
        return False
    cx = d[1] * e[2] - d[2] * e[1]
    cy = d[2] * e[0] - d[0] * e[2]
    cz = d[0] * e[1] - d[1] * e[0]
    if (cx * cx + cy * cy + cz * cz) ** 0.5 > 1e-9:
        return False
    if d[0] * e[0] + d[1] * e[1] + d[2] * e[2] <= 0:
        return False
    return _point_seg_dist(b0, a0, a1) < 1e-6


def _orderLinks(links, reverse_seed):
    """Order one chain's links head-to-tail, keeping every points list in
    its stored travel direction; raises ValueError on unorderable
    leftovers. Mirrors the offset machinery's traversal: forward from the
    seed, then backward from the head."""
    first = links.pop(0)
    seed = list(reversed(first[0])) if reverse_seed else list(first[0])
    ordered = [(seed, first[1])]
    while links:
        for i, (pts, is_line) in enumerate(links):
            if _point_dist(pts[0], ordered[-1][0][-1]) <= 1e-3:
                ordered.append((list(pts), is_line))
                links.pop(i)
                break
        else:
            break
    while links:
        for i, (pts, is_line) in enumerate(links):
            if _point_dist(pts[-1], ordered[0][0][0]) <= 1e-3:
                ordered.insert(0, (list(pts), is_line))
                links.pop(i)
                break
        else:
            raise ValueError("chain edges do not follow one travel direction")
    return ordered


def chain_runs(links):
    """Split one connected edge chain into wall runs: maximal sequences
    of consecutive collinear straight edges; every curved edge is its
    own run — the unit the built wall's side faces show.

    links is [(points, is_line)] for the chain's usable edges, points a
    list of (x, y, z) tuples in the edge's own travel direction, in any
    order. Raises ValueError when the links do not traverse one
    head-to-tail chain (the same rule as the offset machinery's
    polyline). Returns run polylines: a list of point lists in traversal
    order, joints deduplicated within a run."""
    if not links:
        raise ValueError("chain has no usable edges")
    try:
        ordered = _orderLinks(list(links), False)
    except ValueError:
        # The seed link may be stored tail-first relative to the chain;
        # retry with it flipped before giving up.
        ordered = _orderLinks(list(links), True)
    runs = []
    kinds = []  # True while the run consists of straight links only
    for pts, is_line in ordered:
        if runs and kinds[-1] and is_line and _continues_straight(runs[-1],
                                                                  pts):
            runs[-1].extend(pts[1:])
        else:
            runs.append(list(pts))
            kinds.append(is_line)
    return runs
