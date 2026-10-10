# -*- coding: utf-8 -*-
"""
rebar.py - reinforcement of the slabs for the drawings
======================================================

Turns the results of the calculations (bar diameter and spacing in every
designed section of sections I-IV and VII) into bar positions placed on the
real geometry of the formwork plan:

  BR  bottom main bars          DR  bottom distribution bars
  TR  top bars (supports, edges, cantilevers)
  AR  top assembly / distribution bars under the TR bars

Every position gets a bar shape (lengths of the straight parts in cm), a
number of bars and one or more "representative" bars on the plan (the usual
way of drawing slab reinforcement: one bar of each group is drawn with its
shape and label, a range line shows over which width the group is spread).
Bars with the same mark, diameter, shape and spacing share one position
number in the bar schedule.

Detailing rules (EC2 9.3, course practice):
  * cover c_nom = 25 mm; first bar 5 cm from the face of the support
  * bottom bars run into the supports up to the far face minus the cover
    (lapped over interior supports, anchored at end supports)
  * top bars over interior supports: 0.3·l beyond the face of the support
    (two-way slabs 0.25·l), ends bent down to the bottom cover
  * top bars at monolithic end supports: A_s3 ≥ max(0.25·A_s,span; A_s,min;
    5Φ8/m), 0.2·l from the face, 15 cm hook into the support
  * edges parallel to the span: constructive top bars 5Φ8/m, 0.2·l
  * distribution bars: ≥ 0.2·A_s and ≥ 3Φ8/m (from the calculation)
  * assembly bars under the top bars Φ6/25 cm (Φ8 for slabs ≥ 18 cm)
  * bars longer than 12 m are split with a lap of 50Φ
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .design import BAR_AREA, slab_bars
from .engine import fmt

COVER = 2.5          # cm, c_nom = 25 mm
EDGE_GAP = 5.0       # cm, first / last bar from the face of the support
AR_SPACING = 25.0    # cm, assembly bars under the top bars
MAX_BAR = 1200.0     # cm, longest bar
HOOK = 15.0          # cm, hook of top bars into an edge support
WALL = 25.0          # cm, walls and ordinary beams
MASS = {d: 7850e-6 * a for d, a in BAR_AREA.items()}      # kg/m


def ceil5(v):
    return 5.0 * math.ceil(v / 5.0 - 1e-9)


def cm(v):
    """Cut length in whole cm (rounded down - bars stay inside the cover)."""
    return float(math.floor(v + 1e-6))


def count(length, s):
    """Number of bars at spacing s over a width 'length' (clear)."""
    return max(2, int(math.floor((length - 2 * EDGE_GAP) / s + 1e-6)) + 1)


def sp(s_mm):
    return s_mm / 10.0


# ============================================================================
# data
# ============================================================================
@dataclass
class BarType:
    """One position of the bar schedule."""
    mark: str               # BR / DR / TR / AR
    phi: int                # mm
    segs: tuple             # cm - lengths of the straight parts of the shape
    s: float                # cm - spacing (0 = not regular)
    face: str               # "bottom" / "top"
    pos: int = 0
    n_total: int = 0
    where: list = field(default_factory=list)

    @property
    def L(self):
        return sum(self.segs)

    def key(self):
        return (self.mark, self.phi, tuple(round(x, 1) for x in self.segs), round(self.s, 2), self.face)

    def label(self, n):
        s = f"/{fmt(self.s)}" if self.s else ""
        return f"N{self.pos} {self.mark} {n}%%c{self.phi}x{fmt(self.L)}{s}"


@dataclass
class Rep:
    """A representative bar on the plan."""
    bar: BarType
    n: int
    p0: tuple                    # start of the main part (x, y)
    p1: tuple                    # end of the main part
    legs: tuple = (0.0, 0.0)     # legs at p0 / p1 (drawn folded into the plan)
    side: int = 1                # side of the legs / length texts (+1 left of p0->p1)
    rng: tuple = None            # ((x, y), (x, y)) range line
    ar: tuple = None             # (BarType, n) assembly bars shown as dots
    lab_t: float = 0.5           # position of the label along the bar (0..1)
    slab: str = ""


class Schedule:
    def __init__(self):
        self.types = {}
        self.order = []

    def get(self, mark, phi, segs, s, face, where):
        b = BarType(mark, int(phi), tuple(float(x) for x in segs), float(s), face)
        k = b.key()
        if k not in self.types:
            self.types[k] = b
            self.order.append(b)
        b = self.types[k]
        if where and where not in b.where:
            b.where.append(where)
        return b

    def number(self):
        i = 0
        for face in ("bottom", "top"):
            for b in self.order:
                if b.face == face:
                    i += 1
                    b.pos = i

    def rows(self, face=None):
        return [b for b in sorted(self.order, key=lambda b: b.pos) if face in (None, b.face)]

    @staticmethod
    def totals(bars):
        """{phi: (length m, mass kg)} and total mass."""
        out = {}
        for b in bars:
            Lm = b.L * b.n_total / 100.0
            l0, m0 = out.get(b.phi, (0.0, 0.0))
            out[b.phi] = (l0 + Lm, m0 + Lm * MASS[b.phi])
        return dict(sorted(out.items())), sum(v[1] for v in out.values())


@dataclass
class SlabPlan:
    bottom: list
    top: list
    schedule: Schedule
    notes: list
    hf: dict                   # slab number -> thickness [cm]
    texts: list = field(default_factory=list)   # (x, y, text, height, rotation)


# ============================================================================
# detailing helpers (per metre)
# ============================================================================
def edge_top_bars(r_span, h_cm):
    """Top bars at a monolithic end support: max(0.25·A_s; A_s,min; 5Φ8/m)."""
    As3 = max(0.25 * r_span["As_prov"], r_span.get("As_min", 0.0), 5 * BAR_AREA[8])
    _, _, phi, s = slab_bars(As3, h_cm * 10, dias=(8, 10, 12))
    return phi, sp(s)


def constructive_top(h_cm):
    _, _, phi, s = slab_bars(5 * BAR_AREA[8], h_cm * 10, dias=(8, 10))
    return phi, sp(s)


def dist_bars(As_main, h_cm):
    As_d = max(0.2 * As_main, 3 * BAR_AREA[8])
    _, _, phi, s = slab_bars(As_d, h_cm * 10, s_max=min(3 * h_cm * 10, 400), dias=(6, 8, 10))
    return phi, sp(s)


def ar_phi(h_cm):
    return 8 if h_cm >= 18 else 6


def n_ar(straight):
    return max(2, int(math.floor((straight - 2 * EDGE_GAP) / AR_SPACING + 1e-6)) + 1)


def split_run(a, b, phi, anchors=(0.0, 0.0), joints=()):
    """Split a run of bars from a to b (clear) into pieces at the given joint
    coordinates (lap 50Φ centred on each joint). anchors: extension beyond a
    and b into the supports. Returns [(start, end)] (bar ends)."""
    lap = max(ceil5(50 * phi / 10.0), 30.0)
    pts = [a - anchors[0]] + list(joints) + [b + anchors[1]]
    out = []
    for i in range(len(pts) - 1):
        s0 = pts[i] - (lap / 2 if i > 0 else 0.0)
        s1 = pts[i + 1] + (lap / 2 if i < len(pts) - 2 else 0.0)
        out.append((s0, s1))
    return out


# ============================================================================
# slab thicknesses (for the labels of the formwork plan)
# ============================================================================
def slab_thickness(P):
    """Slab number -> thickness [cm] from the results of the calculations."""
    G, res = P.G, P.res
    hf = {}
    if "II" in res:
        n = 2 * G.n_half
        hf.update({i: res["II"]["hf"] for i in range(1, n + 1)})
    if "III" in res:
        hf.update({no: res["III"]["hf"] for no in G.no_room})
    if "I" in res:
        hf[G.no_corr] = res["I"]["hf"]
    if "IV" in res:
        h4 = res["IV"]["hf"]
        hf.update({no: h4 for no in G.no_office + G.no_balcony + [G.no_10, G.no_lobby]})
    if "V" in res:
        hf.update({no: res["V"]["h"] for no in G.no_stairs[1:]})
    if "VII" in res and "canopy" in res["VII"]:
        hf[G.no_stairs[0]] = res["VII"]["canopy"]["hf"]
    return hf


# ============================================================================
# the builder
# ============================================================================
class Builder:
    def __init__(self, P, lay):
        self.P, self.lay = P, lay
        self.inp, self.G = P.inp, P.G
        self.sch = Schedule()
        self.bottom, self.top = [], []
        self.notes, self.texts = [], []

    # ---------------------------------------------------------- primitives
    def bar(self, mark, phi, segs, s, face, where):
        """segs: legs are rounded to cm, the main (middle) part is cut down to cm."""
        mid = len(segs) // 2
        segs = [cm(x) if i == mid else float(round(x)) for i, x in enumerate(segs)]
        return self.sch.get(mark, phi, segs, s, face, where)

    def add(self, rep, mult=1):
        rep.bar.n_total += rep.n * mult
        if rep.ar is not None:
            rep.ar[0].n_total += rep.ar[2] * mult
        (self.bottom if rep.bar.face == "bottom" else self.top).append(rep)
        return rep

    # straight bottom bars across a panel --------------------------------
    def bottom_bars(self, mark, panel, direction, phi, s, ext, frac, rfrac, where, slab,
                    lab_t=0.5, side=1, mult=1, n_override=None):
        """panel = (x0, y0, x1, y1) clear; direction 'x' or 'y' (bar direction);
        ext = (e0, e1) extensions into the supports at both ends; frac =
        position of the drawn bar across the panel; rfrac = position of the
        range line along the bar."""
        x0, y0, x1, y1 = panel
        if direction == "x":
            L = (x1 - x0) + ext[0] + ext[1]
            n = n_override or count(y1 - y0, s)
            yr = y0 + frac * (y1 - y0)
            p0, p1 = (x0 - ext[0], yr), (x1 + ext[1], yr)
            xr = x0 + rfrac * (x1 - x0)
            rng = ((xr, y0 + EDGE_GAP), (xr, y1 - EDGE_GAP))
        else:
            L = (y1 - y0) + ext[0] + ext[1]
            n = n_override or count(x1 - x0, s)
            xr = x0 + frac * (x1 - x0)
            p0, p1 = (xr, y0 - ext[0]), (xr, y1 + ext[1])
            yr = y0 + rfrac * (y1 - y0)
            rng = ((x0 + EDGE_GAP, yr), (x1 - EDGE_GAP, yr))
        b = self.bar(mark, phi, [L], s, "bottom", where)
        return self.add(Rep(b, n, p0, p1, side=side, rng=rng, lab_t=lab_t, slab=slab), mult)

    # top bars over an interior support -----------------------------------
    def top_over(self, c, t, direction, span, phi, s, ext, h_cm, frac, where, slab, side=1,
                 lab_t=0.5, rside=1, mult=1, n_override=None):
        """Support line at coordinate c (x for direction 'x' bars, y for 'y'),
        width t; span = (a0, a1) clear extent along the support; ext =
        extension beyond each face."""
        a0, a1 = span
        leg = max(h_cm - 2 * COVER, 5.0)
        straight = t + 2 * ext
        n = n_override or count(a1 - a0, s)
        q = a0 + frac * (a1 - a0)
        rpos = c + rside * (t / 2 + 0.55 * ext)
        if direction == "x":
            p0, p1 = (c - t / 2 - ext, q), (c + t / 2 + ext, q)
            rng = ((rpos, a0 + EDGE_GAP), (rpos, a1 - EDGE_GAP))
        else:
            p0, p1 = (q, c - t / 2 - ext), (q, c + t / 2 + ext)
            rng = ((a0 + EDGE_GAP, rpos), (a1 - EDGE_GAP, rpos))
        b = self.bar("TR", phi, [leg, straight, leg], s, "top", where)
        return b, Rep(b, n, p0, p1, legs=(leg, leg), side=side, rng=rng, lab_t=lab_t, slab=slab)

    # top bars at an edge support -----------------------------------------
    def top_edge(self, face, t, inward, direction, span, phi, s, ext, h_cm, frac, where, slab,
                 side=1, lab_t=0.5, mult=1, n_override=None, hook=HOOK):
        """face = coordinate of the inner face of the edge support; inward =
        +1 / -1 direction into the slab."""
        a0, a1 = span
        leg = max(h_cm - 2 * COVER, 5.0)
        straight = (t - COVER) + ext
        n = n_override or count(a1 - a0, s)
        q = a0 + frac * (a1 - a0)
        outer = face - inward * (t - COVER)
        inner = face + inward * ext
        rpos = face + inward * 0.55 * ext
        if direction == "x":
            p0, p1 = (outer, q), (inner, q)
            rng = ((rpos, a0 + EDGE_GAP), (rpos, a1 - EDGE_GAP))
        else:
            p0, p1 = (q, outer), (q, inner)
            rng = ((a0 + EDGE_GAP, rpos), (a1 - EDGE_GAP, rpos))
        b = self.bar("TR", phi, [hook, straight, leg], s, "top", where)
        return b, Rep(b, n, p0, p1, legs=(hook, leg), side=side, rng=rng, lab_t=lab_t, slab=slab)

    def with_ar(self, rep, run_len, h_cm, where, runs=1):
        """Assembly bars under the top bars, drawn as dots on the representative
        bar; 'runs' = number of runs of assembly bars along the group (one per
        panel when the group crosses several panels)."""
        straight = math.dist(rep.p0, rep.p1)
        k = n_ar(straight)
        a = self.bar("AR", ar_phi(h_cm), [run_len], AR_SPACING, "top", where)
        rep.ar = (a, k, k * runs)
        return self.add(rep)

    # ======================================================================
    # slabs
    # ======================================================================
    def build(self):
        res = self.P.res
        if "II" in res:
            self.hall(res["II"])
        if "III" in res:
            self.room(res["III"])
        if "I" in res:
            self.corridor(res["I"])
        if "IV" in res:
            self.offices(res["IV"])
            self.two_way_extra(res["IV"])
            self.balconies(res["IV"])
        if "VII" in res and "canopy" in res["VII"]:
            self.canopy(res["VII"])
        self.stairs(res.get("V"))
        self.sch.number()
        return SlabPlan(self.bottom, self.top, self.sch, self.notes, slab_thickness(self.P), self.texts)

    # ------------------------------------------------------------- hall
    def hall(self, R):
        lay, inp, G = self.lay, self.inp, self.G
        X = lay.X
        hf = R["hf"]
        D = R["design"]
        n = D["n"]
        tb, t2 = inp.B5_b, inp.B15_b
        yb = lay.hall_y
        bays = [(X["1"] + WALL / 2, X["2"] - t2 / 2, WALL, t2),
                (X["2"] + t2 / 2, X["3"] - WALL / 2, t2, WALL)]
        names = [chr(ord("A") + i) for i in range(n + 1)]

        def tw(j):                     # width of support j (0..n)
            return WALL if j in (0, n) else tb

        panels = [(yb[j] + tw(j) / 2, yb[j + 1] - tw(j + 1) / 2) for j in range(n)]
        nos = [n - j for j in range(n)]                       # slab numbers (1 at axis E)
        phid, sd = D["dist"]["phi"], sp(D["dist"]["s"])
        r1 = D["span"][1]
        for k, (x0, x1, tl, tr) in enumerate(bays):
            W = x1 - x0
            for j, (y0, y1) in enumerate(panels):
                i = n - j                                     # span number 1..n (1 at E)
                sym = min(i, n + 1 - i)
                r = D["span"][sym]
                no = nos[j]
                where = f"slabs {G.no_hall}, span {sym}"
                self.bottom_bars("BR", (x0, y0, x1, y1), "y", r["phi"], sp(r["s"]),
                                 (tw(j) - COVER, tw(j + 1) - COVER), 0.53 if j % 2 else 0.60, 0.74,
                                 where, str(no), side=1, lab_t=0.5)
                self.bottom_bars("DR", (x0, y0, x1, y1), "x", phid, sd, (tl - COVER, tr - COVER),
                                 0.27 if k == 0 else 0.35, 0.88, f"slabs {G.no_hall}, distribution",
                                 str(no), side=-1, lab_t=0.24)
            # top bars over the secondary beams
            for j in range(1, n):
                sym = min(j, n - j)
                r = D["sup"][names[sym]]
                lcl = max(panels[j - 1][1] - panels[j - 1][0], panels[j][1] - panels[j][0])
                ext = ceil5(0.3 * lcl)
                frac = 0.22 if j % 2 else 0.60
                b, rep = self.top_over(yb[j], tb, "y", (x0, x1), r["phi"], sp(r["s"]), ext, hf, frac,
                                       f"slabs {G.no_hall}, over support {names[sym]}", "",
                                       side=-1, lab_t=0.5, rside=1 if j % 2 else -1)
                self.with_ar(rep, W + (tl - COVER) + (tr - COVER), hf, f"slabs {G.no_hall}, under TR")
            # end supports on axes A and E
            phe, se = edge_top_bars(r1, hf)
            for j, face, inward in ((0, panels[0][0], 1), (n - 1, panels[-1][1], -1)):
                ext = ceil5(0.2 * (panels[j][1] - panels[j][0]))
                b, rep = self.top_edge(face, WALL, inward, "y", (x0, x1), phe, se, ext, hf, 0.36,
                                       f"slabs {G.no_hall}, edges A / E", "", side=-1)
                self.with_ar(rep, W + (tl - COVER) + (tr - COVER), hf, f"slabs {G.no_hall}, under TR")
        # constructive top bars along axes 1, 2, 3 (edges parallel to the span)
        phc, sc = constructive_top(hf)
        lsh = panels[1][1] - panels[1][0]
        extc = ceil5(max(0.2 * lsh, 40.0))
        ycl = (panels[0][0], panels[-1][1])
        ntot = sum(count(y1 - y0, sc) for y0, y1 in panels)
        jr = n // 2 - 1                                   # panel where the bar is drawn
        fr = (panels[jr][0] + 0.5 * (panels[jr][1] - panels[jr][0]) - ycl[0]) / (ycl[1] - ycl[0])
        run = lsh + 2 * (tb - COVER)
        where = f"slabs {G.no_hall}, edges on axes 1, 2, 3"
        b, rep = self.top_over(X["2"], t2, "x", ycl, phc, sc, extc, hf, fr, where, "",
                               side=1, n_override=ntot, rside=1)
        self.with_ar(rep, run, hf, where, runs=n)
        for xf, inward in ((X["1"] + WALL / 2, 1), (X["3"] - WALL / 2, -1)):
            b, rep = self.top_edge(xf, WALL, inward, "x", ycl, phc, sc, extc, hf, fr, where, "",
                                   side=1, n_override=ntot)
            self.with_ar(rep, run, hf, where, runs=n)

    # ------------------------------------------------------------- meeting room
    def room(self, R):
        lay, G = self.lay, self.G
        Y = lay.Y
        hf = R["hf"]
        D = R["design"]
        q = lay.room_x
        n = len(q) - 1
        y0, y1 = Y["D"] + WALL / 2, Y["E"] - WALL / 2
        H = y1 - y0
        panels = [(q[j] + WALL / 2, q[j + 1] - WALL / 2) for j in range(n)]
        nos = G.no_room
        phid, sd = D["dist"]["phi"], sp(D["dist"]["s"])
        e = WALL - COVER
        rng_txt = f"slabs {nos[0]}-{nos[-1]}"
        for j, (x0, x1) in enumerate(panels):
            r = D["r1"] if j in (0, n - 1) else D["r2"]
            self.bottom_bars("BR", (x0, y0, x1, y1), "x", r["phi"], sp(r["s"]), (e, e),
                             0.26 if j % 2 else 0.33, 0.82,
                             f"{rng_txt}, {'end' if j in (0, n - 1) else 'interior'} span", str(nos[j]),
                             side=-1, lab_t=0.5)
            self.bottom_bars("DR", (x0, y0, x1, y1), "y", phid, sd, (e, e), 0.14, 0.12,
                             f"{rng_txt}, distribution", str(nos[j]), side=-1, lab_t=0.70)
        for j in range(1, n):
            r = D["rB"] if j in (1, n - 1) else D["r2"]
            lcl = max(panels[j - 1][1] - panels[j - 1][0], panels[j][1] - panels[j][0])
            ext = ceil5(0.3 * lcl)
            frac = 0.86 if j % 2 else 0.70
            b, rep = self.top_over(q[j], WALL, "x", (y0, y1), r["phi"], sp(r["s"]), ext, hf, frac,
                                   f"{rng_txt}, over the beams", "", side=1, rside=1 if j % 2 else -1)
            self.with_ar(rep, H + 2 * e, hf, f"{rng_txt}, under TR")
        phe, se = edge_top_bars(D["r1"], hf)
        for j, face, inward in ((0, panels[0][0], 1), (n - 1, panels[-1][1], -1)):
            ext = ceil5(0.2 * (panels[j][1] - panels[j][0]))
            b, rep = self.top_edge(face, WALL, inward, "x", (y0, y1), phe, se, ext, hf, 0.78,
                                   f"{rng_txt}, edges 5' / 7", "", side=1)
            self.with_ar(rep, H + 2 * e, hf, f"{rng_txt}, under TR")
        # constructive top bars along axes D and E
        phc, sc = constructive_top(hf)
        lsh = panels[1][1] - panels[1][0]
        extc = ceil5(max(0.2 * lsh, 40.0))
        xcl = (panels[0][0], panels[-1][1])
        ntot = sum(count(x1 - x0, sc) for x0, x1 in panels)
        jr = n // 2
        fr = (panels[jr][0] + 0.5 * lsh - xcl[0]) / (xcl[1] - xcl[0])
        where = f"{rng_txt}, edges on axes D, E"
        for face, inward in ((y0, 1), (y1, -1)):
            b, rep = self.top_edge(face, WALL, inward, "y", xcl, phc, sc, extc, hf, fr, where, "",
                                   side=-1, n_override=ntot)
            self.with_ar(rep, lsh + 2 * e, hf, where, runs=n)

    # ------------------------------------------------------------- corridor
    def corridor(self, R):
        lay, G = self.lay, self.G
        X, Y = lay.X, lay.Y
        hf = R["hf"]
        D = R["design"]
        r = D["span"]
        no = G.no_corr
        x0, x1 = X["4"] + WALL / 2, X["7"] - WALL / 2
        y0, y1 = Y["B"] + WALL / 2, Y["D"] - WALL / 2
        H = y1 - y0
        e = WALL - COVER
        phid, sd = D["dist"]["phi"], sp(D["dist"]["s"])
        # bays between axes 4-5, 5-6, 6-7: bottom main bars, distribution bars in 3 pieces
        bx = [x0, X["5"], X["6"], x1]
        pieces = split_run(x0, x1, phid, (e, e), joints=[X["5"], X["6"]])
        phe, se = edge_top_bars(r, hf)
        ext = ceil5(0.2 * H)
        tops = []
        for k in range(3):
            xa, xb = bx[k], bx[k + 1]
            self.bottom_bars("BR", (xa, y0, xb, y1), "y", r["phi"], sp(r["s"]), (e, e), 0.62, 0.78,
                             f"slab {no}", str(no), side=1, lab_t=0.5)
            s0, s1 = pieces[k]
            yk = y0 + (0.30 + 0.06 * (k % 2)) * H
            L = s1 - s0
            b = self.bar("DR", phid, [L], sd, "bottom", f"slab {no}, distribution")
            self.add(Rep(b, count(H, sd), (s0, yk), (s1, yk), side=-1,
                         rng=((xa + 0.88 * (xb - xa), y0 + EDGE_GAP), (xa + 0.88 * (xb - xa), y1 - EDGE_GAP)),
                         lab_t=0.30, slab=str(no)))
            tops.append((xa, xb, s1 - s0))
        # top bars at the edge supports B and D
        for face, inward in ((y0, 1), (y1, -1)):
            for k, (xa, xb, Lr) in enumerate(tops):
                b, rep = self.top_edge(face, WALL, inward, "y", (xa, xb), phe, se, ext, hf, 0.30,
                                       f"slab {no}, edges B / D", "", side=-1)
                self.with_ar(rep, Lr, hf, f"slab {no}, under TR")
        # constructive top bars at the walls on axes 4 and 7
        phc, sc = constructive_top(hf)
        extc = ceil5(max(0.2 * H, 40.0))
        for face, inward in ((x0, 1), (x1, -1)):
            b, rep = self.top_edge(face, WALL, inward, "x", (y0, y1), phc, sc, extc, hf, 0.5,
                                   f"slab {no}, edges 4 / 7", "", side=1)
            self.with_ar(rep, H + 2 * e, hf, f"slab {no}, under TR")

    # ------------------------------------------------------------- offices (two-way)
    def office_panels(self):
        X, Y = self.lay.X, self.lay.Y
        t56 = self.inp.B21_b
        y0, y1 = Y["A"] + WALL / 2, Y["B"] - WALL / 2
        return [(X["4"] + WALL / 2, y0, X["5"] - t56 / 2, y1, WALL, t56),
                (X["5"] + t56 / 2, y0, X["6"] - t56 / 2, y1, t56, t56),
                (X["6"] + t56 / 2, y0, X["7"] - WALL / 2, y1, t56, WALL)]

    def two_way_bottom(self, panel, tl, tr, rx, ry, where, no, fx=0.30, fy=0.70):
        x0, y0, x1, y1 = panel
        e = WALL - COVER
        self.bottom_bars("BR", panel, "x", rx["phi"], sp(rx["s"]), (tl - COVER, tr - COVER), fx, 0.86,
                         where + ", direction x", no, side=-1, lab_t=0.40)
        self.bottom_bars("BR", panel, "y", ry["phi"], sp(ry["s"]), (e, e), fy, 0.16,
                         where + ", direction y", no, side=1, lab_t=0.40)

    def offices(self, R):
        G = self.G
        hf = R["hf"]
        D = R["design"]
        pans = self.office_panels()
        nos = G.no_office
        e = WALL - COVER
        for k, (x0, y0, x1, y1, tl, tr) in enumerate(pans):
            rx, ry = (D["x2"], D["y2"]) if k == 1 else (D["x1"], D["y1"])
            self.two_way_bottom((x0, y0, x1, y1), tl, tr, rx, ry, f"slab {nos[k]}", str(nos[k]),
                                fx=0.34 if k % 2 else 0.27)
        # top bars over the beams on axes 5 and 6
        rs = D["sup"]
        X = self.lay.X
        t56 = self.inp.B21_b
        y0, y1 = pans[0][1], pans[0][3]
        H = y1 - y0
        for k, ax in ((0, "5"), (1, "6")):
            lcl = max(pans[k][2] - pans[k][0], pans[k + 1][2] - pans[k + 1][0])
            ext = ceil5(0.25 * lcl)
            b, rep = self.top_over(X[ax], t56, "x", (y0, y1), rs["phi"], sp(rs["s"]), ext, hf, 0.56,
                                   f"slabs {nos[0]}-{nos[-1]}, over axes 5, 6", "", side=1,
                                   rside=1 if k == 0 else -1)
            self.with_ar(rep, H + 2 * e, hf, f"slabs {nos[0]}-{nos[-1]}, under TR")
        # edge supports: walls on axes 4 / 7 (x), beam on axis B (y), axis A of the middle slab
        phx, sx = edge_top_bars(D["x1"], hf)
        phy, sy = edge_top_bars(D["y1"], hf)
        for k, face, inward in ((0, pans[0][0], 1), (2, pans[2][2], -1)):
            ext = ceil5(0.2 * (pans[k][2] - pans[k][0]))
            b, rep = self.top_edge(face, WALL, inward, "x", (y0, y1), phx, sx, ext, hf, 0.56,
                                   f"slabs {nos[0]}, {nos[2]}, edges 4 / 7", "", side=1)
            self.with_ar(rep, H + 2 * e, hf, f"slabs {nos[0]}-{nos[-1]}, under TR")
        ext = ceil5(0.2 * H)
        for k, (x0, _, x1, _, tl, tr) in enumerate(pans):
            run = (x1 - x0) + (tl - COVER) + (tr - COVER)
            b, rep = self.top_edge(y1, WALL, -1, "y", (x0, x1), phy, sy, ext, hf, 0.12,
                                   f"slabs {nos[0]}-{nos[-1]}, edge B", "", side=-1)
            self.with_ar(rep, run, hf, f"slabs {nos[0]}-{nos[-1]}, under TR")
            if k == 1:                                   # no balcony in front of the middle slab
                b, rep = self.top_edge(y0, WALL, 1, "y", (x0, x1), phy, sy, ext, hf, 0.40,
                                       f"slab {nos[1]}, edge A", "", side=-1)
                self.with_ar(rep, run, hf, f"slabs {nos[0]}-{nos[-1]}, under TR")

    # ------------------------------------------------------------- slabs 10 and 18
    def two_way_extra(self, R):
        """Slab 10 (axes 4-5' / D-E) and the lobby slab 18 (axes 3-4, B17-D)
        are not designed separately: they are reinforced like the office
        slabs (two-way, smaller spans, same thickness)."""
        lay, G = self.lay, self.G
        X, Y = lay.X, lay.Y
        hf = R["hf"]
        D = R["design"]
        from .dxf_formwork import T_B17_Y
        e = WALL - COVER
        slabs = [(G.no_10, (X["4"] + WALL / 2, Y["D"] + WALL / 2, X["5'"] - WALL / 2, Y["E"] - WALL / 2)),
                 (G.no_lobby, (X["3"] + WALL / 2, lay.fy(T_B17_Y) + WALL / 2,
                               X["4"] - WALL / 2, Y["D"] - WALL / 2))]
        phx, sx = edge_top_bars(D["x1"], hf)
        phy, sy = edge_top_bars(D["y1"], hf)
        for no, (x0, y0, x1, y1) in slabs:
            where = f"slab {no}"
            self.two_way_bottom((x0, y0, x1, y1), WALL, WALL, D["x1"], D["y1"], where, str(no),
                                fx=0.22, fy=0.78)
            W, H = x1 - x0, y1 - y0
            for face, inward in ((x0, 1), (x1, -1)):
                b, rep = self.top_edge(face, WALL, inward, "x", (y0, y1), phx, sx, ceil5(0.2 * W), hf,
                                       0.30, where + ", edges", "", side=1)
                self.with_ar(rep, H + 2 * e, hf, where + ", under TR")
            for face, inward in ((y0, 1), (y1, -1)):
                b, rep = self.top_edge(face, WALL, inward, "y", (x0, x1), phy, sy, ceil5(0.2 * H), hf,
                                       0.78, where + ", edges", "", side=-1)
                self.with_ar(rep, W + 2 * e, hf, where + ", under TR")
        self.notes.append(f"Slabs {G.no_10} and {G.no_lobby} are reinforced like slabs "
                          f"{G.no_office[0]}-{G.no_office[-1]} (two-way slabs, smaller spans).")

    # ------------------------------------------------------------- balconies
    def balconies(self, R):
        lay, G, inp = self.lay, self.G, self.inp
        Y = lay.Y
        hf = R["hf"]
        D = R["design"]
        rc = D["c"]
        pans = self.office_panels()
        y_root = Y["A"] - WALL / 2                     # outer face of the wall on axis A
        y_tip = y_root - inp.d
        H_off = pans[0][3] - pans[0][1]
        ext_in = max(ceil5(inp.d), ceil5(0.25 * H_off))
        tip_leg = 10.0 - 2 * COVER                    # tip thickness 10 cm
        leg = max(hf - 2 * COVER, 5.0)
        phd, sd = dist_bars(rc["As_prov"], hf)
        for k, no in ((0, G.no_balcony[0]), (2, G.no_balcony[1])):
            x0, x1 = pans[k][0], pans[k][2]
            W = x1 - x0
            main = (inp.d - COVER) + WALL + ext_in
            b = self.bar("TR", rc["phi"], [tip_leg, main, leg], sp(rc["s"]), "top",
                         f"balconies {G.no_balcony[0]}, {G.no_balcony[1]}")
            xq = x0 + 0.62 * W
            rep = Rep(b, count(W, sp(rc["s"])), (xq, y_tip + COVER), (xq, y_root + WALL + ext_in),
                      legs=(tip_leg, leg), side=-1,
                      rng=((x0 + EDGE_GAP, y_root - 0.62 * inp.d), (x1 - EDGE_GAP, y_root - 0.62 * inp.d)),
                      lab_t=0.30, slab=str(no))
            self.add(rep)
            # distribution bars in the cantilever (top, under the main bars)
            Ld = W - 2 * COVER
            bd = self.bar("DR", phd, [Ld], sd, "top", f"balconies {G.no_balcony[0]}, {G.no_balcony[1]}")
            yd = y_root - 0.30 * inp.d
            self.add(Rep(bd, count(inp.d, sd), (x0 + COVER, yd), (x1 - COVER, yd), side=-1,
                         rng=((x0 + 0.18 * W, y_tip + EDGE_GAP), (x0 + 0.18 * W, y_root - EDGE_GAP)),
                         lab_t=0.30, slab=str(no)))

    # ------------------------------------------------------------- canopy slab 7
    def canopy(self, R):
        lay, G, inp = self.lay, self.G, self.inp
        from .dxf_formwork import T_CANOPY_X0, T_CORE_FACE, T_CANOPY_EDGE
        c = R["canopy"]
        r = c["design"]
        hf = c["hf"]
        no = G.no_stairs[0]
        x0, x1 = lay.fx(T_CANOPY_X0), lay.X["4"] + WALL / 2
        y_root, y_tip = lay.fy(T_CORE_FACE), lay.fy(T_CANOPY_EDGE)
        W = x1 - x0
        tip_leg = max(hf - 2 * COVER, 5.0)
        hb = R.get("h", inp.BT_h)
        anch = max(hb - 2 * COVER - 5.0, 20.0)          # hook down into the beam
        main = (y_tip - y_root - COVER) + (inp.BT_b - COVER)
        b = self.bar("TR", r["phi"], [tip_leg, main, anch], sp(r["s"]), "top", f"canopy slab {no}")
        xq = x0 + 0.70 * W
        self.add(Rep(b, count(W, sp(r["s"])), (xq, y_tip - COVER), (xq, y_root - inp.BT_b + COVER),
                     legs=(tip_leg, anch), side=-1,
                     rng=((x0 + EDGE_GAP, y_root + 0.70 * (y_tip - y_root)),
                          (x1 - EDGE_GAP, y_root + 0.70 * (y_tip - y_root))),
                     lab_t=0.62, slab=str(no)))
        phd, sd = dist_bars(r["As_prov"], hf)
        bd = self.bar("DR", phd, [W - 2 * COVER], sd, "top", f"canopy slab {no}")
        yd = y_root + 0.35 * (y_tip - y_root)
        self.add(Rep(bd, count(y_tip - y_root, sd), (x0 + COVER, yd), (x1 - COVER, yd), side=-1,
                     rng=((x0 + 0.2 * W, y_root + EDGE_GAP), (x0 + 0.2 * W, y_tip - EDGE_GAP)),
                     lab_t=0.5, slab=str(no)))

    # ------------------------------------------------------------- stairs
    def stairs(self, R):
        if not R:
            return
        G = self.G
        X, Y = self.lay.X, self.lay.Y
        self.texts.append(((X["3"] + X["4"]) / 2, Y["D"] + 0.45 * (Y["E"] - Y["D"]),
                           f"Stairs {G.no_stairs[1]}, {G.no_stairs[2]}: see the drawing", 9.0, 90.0))
        self.texts.append(((X["3"] + X["4"]) / 2 + 14, Y["D"] + 0.45 * (Y["E"] - Y["D"]),
                           f"of the staircase ({R['bars']})", 9.0, 90.0))


def build(P, lay):
    """Reinforcement of all slabs on the geometry of the formwork layout."""
    return Builder(P, lay).build()
