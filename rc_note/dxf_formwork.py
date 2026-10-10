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
    s = f"{nv:.2f}".replace(".", sep)
    return "+" + s


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


# =============================================================================
# MAIN
# =============================================================================
def redraw(template_path, a, b, c, d, level, hf_by_slab=None, size_rows=None):
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
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)
