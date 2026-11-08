# -*- coding: utf-8 -*-
"""
dxf_formwork.py - formwork plan of the slab above the first floor (ezdxf)
=========================================================================

Redraws the example formwork plan ("Formwork at level +2.90", file
templates/formwork_template.dxf) for the input data of the assignment sheet.

How it works
------------
The example drawing is used as a template, so every symbol, hatch, section
mark, label and dimension of the original is kept. The program:

1. Builds the new structural grid (axes 1-7, 5', A-E) from a, b, c, d.
2. Moves the drawing onto the new grid with a "smart stretch":
     * everything close to an axis or to a beam moves rigidly with it
       (columns, walls, section marks, beams keep their real sizes);
     * small details (section marks, level marks, slab labels, columns ...)
       are detected as rigid clusters and moved without distortion;
     * only the open slab fields in between are stretched.
3. EXHIBITION HALL (axes 1-3, A-E) - one-way slabs 1..6:
     the secondary beams are re-spaced uniformly so that every slab panel is
     a one-way slab (long side / short side >= 2).
4. MEETING ROOM (axes 5'-7, D-E) - one-way slabs 11..:
     the number of slab panels is recalculated. Panels (and secondary beams)
     are added by copying a complete panel of the template (beam, beam
     section, section marks of the edge beams, slab label, level mark,
     dimensions) or removed when fewer panels are needed.
5. Re-numbers slabs and beams that follow the inserted ones, updates the
   level marks, the shear wall labels (SWn L/t), the slab thicknesses
   (h_f = ... cm, from the calculations) and the title, recomputes every
   dimension, adds a table with the element sizes and writes the DXF.

Units of the drawing: cm (1 drawing unit = 1 cm).
"""
from __future__ import annotations

import bisect
import math
import re
from dataclasses import dataclass, field

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.math import Vec2, Vec3
from ezdxf.entities.boundary_paths import (
    PolylinePath, LineEdge, ArcEdge, EllipseEdge, SplineEdge,
)

AX4_TO_5P = 425.0     # [cm] axis 4 -> axis 5'  (400 + 2 x 12.5 on the sheet)
ONE_WAY_LIMIT = 2.0   # slab is one-way when  l_long / l_short >= 2
DEC_SEP = ","         # decimal separator used in dimension texts (DIMDSEP=',')

# =============================================================================
# TEMPLATE DATA  (measured in templates/formwork_template.dxf - do not change)
# =============================================================================
T_X = {"1": 320.4, "2": 950.4, "3": 1580.4, "4": 1965.4,
       "5'": 2390.4, "5": 2595.4, "6": 3225.4, "7": 3855.4}
T_Y = {"A": 598.1, "B": 1178.1, "C": 1353.1, "D": 1528.1, "E": 2108.1}
T_LEVEL = 2.90
T_D = 170.0          # stair parameter d of the template (flight width)
T_STAIR_GAP = 1772.9  # centre of the 20 cm gap between the two flights
T_BALCONY_EDGE = 405.6   # free edge of the balconies (y)
T_CORE_FACE = 2210.6     # outer face of the stair core beyond axis E (y)
T_CANOPY_EDGE = 2435.6   # free edge of the canopy slab (y)
T_CANOPY_X0 = 1745.4     # canopy slab: face of the wall between entrance and canopy (x)
T_B17_Y = 856.6          # axis of beam B17 (lobby slab, axes 3-4)

# exhibition hall: secondary beams (axes) between A-C and C-E (C is a beam too)
T_HALL_BEAMS = [849.6, 1101.6, 1604.7, 1856.6]
T_HALL_PANELS_PER_HALF = 3

# meeting room (5'-7 / D-E): secondary beams, width 25
T_ROOM_BEAMS = [2634.4, 2878.9, 3122.9, 3366.9, 3611.4]
T_BEAM_HALF = 12.5
T_ROOM_ZONE = (T_X["5'"] - 13.5, T_Y["D"] - 57.7, T_X["7"] + 13.5, T_Y["E"] + 52.3)
T_ROOM_WALL0 = (T_X["5'"] - 13.5, T_X["5'"] + 50.0)      # x-range kept with axis 5'
T_ROOM_WALL5 = (T_X["7"] - 105.9, T_X["7"] + 13.5)       # x-range kept with axis 7
T_ROOM_EDGES = (T_Y["E"] - 12.5, T_Y["D"] + 12.5, T_Y["D"] - 12.5)   # beam faces on E, D
T_ROOM_EDGE_X = (T_X["5'"] + 12.5, T_X["7"] - 12.5)      # inner faces 5' and 7
T_ROOM_SLAB_FIRST = 11                                   # slabs 11..16
T_ROOM_SLABS_OLD = 6
T_LAST_SLAB = 21

# shear walls: name -> (direction, from, to) in template coordinates
T_SHEAR_WALLS = {
    "SW1": ("x", 307.9, 688.9), "SW2": ("x", 1977.9, 2402.9),
    "SW3": ("x", 3542.9, 3867.9), "SW4": ("x", 3542.9, 3867.9),
    "SW5": ("x", 307.9, 688.9), "SW6": ("y", 1153.1, 1553.1),
    "SW7": ("y", 1734.1, 2210.6), "SW8": ("y", 1734.1, 2210.6),
    "SW9": ("y", 1745.6, 2120.6),
}

# rigid radius around each control line of the stretch [cm]
R_AXIS = 60.0
R_EDGE = 70.0
R_BEAM = 45.0
R_BD = 26.0          # axes B and D (columns 25x50 on axis 3/4)

SMALL = 100.0        # entities smaller than this can form rigid clusters
CLUSTER_MAX = 160.0  # a cluster bigger than this is dissolved (stretched)
TOUCH = 1.0          # touch tolerance for clustering [cm]
GRID = 0.5           # stretched coordinates are rounded to this grid [cm]


class FormworkError(Exception):
    """The input data cannot be drawn with the template."""


@dataclass
class Layout:
    """Result of the redraw - everything the reinforcement plans need."""
    doc: object
    X: dict                 # axis x-coordinates (drawing)
    Y: dict                 # axis y-coordinates (drawing)
    hall_y: list            # y of all hall supports: A, beams, C, beams, E
    room_x: list            # x of all room supports: 5', beams ..., 7
    n_half: int
    n_room: int
    FX: object              # template x -> drawing x   (callable, returns (x, stretched))
    FY: object              # template y -> drawing y
    level: float
    report: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    def fx(self, x):
        return self.FX(x)[0]

    def fy(self, y):
        return self.FY(y)[0]


# =============================================================================
# NEW GRID
# =============================================================================
def new_grid(a, b, c, d):
    X = {"1": T_X["1"]}
    X["2"] = X["1"] + a
    X["3"] = X["2"] + a
    X["4"] = X["3"] + 2 * d + 45.0
    X["5'"] = X["4"] + AX4_TO_5P
    X["5"] = X["4"] + a
    X["6"] = X["5"] + a
    X["7"] = X["6"] + a
    Y = {"A": T_Y["A"]}
    Y["B"] = Y["A"] + b
    Y["C"] = Y["B"] + c / 2
    Y["D"] = Y["C"] + c / 2
    Y["E"] = Y["D"] + b
    return X, Y


# =============================================================================
# PIECEWISE "STRETCH" MAP WITH RIGID ZONES
# =============================================================================
class StretchMap:
    """1-D map old -> new. Around every control value v_i a zone of radius r_i
    moves rigidly with the control; the gaps between zones are stretched
    linearly. Outside the first/last control the shift of that control is used."""

    def __init__(self, olds, news, radii):
        order = sorted(range(len(olds)), key=lambda i: olds[i])
        o = [olds[i] for i in order]
        n = [news[i] for i in order]
        r = [radii[i] for i in order]
        for _ in range(3):                       # shrink overlapping zones
            for i in range(len(o) - 1):
                room = min(o[i + 1] - o[i], n[i + 1] - n[i]) - 2.0
                if r[i] + r[i + 1] > room:
                    f = max(room, 0.0) / (r[i] + r[i + 1])
                    r[i] *= f
                    r[i + 1] *= f
        self.ko, self.kn = [], []
        for oi, ni, ri in zip(o, n, r):
            self.ko += [oi - ri, oi + ri]
            self.kn += [ni - ri, ni + ri]

    def __call__(self, v):
        ko, kn = self.ko, self.kn
        if v <= ko[0]:
            return v + kn[0] - ko[0], False
        if v >= ko[-1]:
            return v + kn[-1] - ko[-1], False
        i = bisect.bisect_right(ko, v) - 1
        i = min(i, len(ko) - 2)
        if i % 2 == 0:                          # inside a rigid zone
            return v + kn[i] - ko[i], False
        span = ko[i + 1] - ko[i]
        if span <= 1e-9:
            return kn[i], False
        t = (v - ko[i]) / span
        return kn[i] + t * (kn[i + 1] - kn[i]), True


def snap(v, base):
    return base + round((v - base) / GRID) * GRID


XB = T_X["1"] % GRID
YB = T_Y["A"] % GRID


class Placement:
    """Where a group of template entities goes: x-function + the global y-map."""

    def __init__(self, name, xfun):
        self.name = name
        self.xfun = xfun      # x -> (x_new, stretched)
        self.clusters = []    # rigid clusters of this placement

    def point(self, x, y, fy, do_snap=True):
        nx, sx = self.xfun(x)
        ny, sy = fy(y)
        if do_snap and sx:
            nx = snap(nx, XB)
        if do_snap and sy:
            ny = snap(ny, YB)
        return nx, ny


# =============================================================================
# GEOMETRY HELPERS
# =============================================================================
def text_of(e):
    t = e.dxftype()
    if t == "TEXT":
        return e.dxf.text
    if t == "MTEXT":
        return e.plain_text()
    return None


def set_text(e, s):
    if e.dxftype() == "TEXT":
        e.dxf.text = s
    else:
        e.text = s


def ctrl_pts(e):
    """Characteristic points of an entity (template coordinates)."""
    t = e.dxftype()
    try:
        if t == "LINE":
            return [Vec2(e.dxf.start), Vec2(e.dxf.end)]
        if t == "LWPOLYLINE":
            return [Vec2(p[0], p[1]) for p in e.get_points("xy")]
        if t in ("CIRCLE", "ARC"):
            c, r = Vec2(e.dxf.center), e.dxf.radius
            return [c + Vec2(r, r), c - Vec2(r, r)]
        if t == "TEXT":
            p = Vec2(e.dxf.insert)
            h = e.dxf.get("height", 10.0)
            w = 0.7 * h * max(len(e.dxf.text), 1)
            if abs(e.dxf.get("rotation", 0.0) - 90) < 1:
                return [p, p + Vec2(-h, w)]
            return [p, p + Vec2(w, h)]
        if t == "MTEXT":
            p = Vec2(e.dxf.insert)
            h = e.dxf.get("char_height", 10.0)
            return [p - Vec2(h, h), p + Vec2(h, h)]
        if t == "INSERT":
            bb = ezbbox.extents([e])
            if bb.has_data:
                return [Vec2(bb.extmin), Vec2(bb.extmax)]
            return [Vec2(e.dxf.insert)]
        if t == "HATCH":
            pts = []
            for p in e.paths:
                if isinstance(p, PolylinePath):
                    pts += [Vec2(v[0], v[1]) for v in p.vertices]
                else:
                    for ed in p.edges:
                        if isinstance(ed, LineEdge):
                            pts += [Vec2(ed.start), Vec2(ed.end)]
                        elif isinstance(ed, ArcEdge):
                            r = ed.radius
                            pts += [Vec2(ed.center) + Vec2(r, r),
                                    Vec2(ed.center) - Vec2(r, r)]
                        elif isinstance(ed, EllipseEdge):
                            pts.append(Vec2(ed.center))
                        elif isinstance(ed, SplineEdge):
                            pts += [Vec2(q) for q in ed.control_points]
            return pts
        if t == "DIMENSION":
            return [Vec2(e.dxf.defpoint2), Vec2(e.dxf.defpoint3)]
        if t == "SOLID":
            return [Vec2(e.dxf.get(f"vtx{i}")) for i in range(4)
                    if e.dxf.hasattr(f"vtx{i}")]
        if t == "POINT":
            return [Vec2(e.dxf.location)]
    except Exception:
        pass
    return []


def bbox_of(pts):
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def inside(bb, box, tol=0.0):
    return (bb[0] >= box[0] - tol and bb[1] >= box[1] - tol and
            bb[2] <= box[2] + tol and bb[3] <= box[3] + tol)


def touch(b1, b2, tol):
    return not (b1[2] + tol < b2[0] or b2[2] + tol < b1[0] or
                b1[3] + tol < b2[1] or b2[3] + tol < b1[1])


def fmt_num(v, sep=DEC_SEP, dec=1):
    r = round(v, dec)
    if abs(r - round(r)) < 1e-6:
        return str(int(round(r)))
    return f"{r:.{dec}f}".rstrip("0").replace(".", sep)


# =============================================================================
# ENTITY TRANSFORMATION
# =============================================================================
class Mover:
    def __init__(self, doc, fy, shared=()):
        self.doc = doc
        self.fy = fy
        self.shared = list(shared)   # clusters other placements may attach to

    # mapping of one point for an entity --------------------------------------
    def mapper(self, pl, cluster):
        fy = self.fy
        if cluster is not None:
            dx, dy = cluster["delta"]
            return lambda x, y, s=True: (x + dx, y + dy)

        pool = pl.clusters + [c for c in self.shared if c not in pl.clusters]

        def f(x, y, s=True):
            for cl in pool:                            # attach to rigid parts
                bb = cl["bbox"]
                if bb[0] - 0.3 <= x <= bb[2] + 0.3 and bb[1] - 0.3 <= y <= bb[3] + 0.3:
                    dx, dy = cl["delta"]
                    f.attached = True
                    return x + dx, y + dy
            f.attached = False
            return pl.point(x, y, fy, s)
        f.attached = False
        return f

    def move(self, e, pl, cluster):
        f = self.mapper(pl, cluster)
        self.apply(e, f)

    @staticmethod
    def v3(v, f, s=True):
        x, y = f(v.x, v.y, s)
        return Vec3(x, y, v.z)

    def apply(self, e, f):
        t = e.dxftype()
        v3 = self.v3
        if t == "LINE":
            s0, e0 = Vec3(e.dxf.start), Vec3(e.dxf.end)
            s1 = v3(s0, f); a1 = getattr(f, "attached", False)
            e1 = v3(e0, f); a2 = getattr(f, "attached", False)
            # keep horizontal / vertical lines straight: the end that is
            # attached to a rigid part decides the common coordinate
            for ax in (0, 1):
                if abs(s0[ax] - e0[ax]) < 1e-3 and abs(s1[ax] - e1[ax]) > 1e-6:
                    if a1 and not a2:
                        val = s1[ax]
                    elif a2 and not a1:
                        val = e1[ax]
                    else:
                        val = (s1[ax] + e1[ax]) / 2
                    s1 = Vec3(*(val if i == ax else s1[i] for i in range(3)))
                    e1 = Vec3(*(val if i == ax else e1[i] for i in range(3)))
            e.dxf.start, e.dxf.end = s1, e1
        elif t == "LWPOLYLINE":
            pts = []
            for x, y, s, en, bu in e.get_points("xyseb"):
                nx, ny = f(x, y)
                pts.append((nx, ny, s, en, bu))
            e.set_points(pts, "xyseb")
        elif t in ("CIRCLE", "ARC"):
            e.dxf.center = v3(e.dxf.center, f, False)
        elif t in ("TEXT", "MTEXT", "INSERT"):
            ref = e.dxf.insert
            if t == "TEXT" and e.dxf.hasattr("align_point") and (
                    e.dxf.get("halign", 0) or e.dxf.get("valign", 0)):
                ref = e.dxf.align_point
            nx, ny = f(ref.x, ref.y, False)
            delta = Vec3(nx - ref.x, ny - ref.y, 0)
            e.dxf.insert = e.dxf.insert + delta
            if t == "TEXT" and e.dxf.hasattr("align_point"):
                e.dxf.align_point = e.dxf.align_point + delta
            if t == "INSERT":
                for at in e.attribs:
                    at.dxf.insert = at.dxf.insert + delta
                    if at.dxf.hasattr("align_point"):
                        at.dxf.align_point = at.dxf.align_point + delta
        elif t == "HATCH":
            for p in e.paths:
                if isinstance(p, PolylinePath):
                    nv = []
                    for v in p.vertices:
                        nx, ny = f(v[0], v[1])
                        nv.append((nx, ny, v[2] if len(v) > 2 else 0.0))
                    p.vertices = nv
                else:
                    for ed in p.edges:
                        if isinstance(ed, LineEdge):
                            ed.start = Vec2(f(ed.start.x, ed.start.y))
                            ed.end = Vec2(f(ed.end.x, ed.end.y))
                        elif isinstance(ed, (ArcEdge, EllipseEdge)):
                            ed.center = Vec2(f(ed.center.x, ed.center.y, False))
                        elif isinstance(ed, SplineEdge):
                            ed.control_points = [Vec2(f(q.x, q.y)) for q in ed.control_points]
                            ed.fit_points = [Vec2(f(q.x, q.y)) for q in ed.fit_points]
            if e.seeds:
                e.set_seed_points([tuple(f(sp[0], sp[1], False)) for sp in e.seeds])
            e.dxf.associative = 0
        elif t == "DIMENSION":
            self.apply_dimension(e, f)
        elif t == "POINT":
            e.dxf.location = v3(e.dxf.location, f)
        elif t in ("SOLID", "TRACE", "3DFACE"):
            for i in range(4):
                k = f"vtx{i}"
                if e.dxf.hasattr(k):
                    e.dxf.set(k, v3(e.dxf.get(k), f))

    def apply_dimension(self, e, f):
        """Move the definition points with f; move the geometry block in the
        dimension's own frame (u along the dimension, v across it) so that
        extension lines stay perpendicular and the dimension line straight."""
        try:
            old_m = e.get_measurement()
        except Exception:
            old_m = None
        old = {}
        for k in ("defpoint", "defpoint2", "defpoint3", "defpoint4", "defpoint5"):
            if e.dxf.hasattr(k):
                old[k] = Vec3(e.dxf.get(k))
                v = self.v3(old[k], f)
                if k != "defpoint":                    # measured points
                    v = Vec3(snap(v.x, XB), snap(v.y, YB), v.z)
                e.dxf.set(k, v)
        new = {k: Vec3(e.dxf.get(k)) for k in old}
        p1, p2, p3 = old["defpoint"], old.get("defpoint2", old["defpoint"]), \
            old.get("defpoint3", old["defpoint"])
        q1, q2, q3 = new["defpoint"], new.get("defpoint2", new["defpoint"]), \
            new.get("defpoint3", new["defpoint"])
        if e.dimtype == 1 and (p3 - p2).magnitude > 1e-6:      # aligned
            ang = math.atan2(p3.y - p2.y, p3.x - p2.x)
        else:
            ang = math.radians(e.dxf.get("angle", 0.0))
        du = Vec2(math.cos(ang), math.sin(ang))
        dv = Vec2(-du.y, du.x)
        U = lambda P: P.x * du.x + P.y * du.y
        V = lambda P: P.x * dv.x + P.y * dv.y
        u2, u3, U2, U3 = U(p2), U(p3), U(q2), U(q3)
        if u2 > u3:
            u2, u3, U2, U3 = u3, u2, U3, U2
            sv2, sv3 = V(q3) - V(p3), V(q2) - V(p2)
            vv2, vv3 = V(p3), V(p2)
        else:
            sv2, sv3 = V(q2) - V(p2), V(q3) - V(p3)
            vv2, vv3 = V(p2), V(p3)
        vl, svl = V(p1), V(q1) - V(p1)

        def g(x, y, s=True):
            P = Vec2(x, y)
            u, v = U(P), V(P)
            if u3 - u2 < 1e-6 or u <= u2:
                nu = u + U2 - u2
            elif u >= u3:
                nu = u + U3 - u3
            else:
                nu = U2 + (u - u2) * (U3 - U2) / (u3 - u2)
            if abs(v - vl) <= min(abs(v - vv2), abs(v - vv3)):
                nv = v + svl
            else:
                nv = v + (sv2 if abs(u - u2) <= abs(u - u3) else sv3)
            R = du * nu + dv * nv
            return R.x, R.y

        if e.dxf.hasattr("text_midpoint"):
            tm = e.dxf.text_midpoint
            e.dxf.text_midpoint = Vec3(*g(tm.x, tm.y), tm.z)
        blk = self.doc.blocks.get(e.dxf.get("geometry", ""))
        if blk is not None:
            for be in blk:
                self.apply(be, g)
        fix_dimension_text(self.doc, e, old_m)


NUM_RE = re.compile(r"^\s*-?\d+(?:[.,]\d+)?\s*$")
LAST_NUM_RE = re.compile(r"(\d+(?:[.,]\d+)?)(?!.*\d)")


def fix_dimension_text(doc, e, old_m):
    """Write the (new) measurement into the dimension's geometry block."""
    try:
        m = e.get_measurement()
    except Exception:
        return
    if not isinstance(m, (int, float)):
        return
    ovr = e.dxf.get("text", "") or ""
    changed = old_m is None or abs(m - old_m) > 0.05
    if ovr and "<>" not in ovr and NUM_RE.match(ovr.replace(",", ".")):
        if changed:
            e.dxf.text = ""          # numeric override is not valid any more
            ovr = ""
        else:
            return                   # keep the override text
    elif ovr and "<>" not in ovr:
        return                       # non-numeric override: keep it
    blk = doc.blocks.get(e.dxf.get("geometry", ""))
    if blk is None:
        return
    new = fmt_num(m)
    for be in blk:
        if be.dxftype() == "MTEXT":
            be.text = LAST_NUM_RE.sub(new, be.text, count=1)


# =============================================================================
# MEETING-ROOM ZONE (one-way slabs 11..): grouping and duplication
# =============================================================================
def is_B_label(e):
    s = text_of(e)
    return s is not None and re.fullmatch(r"B\d+", s.strip()) is not None


def plan_room(X, Y):
    """Number of one-way panels between 5' and 7 and their positions."""
    L = X["7"] - X["5'"]
    span = Y["E"] - Y["D"]
    n = max(2, math.ceil(ONE_WAY_LIMIT * L / span - 1e-9))
    q = [X["5'"] + L * j / n for j in range(n + 1)]
    q = [q[0]] + [snap(v, XB) for v in q[1:-1]] + [q[-1]]
    nold = T_ROOM_SLABS_OLD
    if n >= nold:
        src = [1, 2] + [2] * (n - nold) + list(range(3, nold + 1))
    else:
        src = [1] + list(range(2, n)) + [nold]
    return n, q, src


def collect_room(msp):
    """Explode slab labels, rebuild the beam-face lines and sort all entities
    of the meeting-room zone into beams / panels (template coordinates)."""
    x0, y0, x1, y1 = T_ROOM_ZONE
    zone = (x0, y0, x1, y1)
    for ins in list(msp.query("INSERT")):
        p = ins.dxf.insert
        if ins.dxf.layer == "!Hf" and x0 < p.x < x1 and y0 < p.y < y1:
            ins.explode()

    # beam-face lines on axes D and E: clip the part between the walls and
    # replace it by one continuous line (redrawn later, broken at the webs)
    ex0, ex1 = T_ROOM_EDGE_X
    edge_lines = {}
    for ln in list(msp.query("LINE")):
        if ln.dxf.layer != "035":
            continue
        s, en = ln.dxf.start, ln.dxf.end
        if abs(s.y - en.y) > 0.05:
            continue
        yy = s.y
        if not any(abs(yy - ey) < 0.05 for ey in T_ROOM_EDGES):
            continue
        lo, hi = sorted((s.x, en.x))
        if hi <= ex0 + 0.05 or lo >= ex1 - 0.05:
            continue
        if lo < ex0 - 0.05:
            cp = ln.copy(); msp.add_entity(cp)
            cp.dxf.start = Vec3(lo, yy); cp.dxf.end = Vec3(ex0, yy)
        if hi > ex1 + 0.05:
            cp = ln.copy(); msp.add_entity(cp)
            cp.dxf.start = Vec3(ex1, yy); cp.dxf.end = Vec3(hi, yy)
        key = round(yy, 1)
        if key not in edge_lines:
            cp = ln.copy(); msp.add_entity(cp)
            cp.dxf.start = Vec3(ex0, yy); cp.dxf.end = Vec3(ex1, yy)
            edge_lines[key] = cp
        msp.delete_entity(ln)

    edge_handles = {e.dxf.handle for e in edge_lines.values()}
    beams = [T_X["5'"]] + T_ROOM_BEAMS + [T_X["7"]]
    nb = len(T_ROOM_BEAMS)
    groups = {("beam", k): [] for k in range(1, nb + 1)}
    groups.update({("panel", k): [] for k in range(1, nb + 2)})
    y_on_E = T_Y["E"] - 52.7          # facade columns on axis E move with the panels
    y_lo, y_hi = T_Y["D"] + 7.3, T_Y["E"] - 6.7

    def beam_line_k(e):
        if e.dxftype() != "LINE" or e.dxf.layer not in ("035", "Osi"):
            return None
        s, en = e.dxf.start, e.dxf.end
        if abs(s.x - en.x) > 0.05 or abs(s.y - en.y) < 40:
            return None
        for k in range(1, nb + 1):
            if abs(abs(s.x - beams[k]) - T_BEAM_HALF) < 0.3 or abs(s.x - beams[k]) < 0.3:
                return k
        return None

    cands, dims = [], []
    for e in msp:
        if e.dxf.handle in edge_handles:
            continue
        pts = ctrl_pts(e)
        if not pts:
            continue
        bb = bbox_of(pts)
        full = bb
        if e.dxftype() == "DIMENSION":       # dimension line must be in zone
            full = bbox_of(pts + [Vec2(e.dxf.defpoint)])
        if not inside(full, zone):
            continue
        on_E = (bb[1] + bb[3]) / 2 >= y_on_E
        if e.dxf.layer in ("!Column", "!Hatch") and not on_E:
            continue                         # with the panels, those on D not
        s = text_of(e)
        if s is not None:
            st = s.strip()
            if re.fullmatch(r"SW\d+.*", st):
                continue
            if re.fullmatch(r"C\d+", st) and not on_E:
                continue
            if e.dxf.layer == "text" and NUM_RE.match(st) and not on_E:
                continue                     # column sizes
            if is_B_label(e):
                ix = e.dxf.insert.x
                k = min(range(1, nb + 1), key=lambda i: abs(ix - beams[i]))
                if abs(ix - beams[k]) <= 60:
                    groups[("beam", k)].append(e)
                continue                     # other B labels stay global
        if e.dxftype() == "LINE":
            st, en = e.dxf.start, e.dxf.end
            if (abs(st.y - en.y) < 0.05 and abs(st.x - en.x) > 300):
                continue                     # long edge lines stay global
        if e.dxftype() == "DIMENSION":
            dims.append((e, bb))
        else:
            cands.append((e, bb))

    # cluster candidates (touching bounding boxes)
    nC = len(cands)
    parent = list(range(nC))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for i in range(nC):
        for j in range(i + 1, nC):
            if touch(cands[i][1], cands[j][1], 0.6):
                parent[find(i)] = find(j)
    clusters = {}
    for i in range(nC):
        clusters.setdefault(find(i), []).append(i)

    def wall_zone(bb):
        return ((bb[0] >= T_ROOM_WALL0[0] and bb[2] <= T_ROOM_WALL0[1]) or
                (bb[0] >= T_ROOM_WALL5[0] and bb[2] <= T_ROOM_WALL5[1]))

    def classify(bb, ents=()):
        for e in ents:
            k = beam_line_k(e)
            if k:
                return ("beam", k)
        for k in range(1, nb + 1):
            if (bb[0] >= beams[k] - 47 and bb[2] <= beams[k] + 47
                    and bb[1] >= y_lo and bb[3] <= y_hi):
                return ("beam", k)
        if wall_zone(bb):
            return ("wall", 0)
        cx = (bb[0] + bb[2]) / 2
        for k in range(1, nb + 2):
            if beams[k - 1] < cx <= beams[k]:
                return ("panel", k)
        return ("wall", 0)

    cl_boxes = []
    for idxs in clusters.values():
        bb = bbox_of([Vec2(cands[i][1][0], cands[i][1][1]) for i in idxs] +
                     [Vec2(cands[i][1][2], cands[i][1][3]) for i in idxs])
        g = classify(bb, [cands[i][0] for i in idxs])
        cl_boxes.append((bb, g))
        if g[0] != "wall":
            groups[g] += [cands[i][0] for i in idxs]
    for e, bb in dims:
        g = None
        for cbb, cg in cl_boxes:                 # dimension of a section mark
            if inside(bb, cbb, 2.0):
                g = cg
                break
        if g is None:
            g = classify(bb)
        if g[0] != "wall":
            groups[g].append(e)
    return groups, beams, edge_lines


def room_placements(groups, beams, q, src, fy, msp):
    """Return list of (entity, Placement) for the meeting-room zone, copying
    entities of the duplicated panel/beam where extra panels are needed."""
    items = []
    n = len(q) - 1
    used_p, used_b = set(), set()
    pl_info = []        # (placement, kind, new index, src, is_copy)

    def panel_fun(k, j):
        PL, PR = beams[k - 1] + T_BEAM_HALF, beams[k] - T_BEAM_HALF
        QL, QR = q[j - 1] + T_BEAM_HALF, q[j] - T_BEAM_HALF
        s = (QR - QL) / (PR - PL)
        return lambda x: (QL + (x - PL) * s, abs(s - 1) > 1e-9)

    for j in range(1, n + 1):
        k = src[j - 1]
        pl = Placement(f"panel{j}<-P{k}", panel_fun(k, j))
        copy = k in used_p
        used_p.add(k)
        pl_info.append((pl, "panel", j, k, copy))
        for e in groups[("panel", k)]:
            ent = e
            if copy:
                ent = e.copy(); msp.add_entity(ent)
            items.append((ent, pl, e))
        if j < n:                                # beam on the right of panel j
            dx = q[j] - beams[k]
            plb = Placement(f"beam{j}<-B{k}", (lambda dx: lambda x: (x + dx, False))(dx))
            bcopy = k in used_b
            used_b.add(k)
            pl_info.append((plb, "beam", j, k, bcopy))
            for e in groups[("beam", k)]:
                ent = e
                if bcopy:
                    ent = e.copy(); msp.add_entity(ent)
                items.append((ent, plb, e))
    # template panels / beams that are not used any more (fewer panels)
    for (kind, k), ents in groups.items():
        if (kind == "panel" and k not in used_p) or (kind == "beam" and k not in used_b):
            for e in ents:
                msp.delete_entity(e)
    return items, pl_info


# =============================================================================
# RIGID CLUSTERS
# =============================================================================
def build_clusters(items, fy):
    """items: list of (entity, placement, template_entity). Small entities of
    the same placement that touch each other form rigid clusters."""
    by_pl = {}
    for idx, (e, pl, src) in enumerate(items):
        if e.dxftype() in ("DIMENSION",):
            continue
        pts = ctrl_pts(src)
        if not pts:
            continue
        bb = bbox_of(pts)
        if max(bb[2] - bb[0], bb[3] - bb[1]) > SMALL:
            continue
        tol = TOUCH
        if e.dxftype() in ("TEXT", "MTEXT"):
            tol = 4.0
        by_pl.setdefault(id(pl), (pl, []))[1].append((idx, bb, tol))
    member = {}
    for pl, lst in by_pl.values():
        m = len(lst)
        parent = list(range(m))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        # sweep on x to keep it fast
        order = sorted(range(m), key=lambda i: lst[i][1][0])
        for oi, i in enumerate(order):
            bi = lst[i][1]
            for j in order[oi + 1:]:
                bj = lst[j][1]
                if bj[0] > bi[2] + 4.0:
                    break
                if touch(bi, bj, max(lst[i][2], lst[j][2])):
                    parent[find(i)] = find(j)
        groups = {}
        for i in range(m):
            groups.setdefault(find(i), []).append(i)
        for g in groups.values():
            bb = (min(lst[i][1][0] for i in g), min(lst[i][1][1] for i in g),
                  max(lst[i][1][2] for i in g), max(lst[i][1][3] for i in g))
            if max(bb[2] - bb[0], bb[3] - bb[1]) > CLUSTER_MAX:
                continue
            if len(g) == 1 and items[lst[g[0]][0]][0].dxftype() in ("LINE",):
                continue                     # single short line: just stretch
            cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
            nx, sx = pl.xfun(cx)
            ny, sy = fy(cy)
            dx = snap(nx - cx, 0.0) if sx else nx - cx     # exact when rigid
            dy = snap(ny - cy, 0.0) if sy else ny - cy
            cl = {"bbox": bb, "delta": (dx, dy)}
            pl.clusters.append(cl)
            for i in g:
                member[lst[i][0]] = cl
    # dimensions whose measured points lie inside one cluster move with it
    for idx, (e, pl, src) in enumerate(items):
        if e.dxftype() != "DIMENSION":
            continue
        pts = ctrl_pts(src)
        for cl in pl.clusters:
            bb = cl["bbox"]
            if all(bb[0] - 0.5 <= p.x <= bb[2] + 0.5 and bb[1] - 0.5 <= p.y <= bb[3] + 0.5
                   for p in pts):
                member[idx] = cl
                break
    return member


# =============================================================================
# TEXT UPDATES
# =============================================================================
LEVEL_RE = re.compile(r"^\s*\+\s*(\d+)([.,])(\d+)\s*$")
HF_RE = re.compile(r"^(\s*h\s*=\s*)(\d+(?:[.,]\d+)?)(\s*cm\s*)$")


def new_level_text(m, level, warnings):
    v = float(f"{m.group(1)}.{m.group(3)}")
    dec = len(m.group(3))
    sep = m.group(2)
    if v >= 2.0:
        nv = v - T_LEVEL + level
    elif abs(v - T_LEVEL / 2) < 0.06:
        nv = level / 2
    else:
        nv = v * level / T_LEVEL
        if abs(nv - v) > 0.005:
            warnings.append(f"level +{m.group(1)}{sep}{m.group(3)} (stair) scaled to "
                            f"+{nv:.{dec}f} - check against the staircase design")
    return f"+{nv:.2f}"


def update_slab_thickness(doc, msp, hf_by_slab):
    """Write the slab thicknesses from the calculations into the labels
    'h =12cm' (slab label blocks on layer !Hf and exploded labels)."""
    if not hf_by_slab:
        return
    # slab label blocks: number (MTEXT) + 'h =..cm' (TEXT) in one block
    done = set()
    for ins in msp.query("INSERT"):
        if ins.dxf.layer != "!Hf" or ins.dxf.name in done:
            continue
        blk = doc.blocks.get(ins.dxf.name)
        if blk is None:
            continue
        no = [text_of(e).strip() for e in blk if e.dxftype() in ("TEXT", "MTEXT")
              and (text_of(e) or "").strip().isdigit()]
        if not no or int(no[0]) not in hf_by_slab:
            continue
        for e in blk:
            st = text_of(e) if e.dxftype() in ("TEXT", "MTEXT") else None
            m = HF_RE.match(st or "")
            if m:
                set_text(e, f"{m.group(1)}{fmt_num(hf_by_slab[int(no[0])], '.')}{m.group(3)}")
        done.add(ins.dxf.name)
    # exploded labels: slab number in a circle, 'h =..cm' close to it
    circles = [ci for ci in msp.query("CIRCLE") if 18.0 <= ci.dxf.radius <= 21.0]
    numbers = []
    for e in msp.query("TEXT MTEXT"):
        st = (text_of(e) or "").strip()
        if st.isdigit():
            p = Vec2(e.dxf.insert)
            if any((Vec2(ci.dxf.center) - p).magnitude < 25 for ci in circles):
                numbers.append((int(st), p))
    for e in msp.query("TEXT"):
        m = HF_RE.match(e.dxf.text or "")
        if not m or not numbers:
            continue
        p = Vec2(e.dxf.insert)
        no, q = min(numbers, key=lambda t: (t[1] - p).magnitude)
        if (q - p).magnitude < 130 and no in hf_by_slab:
            e.dxf.text = f"{m.group(1)}{fmt_num(hf_by_slab[no], '.')}{m.group(3)}"


# =============================================================================
# SECTION MARKS OF THE BEAMS: slab thickness and beam depth from the design
# =============================================================================
def find_sections(msp):
    """Beam section marks = three parallel dimensions of the depth: h_f (slab),
    web and total h sharing their end points. Returns a list of dicts
    (ax: 0 = depth along x / 1 = along y, top, f (slab soffit), bot, o (position
    across), hf, h)."""
    D = []
    for e in msp.query("DIMENSION"):
        try:
            m = e.get_measurement()
        except Exception:
            continue
        p2, p3 = e.dxf.defpoint2, e.dxf.defpoint3
        if e.dimtype % 32 == 1:                      # aligned: measured along p2 -> p3
            if abs(p2.x - p3.x) < 0.5:
                ax = 1
            elif abs(p2.y - p3.y) < 0.5:
                ax = 0
            else:
                continue
            m = abs(p3[ax] - p2[ax])
        else:
            ang = round(e.dxf.get("angle", 0.0)) % 180
            if ang not in (0, 90):
                continue
            ax = 0 if ang == 0 else 1
        if not isinstance(m, (int, float)) or m > 120:
            continue
        a, b = sorted((p2[ax], p3[ax]))
        D.append(dict(e=e, ax=ax, a=a, b=b, L=b - a, o=(p2[1 - ax] + p3[1 - ax]) / 2, cs=[p2[1 - ax], p3[1 - ax]]))
    out, used = [], set()
    for T in D:
        if not 30 <= T["L"] <= 110 or id(T["e"]) in used:
            continue
        for H in D:
            if H is T or H["ax"] != T["ax"] or not 8 <= H["L"] <= 22.5 or abs(H["o"] - T["o"]) > 90:
                continue
            if abs(H["a"] - T["a"]) < 3:
                top, f, bot, sgn = T["a"], H["b"], T["b"], 1
            elif abs(H["b"] - T["b"]) < 3:
                top, f, bot, sgn = T["b"], H["a"], T["a"], -1
            else:
                continue
            W = [w for w in D if w["ax"] == T["ax"] and w is not T and w is not H and abs(w["o"] - T["o"]) < 90
                 and abs(w["L"] - (T["L"] - H["L"])) < 3 and (abs(w["a"] - f) < 3 or abs(w["b"] - f) < 3)]
            if not W:
                continue
            key = (T["ax"], round(top), round(T["o"] / 10))
            if any(k == key for k in (g["key"] for g in out)):
                break
            used.add(id(T["e"]))
            out.append(dict(key=key, ax=T["ax"], top=top, f=f, bot=bot, sgn=sgn, o=T["o"],
                            hf=abs(f - top), h=abs(bot - top), cs=T["cs"] + H["cs"] + W[0]["cs"],
                            dims=[T["e"], H["e"], W[0]["e"]]))
            break
    return out


SEC_DIMSTYLE = "RC_SECTION"
SEC_LAYER = "! Plochi sech"   # layer of the section mark blocks of the template
SEC_FLANGE = 35.0          # cm, flange drawn on each side of the web
SEC_DIM_OFF = 14.0         # cm, distance of the dimension lines from the symbol


def _sec_dimstyle(doc):
    if SEC_DIMSTYLE not in doc.dimstyles:
        doc.dimstyles.new(SEC_DIMSTYLE, dxfattribs={
            "dimtxt": 9.0, "dimasz": 3.5, "dimblk": "OBLIQUE", "dimexo": 1.5, "dimexe": 2.5,
            "dimgap": 1.5, "dimdec": 0, "dimzin": 8, "dimtad": 1, "dimtih": 0, "dimtoh": 0,
            "dimtxsty": "Standard", "dimlunit": 2, "dimtmove": 2, "dimclrt": 7, "dimclrd": 3, "dimclre": 3})


def _outline_of(sec, lines):
    """Outline of a section mark: the connected axis-parallel lines (layer 0, colour 3)
    around the bottom of the web. Returns (component, (c0, c1)) or None."""
    ax, top, bot, o = sec["ax"], sec["top"], sec["bot"], sec["o"]
    lo, hi = min(top, bot), max(top, bot)
    U = lambda p: p[ax]
    V = lambda p: p[1 - ax]
    cand = []
    for e in lines:
        # outline lines: layer 0 / colour 3, or the layer of the section blocks (exploded)
        if not e.is_alive or not ((e.dxf.layer == "0" and e.dxf.color == 3) or e.dxf.layer == SEC_LAYER):
            continue
        a_, b_ = e.dxf.start, e.dxf.end
        if abs(U(a_) - U(b_)) > 0.3 and abs(V(a_) - V(b_)) > 0.3:
            continue
        if all(lo - 2 <= U(q) <= hi + 2 and o - 130 <= V(q) <= o + 130 for q in (a_, b_)):
            cand.append(((U(a_), V(a_)), (U(b_), V(b_))))
    bottoms = [c for c in cand if abs(c[0][0] - bot) < 1.5 and abs(c[1][0] - bot) < 1.5
               and 15 <= abs(c[0][1] - c[1][1]) <= 45]
    if not bottoms:
        return None
    start = min(bottoms, key=lambda c: abs((c[0][1] + c[1][1]) / 2 - o) if not (min(c[0][1], c[1][1]) - 1 <= o <= max(c[0][1], c[1][1]) + 1) else -1)
    c0, c1 = sorted((start[0][1], start[1][1]))

    comp = [c for c in cand if min(c[0][1], c[1][1]) >= c0 - 60 and max(c[0][1], c[1][1]) <= c1 + 60]
    return comp, (c0, c1)


def shift_entity(e, dx, dy):
    """move an entity; a hatch keeps its pattern (ezdxf's translate() scales the pattern
    lines of a hatch with the pattern scale once more)"""
    if e.dxftype() != "HATCH":
        e.translate(dx, dy, 0)
        return
    for p in e.paths:
        if isinstance(p, PolylinePath):
            p.vertices = [(v[0] + dx, v[1] + dy, v[2] if len(v) > 2 else 0.0) for v in p.vertices]
            continue
        for ed in p.edges:
            if isinstance(ed, LineEdge):
                ed.start = Vec2(ed.start[0] + dx, ed.start[1] + dy)
                ed.end = Vec2(ed.end[0] + dx, ed.end[1] + dy)
            elif isinstance(ed, (ArcEdge, EllipseEdge)):
                ed.center = Vec2(ed.center[0] + dx, ed.center[1] + dy)
            elif isinstance(ed, SplineEdge):
                ed.control_points = [Vec2(q[0] + dx, q[1] + dy) for q in ed.control_points]
                ed.fit_points = [Vec2(q[0] + dx, q[1] + dy) for q in ed.fit_points]
    if e.seeds:
        e.seeds = [(q[0] + dx, q[1] + dy) for q in e.seeds]
    if e.pattern:
        for ln in e.pattern.lines:
            ln.base_point = Vec2(ln.base_point[0] + dx, ln.base_point[1] + dy)


def _analyze_section(sec, lines, hf_at):
    """Old symbol of a section mark (outline, slab on each side of the web) and the
    sizes of the new one. None when it is not a beam section (stair landings ...)."""
    ax, sgn = sec["ax"], sec["sgn"]
    res = _outline_of(sec, lines)
    if res is None:
        return None
    comp, (c0, c1) = res
    us = [q[0] for c in comp for q in c]
    top = min(us) if sgn > 0 else max(us)
    depth = lambda u_: (u_ - top) * sgn          # depth below the top of the highest slab
    perp = [c for c in comp if abs(c[0][0] - c[1][0]) < 0.3]

    def side(is_left):
        ls = [c for c in perp if (min(c[0][1], c[1][1]) < c0 - 2 if is_left else max(c[0][1], c[1][1]) > c1 + 2)]
        if not ls:
            return None
        ds = {round(depth(c[0][0]), 1) for c in ls}
        # end line of the slab (along the beam): gives the depth range when a face line is missing
        ends = [c for c in comp if abs(c[0][1] - c[1][1]) < 0.3 and (c[0][1] < c0 - 2 if is_left else c[0][1] > c1 + 2)]
        for c in ends:
            ds |= {round(depth(c[0][0]), 1), round(depth(c[1][0]), 1)}
        ds = sorted(ds)
        ext = min(min(c[0][1], c[1][1]) for c in ls) if is_left else max(max(c[0][1], c[1][1]) for c in ls)
        if len(ds) < 2 or not 5 <= ds[-1] - ds[0] <= 30:
            return None
        return dict(off=ds[0], t=ds[-1] - ds[0], ext=ext)
    L, R = side(True), side(False)
    if L is None and R is None:
        return None

    def P(u, v):
        d = top + sgn * u
        return (d, v) if ax == 0 else (v, d)
    # new slab thicknesses (slab on each side), beam depth
    for sd, vmid in ((L, (c0 - SEC_FLANGE / 2)), (R, (c1 + SEC_FLANGE / 2))):
        if sd is not None:
            q = P(sd["off"] + sd["t"] / 2, vmid)
            sd["t_new"] = hf_at(q[0], q[1], sec) or round(sd["t"])
    hf_main = (L or R)["t_new"]
    h_new = sec["h_set"] if sec["h_set"] is not None else max(sec["h_tpl"], hf_main + 10)
    h_new = max(h_new, max(sd["off"] + sd["t_new"] + 10 for sd in (L, R) if sd))
    bot = sec["bot"]
    v_lo = min(L["ext"] if L else c0, c0) - 1.5
    v_hi = max(R["ext"] if R else c1, c1) + 1.5
    return dict(sec=sec, ax=ax, sgn=sgn, top=top, old=(min(top, bot), max(top, bot)), c0=c0, c1=c1,
                web=(c0 + c1) / 2, L=L, R=R, h=h_new, hf=hf_main, vwin=(v_lo, v_hi), tops=[top])


def _sec_sig(m):
    """what a section mark shows (two marks with the same signature are the same drawing)"""
    sd = lambda s: None if s is None else (round(s["off"]), round(s["t_new"]))
    return m["ax"], round(m["h"]), sd(m["L"]), sd(m["R"])


def _sec_box(m, top, dims=True):
    """footprint (x0, y0, x1, y1) of a section mark drawn from 'top', dimensions included
    (dims=False: the hatched symbol only)"""
    u0, u1 = sorted((top, top + m["sgn"] * m["h"]))
    e = SEC_DIM_OFF + 12.0 if dims else 0.0
    v0 = (m["c0"] - SEC_FLANGE if m["L"] else m["c0"]) - e
    v1 = (m["c1"] + SEC_FLANGE if m["R"] else m["c1"]) + e
    return (u0, v0, u1, v1) if m["ax"] == 0 else (v0, u0, v1, u1)


def _erase_section(msp, m):
    """delete the old symbol of a section mark and its dimensions"""
    ax, (lo, hi), (v_lo, v_hi) = m["ax"], m["old"], m["vwin"]

    def inside(pts, tol=0.0):
        return all(lo - 2 - tol <= q[ax] <= hi + 2 + tol and v_lo - tol <= q[1 - ax] <= v_hi + tol for q in pts)
    c0, c1 = m["c0"], m["c1"]
    for e in list(msp.query("LINE LWPOLYLINE HATCH SOLID")):
        try:
            bb = ezbbox.extents([e], fast=True)
        except Exception:
            continue
        if not bb.has_data:
            continue
        if inside([bb.extmin, bb.extmax]):
            msp.delete_entity(e)
        elif e.dxftype() == "HATCH" and e.dxf.layer in ("0", SEC_LAYER) and not e.dxf.solid_fill and \
                lo - 4.5 <= bb.extmin[ax] and bb.extmax[ax] <= hi + 4.5 and \
                c0 - 75 <= bb.extmin[1 - ax] and bb.extmax[1 - ax] <= c1 + 75:
            msp.delete_entity(e)               # hatch of the old symbol, bigger than its outline
    for e in list(msp.query("DIMENSION")):
        if e in m["sec"]["dims"] or (e.dxf.hasattr("defpoint2") and inside([e.dxf.defpoint2, e.dxf.defpoint3])):
            msp.delete_entity(e)


def _face_lines(msp, ax, vf, fill, cuts, layer="035"):
    """Beam face line at v = vf: close the gap the old symbol left in it (fill = (u0, u1))
    and interrupt it where the new symbols are drawn (cuts = [(u0, u1), ...])."""
    U = lambda q: q[ax]
    V = lambda q: q[1 - ax]
    spans = ([fill] if fill else []) + list(cuts)
    if not spans:
        return
    lo, hi = min(s[0] for s in spans) - 3, max(s[1] for s in spans) + 3
    found = []
    for e in msp.query("LINE"):
        if e.dxf.layer != layer:
            continue
        a, b = e.dxf.start, e.dxf.end
        if abs(V(a) - V(b)) > 0.3 or abs((V(a) + V(b)) / 2 - vf) > 0.8:
            continue
        u0, u1 = sorted((U(a), U(b)))
        if u1 >= lo and u0 <= hi:
            found.append((u0, u1, e))
    if not found:
        return
    iv = sorted([u0, u1] for u0, u1, _ in found)
    merged = [iv[0]]
    for u0, u1 in iv[1:]:
        last = merged[-1]
        if u0 <= last[1] + 0.05 or (fill and last[1] >= fill[0] - 3 and u0 <= fill[1] + 3):
            last[1] = max(last[1], u1)
        else:
            merged.append([u0, u1])
    for c0_, c1_ in cuts:
        out = []
        for u0, u1 in merged:
            if u1 <= c0_ + 0.01 or u0 >= c1_ - 0.01:
                out.append([u0, u1])
                continue
            if c0_ - u0 > 0.5:
                out.append([u0, c0_])
            if u1 - c1_ > 0.5:
                out.append([c1_, u1])
        merged = out
    proto = found[0][2]
    for *_, e in found:
        if e is not proto:
            msp.delete_entity(e)
    for u0, u1 in merged:
        if u1 - u0 < 0.5:
            continue
        n = proto.copy()
        msp.add_entity(n)
        n.dxf.start = Vec3(u0, vf, 0) if ax == 0 else Vec3(vf, u0, 0)
        n.dxf.end = Vec3(u1, vf, 0) if ax == 0 else Vec3(vf, u1, 0)
    msp.delete_entity(proto)


def _draw_section(msp, m, top):
    """hatched outline and dimensions of a section mark, drawn from the slab top 'top'"""
    ax, sgn, c0, c1, L, R, h_new = m["ax"], m["sgn"], m["c0"], m["c1"], m["L"], m["R"], m["h"]

    def P(u, v):
        d = top + sgn * u
        return (d, v) if ax == 0 else (v, d)
    # (u, v): u = depth below the top of the highest slab, v = across
    va, vb = c0 - SEC_FLANGE, c1 + SEC_FLANGE
    pts = []
    if L:
        pts += [(L["off"], va), (L["off"], c0)]
    pts += [(0, c0), (0, c1)]
    if R:
        pts += [(R["off"], c1), (R["off"], vb), (R["off"] + R["t_new"], vb), (R["off"] + R["t_new"], c1)]
    pts += [(h_new, c1), (h_new, c0)]
    if L:
        pts += [(L["off"] + L["t_new"], c0), (L["off"] + L["t_new"], va)]
    clean = [pts[0]]
    for q in pts[1:]:
        if abs(q[0] - clean[-1][0]) > 1e-6 or abs(q[1] - clean[-1][1]) > 1e-6:
            clean.append(q)
    outline = [P(u, v) for u, v in clean]
    msp.add_lwpolyline(outline, close=True, dxfattribs={"layer": "0", "color": 3, "lineweight": 35})
    hat = msp.add_hatch(color=7, dxfattribs={"layer": "0"})
    hat.set_pattern_fill("ANSI31", scale=2.5, angle=0.0)
    hat.paths.add_polyline_path(outline, is_closed=True)
    # dimensions: each side its own chain, the side of a symmetric T shows the total h
    ang = 0 if ax == 0 else 90

    def chain(sd, v_edge, v_web):
        if sd is None:
            return [(0, v_web), (h_new, v_web)]
        q = [(0, v_web)] if sd["off"] > 0.5 else []
        return q + [(sd["off"], v_edge), (sd["off"] + sd["t_new"], v_edge), (h_new, v_web)]
    same = L and R and abs(L["off"] - R["off"]) < 0.5 and abs(L["t_new"] - R["t_new"]) < 0.5
    left_pts = chain(L, va, c0)
    right_pts = [(0, vb), (h_new, c1)] if same else chain(R, vb, c1)
    for pts_, vline in ((left_pts, (va if L else c0) - SEC_DIM_OFF), (right_pts, (vb if R else c1) + SEC_DIM_OFF)):
        for (u0, v0), (u1, v1) in zip(pts_, pts_[1:]):
            if abs(u1 - u0) < 0.5:
                continue
            d = msp.add_linear_dim(base=P(0, vline), p1=P(u0, v0), p2=P(u1, v1), angle=ang,
                                   dimstyle=SEC_DIMSTYLE, dxfattribs={"layer": "!Dimension"})
            d.render()


def rebuild_sections(doc, msp, sections, hf_at, depth_of, plan=None):
    """Redraw every beam section mark of the plan: a hatched T (L for edge beams,
    stepped where the slabs on the two sides are at different levels) of the
    designed depth and slab thickness, symmetric about the web, with the
    dimensions of each side at the same distance from the symbol.
    plan(marks, dropped) may move the marks along their beams: it sets m["tops"]
    (slab top of every copy of the mark to draw, [] = mark not drawn)."""
    _sec_dimstyle(doc)
    for sec in sections:
        mid = (sec["top"] + sec["bot"]) / 2
        cx, cy = (mid, sec["o"]) if sec["ax"] == 0 else (sec["o"], mid)
        sec["c"] = (cx, cy)
        sec["h_set"] = depth_of(cx, cy, sec)
        sec["h_tpl"] = 5 * math.ceil((sec["h"] - 2) / 5)
    for sec in sections:
        if sec["h_set"] is None:
            sec["h_tpl"] = max(t["h_tpl"] for t in sections if t["h_set"] is None and t["ax"] == sec["ax"]
                               and abs(t["o"] - sec["o"]) < 30)
    lines = list(msp.query("LINE"))
    marks, dropped, report = [], [], []
    for sec in sections:
        m = _analyze_section(sec, lines, hf_at)
        if m is None:
            dropped.append(sec)
        elif any(abs(k["top"] - m["top"]) < 1 and abs(k["web"] - m["web"]) < 1 and _sec_sig(k)[2:] == _sec_sig(m)[2:]
                 for k in marks):
            for k in marks:                         # the same mark twice in the template
                if abs(k["top"] - m["top"]) < 1 and abs(k["web"] - m["web"]) < 1:
                    k["h"] = max(k["h"], m["h"])
            for e in sec["dims"]:
                if e.is_alive:
                    msp.delete_entity(e)
        else:
            marks.append(m)
    for sec in dropped:
        # not a beam section (stair landings): no dimensions that could contradict the design
        ax = sec["ax"]
        lo_, hi_ = min(sec["top"], sec["bot"]) - 2, max(sec["top"], sec["bot"]) + 2
        for e in list(msp.query("DIMENSION")):
            if e in sec["dims"] or (e.dxf.hasattr("defpoint2") and all(
                    lo_ <= q[ax] <= hi_ and abs(q[1 - ax] - sec["o"]) < 60
                    for q in (e.dxf.defpoint2, e.dxf.defpoint3))):
                msp.delete_entity(e)
        report.append((round(sec["c"][0]), round(sec["c"][1]), None, None))
    if plan is not None:
        plan(marks, dropped)
    for m in marks:
        _erase_section(msp, m)
    for m in marks:                                  # parts drawn on with the mark (balcony sections)
        if m.get("attach") and len(m["tops"]) == 1 and abs(m["tops"][0] - m["top"]) > 0.5:
            ax, (lo, hi), (w0, w1) = m["ax"], m["old"], m["attach"]
            d = m["tops"][0] - m["top"]
            for e in list(msp.query("LINE LWPOLYLINE HATCH SOLID ARC")):
                try:
                    bb = ezbbox.extents([e], fast=True)
                except Exception:
                    continue
                if bb.has_data and lo - 40 <= bb.extmin[ax] and bb.extmax[ax] <= hi + 40 and \
                        w0 <= bb.extmin[1 - ax] and bb.extmax[1 - ax] <= w1 and \
                        min(bb.extmin[1 - ax], 1e9) < min(m["c0"], m["c1"]) - 1.5:
                    shift_entity(e, d if ax == 0 else 0.0, d if ax == 1 else 0.0)
    for m in marks:
        cuts = [tuple(sorted((t, t + m["sgn"] * m["h"]))) for t in m["tops"]]
        for vf in (m["c0"], m["c1"]):
            _face_lines(msp, m["ax"], vf, m["old"], cuts)
        for t in m["tops"]:
            _draw_section(msp, m, t)
            mid = t + m["sgn"] * m["h"] / 2
            c = (mid, m["web"]) if m["ax"] == 0 else (m["web"], mid)
            report.append((round(c[0]), round(c[1]), m["hf"], m["h"]))
    return report




def add_size_table(msp, x0, y0, title, rows, h=12.0):
    """Simple table (title + 2 columns) drawn with lines and texts."""
    if not rows:
        return
    w1 = max(len(r[0]) for r in rows) * 0.75 * h + 2 * h
    w2 = max(len(r[1]) for r in rows) * 0.75 * h + 2 * h
    rh = 2.0 * h
    attr = {"layer": "text", "height": h}
    msp.add_text(title, dxfattribs={"layer": "text", "height": 1.4 * h}).set_placement(
        (x0, y0 + 0.6 * h))
    y = y0
    msp.add_line((x0, y), (x0 + w1 + w2, y), dxfattribs={"layer": "text"})
    for a, b in rows:
        msp.add_text(a, dxfattribs=attr).set_placement((x0 + h, y - 1.45 * h))
        msp.add_text(b, dxfattribs=attr).set_placement((x0 + w1 + h, y - 1.45 * h))
        y -= rh
        msp.add_line((x0, y), (x0 + w1 + w2, y), dxfattribs={"layer": "text"})
    for x in (x0, x0 + w1, x0 + w1 + w2):
        msp.add_line((x, y0), (x, y), dxfattribs={"layer": "text"})


PLAN_DIMSTYLE = "RC_PLAN"


def plan_dimensions(doc, msp, X, Y, d, hall_y, room_x):
    """Replace the dimensions of the template (stretched, with overlapping texts) by
    clean chains: outer faces and axes on the four sides, the overall size, the
    secondary beams of the hall, the panels of the meeting room and the balconies."""
    if PLAN_DIMSTYLE not in doc.dimstyles:
        doc.dimstyles.new(PLAN_DIMSTYLE, dxfattribs={
            "dimtxt": 10.0, "dimasz": 5.0, "dimblk": "OBLIQUE", "dimexo": 0.0, "dimexe": 4.0, "dimgap": 2.0,
            "dimdec": 1, "dimzin": 8, "dimdsep": ord("."), "dimtad": 1, "dimtih": 0, "dimtoh": 0,
            "dimtxsty": "Standard", "dimlunit": 2, "dimtmove": 2, "dimclrt": 7, "dimclrd": 3, "dimclre": 3})
    for e in list(msp.query("DIMENSION")):
        if e.dxf.get("dimstyle", "") != SEC_DIMSTYLE:
            msp.delete_entity(e)
    t = 12.5
    attrs = {"layer": "!Dimension"}

    def chain(pts, c, horizontal, ext=15.0):
        """dimensions between consecutive points (x for horizontal chains, y for vertical)
        on the line c; short extension lines of length ext towards the plan"""
        pts = sorted(set(round(v, 1) for v in pts))
        for a, b in zip(pts, pts[1:]):
            if b - a < 1.0:
                continue
            if horizontal:
                p1, p2, base, ang = (a, c - ext), (b, c - ext), (a, c), 0
            else:
                p1, p2, base, ang = (c - ext, a), (c - ext, b), (c, a), 90
            dd = msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang, dimstyle=PLAN_DIMSTYLE, dxfattribs=attrs)
            dd.render()
    xs = [X[k] for k in ("1", "2", "3", "4", "5'", "5", "6", "7")]
    ys = [Y[k] for k in ("A", "B", "C", "D", "E")]
    x0, x1 = X["1"] - t, X["7"] + t
    y0, y1 = Y["A"] - t, Y["E"] + t
    yb = Y["A"] - t - d                      # free edge of the balconies
    # outer chains: faces + axes (inner line), overall size (outer line)
    top = Y["E"] + (T_CORE_FACE - T_Y["E"]) + 1.25 * d      # free edge of the canopy
    chain([x0] + xs + [x1], top + 40, True, ext=-15.0)
    chain([x0, x1], top + 95, True, ext=-15.0)
    chain([x0] + xs + [x1], yb - 60, True)
    chain([x0, x1], yb - 115, True)
    # left side (exhibition hall): secondary beams, axes, overall size
    chain([y0] + list(hall_y) + [y1], x0 - 45, False)
    chain([y0] + ys + [y1], x0 - 100, False)
    chain([y0, y1], x0 - 155, False)
    chain([yb, y0] + ys + [y1], x1 + 80, False, ext=-15.0)
    chain([yb, y1], x1 + 135, False, ext=-15.0)
    # meeting room: panels (5' ... 7), above the facade on axis E
    chain(room_x, y1 + 62.5, True, ext=-15.0)


def slab_labels(msp):
    """Slab numbers in circles: list of (number, position)."""
    circles = [ci for ci in msp.query("CIRCLE") if 18.0 <= ci.dxf.radius <= 21.0]
    out = []
    doc = msp.doc
    for ins in msp.query("INSERT"):                # slab label blocks
        if ins.dxf.layer != "!Hf":
            continue
        blk = doc.blocks.get(ins.dxf.name)
        if blk is None:
            continue
        no = [text_of(e).strip() for e in blk if e.dxftype() in ("TEXT", "MTEXT")
              and (text_of(e) or "").strip().isdigit()]
        if no:
            out.append((int(no[0]), Vec2(ins.dxf.insert)))
    for e in msp.query("TEXT MTEXT"):
        st = (text_of(e) or "").strip()
        if st.isdigit():
            p = Vec2(e.dxf.insert)
            if any((Vec2(ci.dxf.center) - p).magnitude < 25 for ci in circles):
                out.append((int(st), p))
    return out


def _overlap(b1, b2, gap=0.0):
    return not (b1[2] + gap <= b2[0] or b2[2] + gap <= b1[0] or b1[3] + gap <= b2[1] or b2[3] + gap <= b1[1])


BEAM_NAME_RE = re.compile(r"^\s*B\d+\s*$")
COLUMN_NAME_RE = re.compile(r"^\s*C\d+\s*$")
NAME_RE = re.compile(r"^\s*[BC]\d+\s*$")


def text_boxes(msp, skip=None):
    """Boxes of the names on the plan (beams, columns, walls, titles ...) that the
    section marks, slab labels and level marks must not cover."""
    out = []
    rings = [Vec2(ci.dxf.center) for ci in msp.query("CIRCLE") if 18.0 <= ci.dxf.radius <= 21.0]
    for e in msp.query("TEXT MTEXT"):
        s = (text_of(e) or "").strip()
        if not s or s == "f" or LEVEL_RE.match(s) or HF_RE.match(s) or (skip and skip.match(s)):
            continue
        if s.isdigit() and any((Vec2(e.dxf.insert) - c).magnitude < 25 for c in rings):
            continue                                 # number of a slab label (moves with the label)
        try:
            bb = ezbbox.extents([e], fast=True)
        except Exception:
            continue
        if bb.has_data and max(abs(bb.extmin.x), abs(bb.extmin.y), abs(bb.extmax.x), abs(bb.extmax.y)) < 1e5:
            out.append((bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y))
    return out


def beam_grid(X, Y, hall_y, room_x, y_b17):
    """Beams of the plan: along x (y, x0, x1) and along y (x, y0, y1)."""
    BX = [(Y["A"], X["1"], X["7"]), (Y["E"], X["1"], X["7"]), (Y["B"], X["3"], X["7"]), (Y["D"], X["3"], X["7"])]
    BX += [(y, X["1"], X["3"]) for y in hall_y[1:-1]]              # secondary beams of the hall (and C)
    if y_b17 is not None:
        BX.append((y_b17, X["3"], X["4"]))
    BY = [(X[k], Y["A"], Y["E"]) for k in ("1", "2", "3", "4", "7")]
    BY += [(X["5"], Y["A"], Y["B"]), (X["6"], Y["A"], Y["B"]), (X["5'"], Y["D"], Y["E"])]
    BY += [(x, Y["D"], Y["E"]) for x in room_x[1:-1]]                # beams of the meeting room
    return BX, BY


def section_marks(doc, msp, X, Y, hf_by_slab, depths, n_half, hall_y=None, room_x=None, y_b17=None):
    """Slab thickness and beam depth of every beam section mark from the design:
    depths = dict(hall=B5-B9, facade=B1/B10, B15=..., B21=...) [cm].
    Every mark is moved to the middle of its beam span (between two supports),
    one mark of a kind per span, the meeting room gets one on D and E in every
    panel. Returns dict(report, boxes): boxes = footprints of the marks."""
    # section marks inserted as blocks (meeting room, stairs): explode them so they are redrawn too
    for _ in range(3):
        ins = [e for e in msp.query("INSERT") if e.dxf.layer == SEC_LAYER and abs(e.dxf.insert.x) < 1e5]
        if not ins:
            break
        for e in ins:
            e.explode()
    labels = [(n, p) for n, p in slab_labels(msp) if n in hf_by_slab]
    half = Y["C"] - Y["A"]
    hall_beams = [Y["A"] + i * half / n_half for i in range(1, n_half)] + [Y["C"]] + \
                 [Y["C"] + i * half / n_half for i in range(1, n_half)]

    # slab fields bounded by the axes: a flange takes the thickness of the slab label in its field
    fields = [(X["1"], X["3"], Y["A"], Y["E"]), (X["5'"], X["7"], Y["D"], Y["E"]), (X["4"], X["5'"], Y["D"], Y["E"]),
              (X["4"], X["7"], Y["B"], Y["D"]), (X["4"], X["7"], Y["A"], Y["B"]),
              (X["4"], X["7"], Y["A"] - 400.0, Y["A"]), (X["3"], X["4"], Y["E"], Y["E"] + 600.0)]

    def hf_at(x, y, sec):
        if not labels:
            return None
        for fx0, fx1, fy0, fy1 in fields:
            if fx0 < x < fx1 and fy0 < y < fy1:
                inside = [(n, p) for n, p in labels if fx0 < p.x < fx1 and fy0 < p.y < fy1]
                if inside:
                    n, p = min(inside, key=lambda t: (t[1] - Vec2(x, y)).magnitude)
                    return hf_by_slab[n]
        n, p = min(labels, key=lambda t: (t[1] - Vec2(x, y)).magnitude)
        return hf_by_slab[n] if (p - Vec2(x, y)).magnitude < 700 else None

    def depth_of(x, y, sec):
        if sec["ax"] == 0 and X["1"] < x < X["3"]:                  # beams along x in the hall
            if any(abs(sec["o"] - yb) < 70 for yb in hall_beams) and depths.get("hall"):
                return depths["hall"]
            if min(abs(sec["o"] - Y["A"]), abs(sec["o"] - Y["E"])) < 70 and depths.get("facade"):
                return depths["facade"]
        if sec["ax"] == 1 and min(abs(sec["o"] - X["1"]), abs(sec["o"] - X["7"])) < 60 and depths.get("facade"):
            return depths["facade"]                                  # edge beams on axes 1 and 7
        if sec["ax"] == 1 and abs(sec["o"] - X["2"]) < 60 and depths.get("B15"):
            return depths["B15"]
        if sec["ax"] == 1 and abs(sec["o"] - X["5"]) < 60 and Y["A"] < y < Y["B"] and depths.get("B21"):
            return depths["B21"]
        return None

    boxes = []
    texts = text_boxes(msp, skip=NAME_RE)
    names = []          # names of beams (moved along the beam) and columns (to another corner) in the way
    for e in msp.query("TEXT MTEXT"):
        st = text_of(e) or ""
        if NAME_RE.match(st):
            bb = ezbbox.extents([e], fast=True)
            if not bb.has_data:
                continue
            b = (bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y)
            if any((text_of(n[0]) or "").strip() == st.strip() and max(abs(u - v) for u, v in zip(b, n[1])) < 2.0
                   for n in names):
                msp.delete_entity(e)                 # the same name twice in the template
                continue
            names.append([e, b, "beam" if BEAM_NAME_RE.match(st) else "column"])
    walls = [o for h in msp.query("HATCH") if not h.dxf.solid_fill and h.dxf.layer not in ("0", SEC_LAYER)
             for o in _hatch_polygons(h)]

    def on_wall(x, y):
        return any(o["bb"][0] <= x <= o["bb"][2] and o["bb"][1] <= y <= o["bb"][3] and _in_poly(Vec2(x, y), o["poly"])
                   for o in walls)
    if hall_y is None:
        hall_y = [Y["A"]] + hall_beams + [Y["E"]]
    BX, BY = beam_grid(X, Y, hall_y, room_x or [X["5'"], X["7"]], y_b17)

    def span(ax, web, u):
        """supports of the beam through the mark: (s0, s1) around u, or None"""
        own, other = (BX, BY) if ax == 0 else (BY, BX)
        if not any(abs(c - web) < 20 and lo - 5 <= u <= hi + 5 for c, lo, hi in own):
            return None
        sup = sorted({round(c, 1) for c, lo, hi in other if lo - 1 <= web <= hi + 1})
        i = bisect.bisect_right(sup, u)
        return (sup[i - 1], sup[i]) if 0 < i < len(sup) else None

    def in_core(m):
        """stair core: the sections there show the landings, they stay where the template has them"""
        c = sum(m["old"]) / 2
        x, y = (c, m["web"]) if m["ax"] == 0 else (m["web"], c)
        return X["3"] - 15 <= x <= X["4"] + 15 and y >= Y["D"] - 15

    def free_name(m, s0, s1, target, ideal):
        """move the names covered by the mark at 'target': a beam name along the beam,
        a column name to another corner of the column"""
        ax = m["ax"]
        b0 = _sec_box(m, target - m["sgn"] * m["h"] / 2)
        for nm in names:
            bx = nm[1]
            if not _overlap(b0, bx, 3.0):
                continue
            others = texts + ideal + boxes + [n[1] for n in names if n is not nm]
            if nm[2] == "column":
                cx, cy = (bx[0] + bx[2]) / 2, (bx[1] + bx[3]) / 2
                ax_x = min(X.values(), key=lambda v: abs(v - cx))
                ax_y = min(Y.values(), key=lambda v: abs(v - cy))
                for fx, fy in ((True, False), (False, True), (True, True)):
                    dx = 2 * ax_x - 2 * cx if fx and abs(ax_x - cx) < 80 else 0.0
                    dy = 2 * ax_y - 2 * cy if fy and abs(ax_y - cy) < 80 else 0.0
                    nb = (bx[0] + dx, bx[1] + dy, bx[2] + dx, bx[3] + dy)
                    if (dx or dy) and not any(_overlap(nb, o, 3.0) for o in others):
                        nm[0].translate(dx, dy, 0)
                        nm[1] = nb
                        break
                continue
            # a beam name moves along its own beam (written along it)
            own = 0 if (bx[2] - bx[0]) >= (bx[3] - bx[1]) else 1
            mine = own == ax and abs((bx[1] + bx[3]) / 2 - m["web"] if ax == 0 else (bx[0] + bx[2]) / 2 - m["web"]) <= 70
            for k in range(2, 42):
                d = (k // 2) * 10.0 * (1 if k % 2 else -1)
                nb = tuple(v + (d if i % 2 == own else 0.0) for i, v in enumerate(nm[1]))
                if mine and (nb[ax] < s0 + 15 or nb[ax + 2] > s1 - 15):
                    continue
                if not any(_overlap(nb, o, 3.0) for o in others):
                    nm[0].translate(d if own == 0 else 0.0, d if own == 1 else 0.0, 0)
                    nm[1] = nb
                    break

    def plan(marks, dropped):
        for sec in dropped:                          # marks left as they are (stair landings)
            lo_, hi_ = min(sec["top"], sec["bot"]), max(sec["top"], sec["bot"])
            o = sec["o"]
            boxes.append((lo_, o - 60, hi_, o + 60) if sec["ax"] == 0 else (o - 60, lo_, o + 60, hi_))
        groups = {}
        for m in marks:
            if m["ax"] == 0 and abs(m["web"] - Y["A"]) < 20:
                m["attach"] = (Y["A"] - 300.0, Y["A"] + 60.0)     # balcony section below the beam
            m["seg"] = None if in_core(m) else span(m["ax"], m["web"], sum(m["old"]) / 2)
            if m["seg"] is None:
                boxes.append(_sec_box(m, m["top"]))
                continue
            groups.setdefault((m["ax"], round(m["web"] / 10), m["seg"]), []).append(m)
        todo = []
        for (ax, _, (s0, s1)), ms in groups.items():
            kinds = []
            # the most complete reading first (a mark of the template can be found twice)
            for m in sorted(ms, key=lambda k: (-((k["L"] is not None) + (k["R"] is not None)), -k["h"])):
                if any(_sec_sig(m) == _sec_sig(k) or abs(sum(m["old"]) - sum(k["old"])) < 30 for k in kinds):
                    m["tops"] = []                   # the same mark twice in one span
                else:
                    kinds.append(m)
            kinds.sort(key=lambda k: sum(k["old"]))
            for k, m in enumerate(kinds, 1):         # one mark: middle of the span
                todo.append((m, s0 + (s1 - s0) * k / (len(kinds) + 1), s0, s1))
        if room_x:                                   # meeting room: a mark on D and E in every panel
            for yl in (Y["D"], Y["E"]):
                on = [t for t in todo if t[0]["ax"] == 0 and abs(t[0]["web"] - yl) < 20
                      and room_x[0] - 1 <= t[2] and t[3] <= room_x[-1] + 1]
                have = {(round(t[2]), round(t[3])) for t in on}
                for s0, s1 in zip(room_x, room_x[1:]):
                    wall = all(on_wall(s0 + (s1 - s0) * f, yl) for f in (0.25, 0.5, 0.75))   # SW3 ...
                    if on and (round(s0), round(s1)) not in have and not wall:
                        src = min(on, key=lambda t: abs(t[1] - (s0 + s1) / 2))[0]
                        todo.append((src, (s0 + s1) / 2, s0, s1))
        for m, *_ in todo:
            m["tops"] = []

        def offsets(ms, s0, s1):
            room = (s1 - s0) / 2 - max(m["h"] for m in ms) / 2 - 25.0     # keep clear of the supports
            return [(k // 2) * 10.0 * (1 if k % 2 else -1) for k in range(1, 2 * int(max(room, 0) // 10) + 2)]

        def on_walls(m, c):
            return any(_hits(_sec_box(m, c - m["sgn"] * m["h"] / 2, dims=False), o, 1.0) for o in walls)
        # marks of one span on parallel beams (hall bays, offices, meeting room panels) are shifted
        # together: middle of the span, or the nearest place where no beam of the group is a wall
        spans = {}
        for t in todo:
            spans.setdefault((t[0]["ax"], round(t[2], 1), round(t[3], 1)), []).append(list(t))
        def fixed_ok(m, c):
            """no wall and no name that cannot move (walls, titles, column sizes) under the mark"""
            b = _sec_box(m, c - m["sgn"] * m["h"] / 2)
            return not on_walls(m, c) and not any(_overlap(b, o, 3.0) for o in texts + boxes)
        for (ax, s0, s1), ts in spans.items():
            ds = offsets([t[0] for t in ts], s0, s1)
            d = next((d for d in ds if all(fixed_ok(t[0], t[1] + d) for t in ts)), None)
            if d is None:
                d = next((d for d in ds if not any(on_walls(t[0], t[1] + d) for t in ts)), None)
            for t in ts:
                if d is not None:
                    t[1] += d
                else:
                    t[1] += next((d_ for d_ in offsets([t[0]], s0, s1) if not on_walls(t[0], t[1] + d_)), 0.0)
        aims = [t for ts in spans.values() for t in ts]
        ideal = [_sec_box(m, t - m["sgn"] * m["h"] / 2) for m, t, _, _ in aims]
        for m, target, s0, s1 in aims:
            free_name(m, s0, s1, target, ideal)

        def free(m, c, placed):
            b = _sec_box(m, c - m["sgn"] * m["h"] / 2)
            return not any(_overlap(b, o, 3.0) for o in texts + boxes + placed + [n[1] for n in names]) \
                and not on_walls(m, c)
        for (ax, s0, s1), ts in spans.items():
            ds = offsets([t[0] for t in ts], s0, s1)
            for d in ds:
                placed = []
                for m, c, _, _ in ts:
                    if not free(m, c + d, placed):
                        break
                    placed.append(_sec_box(m, c + d - m["sgn"] * m["h"] / 2))
                else:
                    break
            else:
                d = None
            for m, c, _, _ in ts:
                if d is None:                        # each mark of the span on its own
                    d_ = next((d_ for d_ in offsets([m], s0, s1) if free(m, c + d_, [])), 0.0)
                else:
                    d_ = d
                top = c + d_ - m["sgn"] * m["h"] / 2
                m["tops"].append(top)
                boxes.append(_sec_box(m, top))

    report = rebuild_sections(doc, msp, find_sections(msp), hf_at, depth_of, plan=plan)
    return dict(report=report, boxes=boxes)


# =============================================================================
# SLAB LABELS AND LEVEL MARKS: one pattern for every slab panel
# =============================================================================
LEVEL_R = 10.0                 # level mark: radius of the circle [cm]
LEVEL_TXT = Vec2(32.7, 24.2)   # level mark: text (top centre) from the centre of the symbol
BULGE_90 = math.tan(math.radians(90.0) / 4)


def _label_clusters(doc, msp):
    """Slab labels (number in a circle, span lines, 'h =..cm'): list of dict(no, c, ents, hf)
    with c = centre of the circle and ents = everything that moves with the label."""
    out = []
    for ins in msp.query("INSERT"):                  # label blocks
        if ins.dxf.layer != "!Hf":
            continue
        blk = doc.blocks.get(ins.dxf.name)
        if blk is None:
            continue
        no = [text_of(e).strip() for e in blk if e.dxftype() in ("TEXT", "MTEXT")
              and (text_of(e) or "").strip().isdigit()]
        circ = [e for e in blk if e.dxftype() == "CIRCLE"]
        if no and circ and abs(ins.dxf.get("rotation", 0.0)) < 1e-6:
            p, c0 = ins.dxf.insert, circ[0].dxf.center
            c = Vec2(p.x + ins.dxf.xscale * c0.x, p.y + ins.dxf.yscale * c0.y)
            out.append(dict(no=int(no[0]), c=c, ents=[ins], hf=None, block=True))
    texts = list(msp.query("TEXT MTEXT"))
    lines = list(msp.query("LINE"))
    for ci in msp.query("CIRCLE"):                   # exploded labels
        r = ci.dxf.radius
        if not 18.0 <= r <= 21.0:
            continue
        c = Vec2(ci.dxf.center)
        num = [e for e in texts if (text_of(e) or "").strip().isdigit() and (Vec2(e.dxf.insert) - c).magnitude < 25]
        if not num:
            continue
        ents = [ci, num[0]]
        for ln in lines:
            a, b = Vec2(ln.dxf.start), Vec2(ln.dxf.end)
            (n_, f_) = (a, b) if (a - c).magnitude < (b - c).magnitude else (b, a)
            if abs((n_ - c).magnitude - r) < 1.5 and r + 2 < (f_ - c).magnitude < r + 32 and \
                    abs((n_ - c).normalize().det((f_ - n_).normalize())) < 0.05:
                ents.append(ln)
        out.append(dict(no=int(text_of(num[0]).strip()), c=c, ents=ents, hf=None, block=False))
    loose = [L for L in out if not L["block"]]
    fs = [e for e in texts if (text_of(e) or "").strip() == "f"]
    for h in texts:                                  # 'h =..cm' (+ subscript f) of exploded labels
        if not HF_RE.match(text_of(h) or "") or not loose:
            continue
        p = Vec2(h.dxf.insert)
        lab = min(loose, key=lambda L: (L["c"] - p).magnitude)
        if (lab["c"] - p).magnitude < 130 and lab["hf"] is None:
            lab["hf"] = h
            lab["ents"].append(h)
            lab["ents"] += [f for f in fs if (Vec2(f.dxf.insert) - p).magnitude < 15]
    return out


def _level_clusters(msp):
    """Level marks: text '+2.80' and its symbol (circle, two black quarters, cross).
    Returns (marks, orphans): marks = [dict(text, value, c, ents)] with c = centre of
    the symbol, orphans = [dict(c, ents)] symbols without a text."""
    circles = [ci for ci in msp.query("CIRCLE") if 9.0 <= ci.dxf.radius <= 11.0]
    hatches = []
    for h in msp.query("HATCH"):
        if h.dxf.solid_fill:
            bb = ezbbox.extents([h], fast=True)
            if bb.has_data and bb.extmax.x - bb.extmin.x < 25:
                hatches.append((h, Vec2((bb.extmin + bb.extmax) / 2)))
    lines = list(msp.query("LINE"))

    def cross(c, tol):
        """the lines of the cross through c"""
        out = []
        for ln in lines:
            a, b = Vec2(ln.dxf.start), Vec2(ln.dxf.end)
            mid = (a + b) / 2
            if (a - b).magnitude > 62 or abs(mid.x - c.x) > 25 or abs(mid.y - c.y) > 25:
                continue
            if (abs(a.x - b.x) < 0.3 and abs(a.x - c.x) < tol) or (abs(a.y - b.y) < 0.3 and abs(a.y - c.y) < tol):
                out.append(ln)
        return out
    syms = []
    for ci in circles:
        c = Vec2(ci.dxf.center)
        hs = [h for h, hc in hatches if (hc - c).magnitude < 3.0]
        if hs:
            syms.append(dict(c=c, ents=[ci] + hs + cross(c, 0.6)))
    marks, used = [], set()
    for t in msp.query("TEXT MTEXT"):
        s = (text_of(t) or "").strip()
        if not LEVEL_RE.match(s):
            continue
        guess = Vec2(t.dxf.insert) - LEVEL_TXT
        cand = [sy for sy in syms if id(sy) not in used and (sy["c"] - guess).magnitude < 25]
        if cand:
            sy = min(cand, key=lambda k: (k["c"] - guess).magnitude)
            used.add(id(sy))
            marks.append(dict(text=t, value=s, c=sy["c"], ents=sy["ents"]))
        else:                                    # text without its symbol (lines only, if any)
            marks.append(dict(text=t, value=s, c=guess, ents=cross(guess, 10.0)))
    return marks, [sy for sy in syms if id(sy) not in used]


def _draw_level_symbol(msp, c):
    """circle with the upper left and lower right quarters filled, cross through the centre"""
    cx, cy, r = c.x, c.y, LEVEL_R
    att = {"layer": "0", "color": 7, "lineweight": 20}
    msp.add_circle((cx, cy), r, dxfattribs=att)
    h = msp.add_hatch(color=7, dxfattribs={"layer": "0"})
    h.paths.add_polyline_path([(cx - r, cy, 0), (cx, cy, 0), (cx, cy + r, BULGE_90)], is_closed=True)
    h.paths.add_polyline_path([(cx, cy, 0), (cx, cy - r, BULGE_90), (cx + r, cy, 0)], is_closed=True)
    att["lineweight"] = 25
    msp.add_line((cx, cy - 2 * r), (cx, cy + 2 * r), dxfattribs=att)
    msp.add_line((cx - 2 * r, cy), (cx + 2 * r, cy), dxfattribs=att)


def _level_box(c):
    return (c.x - 2 * LEVEL_R, c.y - 2 * LEVEL_R, c.x + LEVEL_TXT.x + 31.0, c.y + LEVEL_TXT.y + 1.0)


def _hatch_polygons(h):
    """outlines of a hatch as obstacles: dict(bb, poly) per boundary path"""
    from ezdxf import path as ezpath
    out = []
    try:
        paths = ezpath.from_hatch(h)
    except Exception:
        return out
    for pa in paths:
        try:
            pts = [Vec2(q) for q in pa.flattening(2.0)]
        except Exception:
            continue
        if len(pts) < 3:
            continue
        xs, ys = [q.x for q in pts], [q.y for q in pts]
        if max(map(abs, xs + ys)) < 1e5:
            out.append(dict(bb=(min(xs), min(ys), max(xs), max(ys)), poly=pts))
    return out


def _bb(o):
    return o["bb"] if isinstance(o, dict) else o


def _seg_hits_rect(p, q, x0, y0, x1, y1):
    """segment p-q crosses or lies in the rectangle (Liang-Barsky)"""
    dx, dy = q.x - p.x, q.y - p.y
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p.x - x0), (dx, x1 - p.x), (-dy, p.y - y0), (dy, y1 - p.y)):
        if abs(pp) < 1e-12:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return True


def _in_poly(c, poly):
    inside_, j = False, len(poly) - 1
    for i in range(len(poly)):
        a, b = poly[i], poly[j]
        if (a.y > c.y) != (b.y > c.y) and c.x < (b.x - a.x) * (c.y - a.y) / (b.y - a.y) + a.x:
            inside_ = not inside_
        j = i
    return inside_


def _hits(b, o, gap=0.0):
    """box b overlaps the obstacle o (a box or a hatch outline)"""
    if not isinstance(o, dict):
        return _overlap(b, o, gap)
    if not _overlap(b, o["bb"], gap):
        return False
    x0, y0, x1, y1 = b[0] - gap, b[1] - gap, b[2] + gap, b[3] + gap
    poly = o["poly"]
    if any(_seg_hits_rect(poly[i - 1], poly[i], x0, y0, x1, y1) for i in range(len(poly))):
        return True
    return _in_poly(Vec2((x0 + x1) / 2, (y0 + y1) / 2), poly)


def slab_panels(X, Y, hall_y, room_x, y_b17):
    """Slab panels whose label and level mark are laid out: (x0, x1, y0, y1, group);
    the panels of a group get the same arrangement."""
    P = []
    for xa, xb in ((X["1"], X["2"]), (X["2"], X["3"])):            # hall, one-way slabs (span along y)
        P += [(xa, xb, ya, yb, "hall") for ya, yb in zip(hall_y, hall_y[1:])]
    P += [(xa, xb, Y["D"], Y["E"], "room") for xa, xb in zip(room_x, room_x[1:])]   # span along x
    P += [(xa, xb, Y["A"], Y["B"], "office") for xa, xb in ((X["4"], X["5"]), (X["5"], X["6"]), (X["6"], X["7"]))]
    P.append((X["4"], X["7"], Y["B"], Y["D"], "corridor"))
    P.append((X["4"], X["5'"], Y["D"], Y["E"], "lobby"))          # slab next to the meeting room
    if y_b17 is not None:
        P.append((X["3"], X["4"], y_b17, Y["B"], "entrance"))      # slab over the entrance
    P.append((X["3"], X["4"], Y["B"], Y["D"], "front"))           # hall in front of the stairs (level only)
    return P


def annotate_panels(doc, msp, X, Y, hall_y, room_x, y_b17, boxes):
    """Slab labels and level marks of every slab panel on one pattern:
         one-way slabs of the hall / corridor : label at 1/4, level mark at 3/4 of the length,
                                                the section marks of the beams in the middle
         one-way slabs of the meeting room   : label at 3/4, level mark at 1/4 of the height
         two-way slabs                       : label in the centre, level mark above right of it
    The panels of a group are shifted together when a beam name, a wall or a section
    mark is in the way. Panels without a level mark get one (same level as the other
    panels of the group); level symbols without a text and loose template lines in
    the panels are removed."""
    labels = _label_clusters(doc, msp)
    levels, orphans = _level_clusters(msp)
    panels = slab_panels(X, Y, hall_y, room_x, y_b17)
    obst = list(boxes) + text_boxes(msp)
    for h in msp.query("HATCH"):                     # walls, columns, sections left as they are
        if not h.dxf.solid_fill:
            obst += _hatch_polygons(h)
    for e in msp.query("LINE"):                      # outlines of the sections left as they are
        if (e.dxf.layer == "0" and e.dxf.color == 3) or e.dxf.layer == SEC_LAYER:
            a, b = e.dxf.start, e.dxf.end
            obst.append((min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y)))

    def inside(p, P, m=5.0):
        return P[0] + m < p.x < P[1] - m and P[2] + m < p.y < P[3] - m
    in_panel = lambda p: any(inside(p, P) for P in panels)
    for L in labels:                                 # annotations that stay (stairs, canopy ...)
        if not in_panel(L["c"]):
            bb = ezbbox.extents(L["ents"], fast=True)
            if bb.has_data:
                obst.append((bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y))
    for lv in levels:
        if not in_panel(lv["c"]):
            obst.append(_level_box(lv["c"]))
    for sy in orphans:                               # level symbols without a text
        if in_panel(sy["c"]):
            for e in sy["ents"]:
                if e.is_alive:
                    msp.delete_entity(e)
    # loose outline pieces of the template in the middle of the panels
    segs = [(Vec2(e.dxf.start), Vec2(e.dxf.end), e) for e in msp.query("LINE")]
    verts = [Vec2(q[0], q[1]) for pl in msp.query("LWPOLYLINE") for q in pl.get_points("xy")]
    for a, b, e in segs:
        if e.dxf.layer != "0" or e.dxf.color != 3 or (a - b).magnitude > 60 or \
                not any(inside((a + b) / 2, P, 80.0) for P in panels):
            continue
        touch = [q for a2, b2, e2 in segs if e2 is not e and not ((a2 - a).magnitude < 0.1 and (b2 - b).magnitude < 0.1)
                 and not ((a2 - b).magnitude < 0.1 and (b2 - a).magnitude < 0.1) for q in (a2, b2)
                 if min((q - a).magnitude, (q - b).magnitude) < 1.0]
        if not touch and not any(min((q - a).magnitude, (q - b).magnitude) < 1.0 for q in verts) and e.is_alive:
            msp.delete_entity(e)
    values = {}
    for P in panels:
        for lv in levels:
            if inside(lv["c"], P):
                values.setdefault(P[4], []).append(lv["value"])
    proto = levels[0]["text"] if levels else None
    grids = {}

    def grid(w):
        if w not in grids:
            grids[w] = sorted(((dx, dy) for dx in range(-200, 201, 10) for dy in range(-200, 201, 10)),
                              key=lambda t: ((t[0] * w[0]) ** 2 + (t[1] * w[1]) ** 2, abs(t[1]), t[0]))
        return grids[w]

    def fits(b, P, near):
        return (b[0] >= P[0] + 17.5 and b[2] <= P[1] - 17.5 and b[1] >= P[2] + 17.5 and b[3] <= P[3] - 17.5
                and not any(_hits(b, o, 4.0) for o in near))

    def place_group(items, w):
        """items = [(box_at, pref, P)]: positions with one common offset from the preferred
        places (else each item its own nearest free place)"""
        near = []
        for _, _, P in items:
            near.append([o for o in obst if _overlap(_bb(o), (P[0] - 10, P[2] - 10, P[1] + 10, P[3] + 10))])
        for dx, dy in grid(w):
            res = []
            for (box_at, pref, P), nb in zip(items, near):
                q = pref + Vec2(dx, dy)
                b = box_at(q)
                if not fits(b, P, nb):
                    break
                res.append((q, b))
            else:
                return res
        out = []
        for (box_at, pref, P), nb in zip(items, near):
            for dx, dy in grid(w):
                q = pref + Vec2(dx, dy)
                if fits(box_at(q), P, nb):
                    break
            else:
                q = pref
            out.append((q, box_at(q)))
        return out

    def prefs(P):
        x0, x1, y0, y1, g = P
        w, h = x1 - x0, y1 - y0
        xc, yc = (x0 + x1) / 2, (y0 + y1) / 2
        if g in ("hall", "corridor"):
            return Vec2(x0 + w / 4, yc), Vec2(x0 + 3 * w / 4, yc), (1.0, 3.0)
        if g == "room":
            return Vec2(xc, y0 + 3 * h / 4), Vec2(xc, y0 + h / 4), (3.0, 1.0)
        if g == "front":
            return None, Vec2(xc, yc), (1.0, 1.0)
        return Vec2(xc, yc), Vec2(xc + 75.0, yc + 55.0), (1.0, 1.0)
    groups = {}
    for P in panels:
        groups.setdefault(P[4], []).append(P)
    # slab labels
    for g, Ps in groups.items():
        items, labs = [], []
        for P in Ps:
            pl, _, w = prefs(P)
            L = next((L for L in labels if inside(L["c"], P)), None)
            if pl is None or L is None:
                continue
            bb = ezbbox.extents(L["ents"], fast=True)
            rel = (bb.extmin.x - L["c"].x, bb.extmin.y - L["c"].y, bb.extmax.x - L["c"].x, bb.extmax.y - L["c"].y)
            items.append((lambda p, r=rel: (p.x + r[0], p.y + r[1], p.x + r[2], p.y + r[3]), pl, P))
            labs.append(L)
        if not items:
            continue
        for L, (q, b) in zip(labs, place_group(items, prefs(Ps[0])[2])):
            dv = q - L["c"]
            for e in L["ents"]:
                e.translate(dv.x, dv.y, 0)
            L["c"] = q
            obst.append(b)
            hf = L["hf"]
            if hf is not None and not any((text_of(e) or "").strip() == "f" for e in L["ents"]):
                rot = hf.dxf.get("rotation", 0.0)
                off = Vec2(6.6, 7.8) if abs(rot - 90.0) < 1 else Vec2(7.8, -6.6)
                f = msp.add_text("f", height=9.19, rotation=rot,
                                 dxfattribs={"layer": hf.dxf.layer, "style": hf.dxf.get("style", "Standard")})
                f.set_placement(Vec2(hf.dxf.insert) + off)
    # level marks
    for g, Ps in groups.items():
        vals = values.get(g, [])
        items, levs_of = [], []
        for P in Ps:
            _, pv, w = prefs(P)
            levs = [lv for lv in levels if inside(lv["c"], P)]
            if not levs and not vals:
                continue
            items.append((_level_box, pv, P))
            levs_of.append(levs)
        if not items or proto is None:
            continue
        common = max(set(vals), key=vals.count) if vals else None
        for levs, (q, b) in zip(levs_of, place_group(items, prefs(Ps[0])[2])):
            obst.append(b)
            for lv in levs:
                for e in lv["ents"]:
                    if e.is_alive:
                        msp.delete_entity(e)
            for lv in levs[1:]:
                if lv["text"].is_alive:
                    msp.delete_entity(lv["text"])
            t = levs[0]["text"] if levs else None
            if t is None:
                t = proto.copy()
                msp.add_entity(t)
                set_text(t, common)
            if t.dxftype() == "MTEXT":
                t.dxf.attachment_point = 2                 # top centre
                t.dxf.insert = Vec3(q.x + LEVEL_TXT.x, q.y + LEVEL_TXT.y, 0)
            else:
                t.dxf.halign, t.dxf.valign = 1, 3          # top centre
                t.dxf.insert = t.dxf.align_point = Vec3(q.x + LEVEL_TXT.x, q.y + LEVEL_TXT.y, 0)
            _draw_level_symbol(msp, q)


# =============================================================================
# MAIN
# =============================================================================
def redraw(template_path, a, b, c, d, level, hf_by_slab=None, size_rows=None, beam_depths=None):
    """Redraw the template for the new grid. Returns a Layout (doc not saved)."""
    warnings: list[str] = []
    X, Y = new_grid(a, b, c, d)
    doc = ezdxf.readfile(template_path)
    msp = doc.modelspace()

    # ---------------------------------------------------------- slab checks
    half = Y["C"] - Y["A"]
    n_half = max(1, math.ceil(ONE_WAY_LIMIT * half / a - 1e-9))
    hall_ratio = a / (half / n_half)
    if n_half != T_HALL_PANELS_PER_HALF:
        raise FormworkError(
            f"Exhibition hall needs {n_half} panels per half (template has "
            f"{T_HALL_PANELS_PER_HALF}); not supported by this template.")
    n_room, q, src = plan_room(X, Y)
    room_ratio = (Y["E"] - Y["D"]) / ((X["7"] - X["5'"]) / n_room)
    room_ratio_old = (Y["E"] - Y["D"]) / ((X["7"] - X["5'"]) / T_ROOM_SLABS_OLD)

    # ---------------------------------------------------------- global maps
    xo = [T_X[k] for k in T_X]
    xn = [X[k] for k in T_X]
    xr = [R_AXIS if k != "5'" else 50.0 for k in T_X]
    # stair: wall 3 | flight d | 20 gap | flight d | wall 4 -> only the
    # flights change with d, the gap between them stays 20 cm
    xo.append(T_STAIR_GAP)
    xn.append(X["3"] + (T_STAIR_GAP - T_X["3"]) + (d - T_D))
    xr.append(12.0)
    FX = StretchMap(xo, xn, xr)

    hall_new = [snap(Y["A"] + i * half / n_half, YB) for i in range(1, n_half)] + \
               [snap(Y["C"] + i * half / n_half, YB) for i in range(1, n_half)]
    yo = [T_Y["A"], T_HALL_BEAMS[0], T_HALL_BEAMS[1], T_Y["B"], T_Y["C"],
          T_Y["D"], T_HALL_BEAMS[2], T_HALL_BEAMS[3], T_Y["E"]]
    yn = [Y["A"], hall_new[0], hall_new[1], Y["B"], Y["C"],
          Y["D"], hall_new[2], hall_new[3], Y["E"]]
    yr = [R_EDGE, R_BEAM, R_BEAM, R_BD, R_EDGE, R_BD, R_BEAM, R_BEAM, R_EDGE]
    # balconies (free edge d from the face of the wall on axis A) and the
    # canopy slab over the entrance (1.25 d from the wall of the stair core)
    core = Y["E"] + (T_CORE_FACE - T_Y["E"])
    yo += [T_BALCONY_EDGE, T_CORE_FACE, T_CANOPY_EDGE]
    yn += [Y["A"] - 12.5 - d, core, core + 1.25 * d]
    yr += [15.0, 30.0, 15.0]
    FY = StretchMap(yo, yn, yr)

    GLOBAL = Placement("global", FX)

    # ---------------------------------------------------------- meeting room
    groups, beams, edge_lines = collect_room(msp)
    room_items, pl_info = room_placements(groups, beams, q, src, FY, msp)

    # web positions of the section marks on axis E (to break the face line)
    y_web0, y_web1 = T_Y["E"] - 47.5, T_Y["E"] - 12.7
    webs = []
    for e, pl, s in room_items:
        if e.dxftype() == "LINE" and pl.name.startswith("panel"):
            st, en = e.dxf.start, e.dxf.end
            if abs(st.x - en.x) < 0.05 and abs(min(st.y, en.y) - y_web0) < 0.3 \
                    and max(st.y, en.y) >= y_web1:
                webs.append(e)

    room_set = {id(it[0]) for it in room_items}
    items = [(e, GLOBAL, e) for e in msp if id(e) not in room_set]
    items += room_items

    # ---------------------------------------------------------- rigid clusters
    member = build_clusters(items, FY)

    # ---------------------------------------------------------- transform
    shared = [cl for pl, kind, j, k, cp in pl_info if not cp for cl in pl.clusters]
    mover = Mover(doc, FY, shared)
    for idx, (e, pl, s) in enumerate(items):
        mover.move(e, pl, member.get(idx))

    # ---------------------------------------------------------- face line on E
    eline = edge_lines.get(round(T_Y["E"] - 12.5, 1))
    if eline is not None and webs:
        xs = sorted(e.dxf.start.x for e in webs)
        gaps, i = [], 0
        while i < len(xs):
            if i + 1 < len(xs) and xs[i + 1] - xs[i] < 12:
                gaps.append((xs[i], xs[i + 1])); i += 2
            else:
                i += 1
        x_from, x_to = eline.dxf.start.x, eline.dxf.end.x
        segs, cur = [], x_from
        for g0, g1 in gaps:
            if g0 > cur:
                segs.append((cur, g0))
            cur = max(cur, g1)
        segs.append((cur, x_to))
        for s0, s1 in segs:
            cp = eline.copy(); msp.add_entity(cp)
            cp.dxf.start = Vec3(s0, eline.dxf.start.y)
            cp.dxf.end = Vec3(s1, eline.dxf.start.y)
        msp.delete_entity(eline)

    # ---------------------------------------------------------- numbering
    extra = n_room - T_ROOM_SLABS_OLD
    # slab labels inside the meeting room
    for pl, kind, j, k, cp in pl_info:
        if kind != "panel":
            continue
        for e, p2, s in room_items:
            if p2 is not pl:
                continue
            st = text_of(e)
            if st is not None and st.strip().isdigit():
                v = int(st.strip())
                if T_ROOM_SLAB_FIRST <= v < T_ROOM_SLAB_FIRST + T_ROOM_SLABS_OLD:
                    set_text(e, str(T_ROOM_SLAB_FIRST - 1 + j))
    # following slab numbers (17..21 -> +extra)
    circles = [ci for ci in msp.query("CIRCLE") if 18.0 <= ci.dxf.radius <= 21.0]
    room_ids = {id(it[0]) for it in room_items}
    if extra:
        for e in msp.query("TEXT MTEXT"):
            if id(e) in room_ids:
                continue
            st = (text_of(e) or "").strip()
            if not st.isdigit():
                continue
            v = int(st)
            if not (T_ROOM_SLAB_FIRST + T_ROOM_SLABS_OLD <= v <= T_LAST_SLAB):
                continue
            p = Vec2(e.dxf.insert)
            if any((Vec2(ci.dxf.center) - p).magnitude < 25 for ci in circles):
                set_text(e, str(v + extra))
    # beam labels: copies of a beam get new numbers, later beams are shifted
    dup_labels, base = [], None
    for pl, kind, j, k, cp in pl_info:
        if kind != "beam":
            continue
        for e, p2, s in room_items:
            if p2 is pl and is_B_label(e):
                if cp:
                    dup_labels.append(e)
                elif k == 2:
                    base = int(text_of(e).strip()[1:])
    if dup_labels and base is not None:
        shift = len(dup_labels)
        dup_ids = {id(x) for x in dup_labels}
        for e in msp.query("TEXT MTEXT"):
            if id(e) in dup_ids or not is_B_label(e):
                continue
            v = int(text_of(e).strip()[1:])
            if v > base:
                set_text(e, f"B{v + shift}")
        for i, e in enumerate(dup_labels, 1):
            set_text(e, f"B{base + i}")

    # levels, title, shear walls
    for e in msp.query("TEXT MTEXT"):
        st = text_of(e) or ""
        m = LEVEL_RE.match(st)
        if m:
            set_text(e, new_level_text(m, level, warnings))
            continue
        if "Formwork at level" in st:
            set_text(e, re.sub(r"\+\s*\d+[.,]\d+", f"+{level:.2f}", st))
            continue
        m = re.fullmatch(r"\s*(SW\d+)\s+(\d+(?:[.,]\d+)?)/(\d+(?:[.,]\d+)?)\s*", st)
        if m and m.group(1) in T_SHEAR_WALLS:
            direc, p0, p1 = T_SHEAR_WALLS[m.group(1)]
            f = FX if direc == "x" else FY
            gb = XB if direc == "x" else YB
            L = abs(snap(f(p1)[0], gb) - snap(f(p0)[0], gb))
            n1, n2 = m.group(2), m.group(3)
            if float(n1.replace(",", ".")) >= float(n2.replace(",", ".")):
                n1 = fmt_num(L, ".")
            else:
                n2 = fmt_num(L, ".")
            set_text(e, f"{m.group(1)} {n1}/{n2}")

    # slab thicknesses from the calculations, table of element sizes
    if hf_by_slab:                        # keys = final slab numbers
        update_slab_thickness(doc, msp, hf_by_slab)
        hall_y_ = [Y["A"]] + hall_new[:n_half - 1] + [Y["C"]] + hall_new[n_half - 1:] + [Y["E"]]
        y_b17 = snap(FY(T_B17_Y)[0], YB)
        marks = section_marks(doc, msp, X, Y, hf_by_slab, beam_depths or {}, n_half,
                              hall_y=hall_y_, room_x=q, y_b17=y_b17)
        annotate_panels(doc, msp, X, Y, hall_y_, q, y_b17, marks["boxes"])
        plan_dimensions(doc, msp, X, Y, d, hall_y_, q)
    if size_rows:
        add_size_table(msp, X["7"] + 400.0, Y["E"] + 20.0,
                       "Element sizes (from the calculations)", size_rows)

    # ---------------------------------------------------------- header
    try:
        ext = ezbbox.extents(msp, fast=True)
        doc.header["$EXTMIN"] = ext.extmin
        doc.header["$EXTMAX"] = ext.extmax
    except Exception:
        pass

    # ---------------------------------------------------------- report
    rep = [f"a={a:g}  b={b:g}  c={c:g}  d={d:g} cm   level +{level:.2f}",
           f"Exhibition hall (1-3 / A-E): {2 * n_half} panels per bay, {a:g} x {half / n_half:.1f} cm,"
           f" l_long / l_short = {hall_ratio:.2f} -> {'one-way' if hall_ratio >= ONE_WAY_LIMIT else 'TWO-WAY'}"]
    w_room = (X["7"] - X["5'"]) / n_room
    rep.append(f"Meeting room (5'-7 / D-E): {n_room} panels {w_room:.1f} x {Y['E'] - Y['D']:g} cm, "
               f"ratio = {room_ratio:.2f} -> {'one-way' if room_ratio >= ONE_WAY_LIMIT else 'TWO-WAY'}"
               + (f" (template: {T_ROOM_SLABS_OLD} panels, ratio {room_ratio_old:.2f})"
                  if n_room != T_ROOM_SLABS_OLD else ""))
    if extra > 0:
        rep.append(f"{extra} slab(s) added -> slabs {T_ROOM_SLAB_FIRST}..{T_ROOM_SLAB_FIRST + n_room - 1};"
                   f" later slabs renumbered (+{extra})")
    elif extra < 0:
        rep.append(f"{-extra} slab(s) removed -> slabs {T_ROOM_SLAB_FIRST}..{T_ROOM_SLAB_FIRST + n_room - 1};"
                   f" later slabs renumbered ({extra})")

    hall_y = [Y["A"]] + hall_new[:n_half - 1] + [Y["C"]] + hall_new[n_half - 1:] + [Y["E"]]
    return Layout(doc=doc, X=X, Y=Y, hall_y=hall_y, room_x=q, n_half=n_half, n_room=n_room,
                  FX=FX, FY=FY, level=level, report=rep,
                  warnings=list(dict.fromkeys(warnings)))


def render_png(doc, path, box=None, width_px=3000):
    """Black-on-white preview of the model space (needs matplotlib)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import (Configuration, BackgroundPolicy,
                                             ColorPolicy)
    if box is None:
        ext = ezbbox.extents(doc.modelspace(), fast=True)
        box = (ext.extmin.x - 50, ext.extmin.y - 50, ext.extmax.x + 50, ext.extmax.y + 50)
    x0, y0, x1, y1 = box
    w = width_px / 100
    fig = plt.figure(figsize=(w, w * (y1 - y0) / (x1 - x0)), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                        color_policy=ColorPolicy.BLACK)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(
        doc.modelspace())
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("auto")
    fig.set_size_inches(w, w * (y1 - y0) / (x1 - x0))   # the drawing frontend resets the size
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)
