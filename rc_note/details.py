# -*- coding: utf-8 -*-
"""
details.py - reinforcement drawings of the elements (ezdxf)
==========================================================

Detail drawings drawn from the results of the calculations, placed in the
reinforcement DXF below the slab plans and written one per file by export()
(model space, 1 unit = 1 cm, true size; text sizes for printing at the scale
given in the title):

  * beam B21 - simply supported T-beam (section VI)            M 1:25
  * beam on axis E (3-4) - bending and torsion (section VII)   M 1:25
  * beam B5 - continuous beam over B15 (section VIII)          M 1:25
  * column C10 - two storeys, sections 0-0 and 1-1 (IX)       M 1:25
  * frame on axis 2 - beam B15, columns C1, C7, C12 (X)        M 1:25
  * column C7 of the frame - two storeys, sections (X)          M 1:25
  * pad footing under C7 - plan and section (XI)               M 1:25
  * stairs - flight and landing (V)                            M 1:10

Every element has: elevation (or plan) with the bars, links and dimension
lines, cross-sections, the bars drawn separately with the lengths of their
parts (bending schedule), the position numbers in circles and a bar
schedule. Positions are numbered per element.
"""
from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from ezdxf.enums import TextEntityAlignment

from .design import BAR_AREA, beam_bars
from .engine import fmt

MC = TextEntityAlignment.MIDDLE_CENTER
ML = TextEntityAlignment.MIDDLE_LEFT
MR = TextEntityAlignment.MIDDLE_RIGHT
BL = TextEntityAlignment.BOTTOM_LEFT
BC = TextEntityAlignment.BOTTOM_CENTER

C = 2.5                          # cm, concrete cover to the links (c_nom = 25 mm)
C_FOOT = 5.0                     # cm, cover in the footing
MASS = {d: 7850e-6 * math.pi * d * d / 4 for d in (6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32)}

LAYERS = {
    "D-CONCRETE": dict(color=7, lineweight=35),
    "D-HIDDEN": dict(color=8, lineweight=13),
    "D-AXIS": dict(color=2, lineweight=13),
    "D-BARS": dict(color=1, lineweight=50),
    "D-LINKS": dict(color=5, lineweight=25),
    "D-TEXT": dict(color=7, lineweight=18),
    "D-DIM": dict(color=3, lineweight=18),
}


def ceil5(v):
    return 5.0 * math.ceil(v / 5.0 - 1e-9)


def anchor_leg(phi, h):
    """Leg of a beam bar bent into the support: 12Φ, at least 15 cm, inside the section."""
    return min(max(ceil5(12 * phi / 10), 15.0), max(h - 2 * C - 5, 10.0))


def n_bars(length, s, gap=5.0):
    return max(2, int(math.floor((length - 2 * gap) / s + 1e-6)) + 1)


def link_count(x0, x1, s, gap=5.0):
    return max(2, int(math.floor((x1 - x0 - 2 * gap) / s + 1e-6)) + 1)


# ============================================================================
# document setup
# ============================================================================
def setup(doc):
    for name, attr in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, **attr)
    if "RC_DASHED" not in doc.linetypes:
        doc.linetypes.add("RC_DASHED", pattern=[6.0, 4.0, -2.0], description="Dashed __ __")
    if "RC_AXIS" not in doc.linetypes:
        doc.linetypes.add("RC_AXIS", pattern=[24.0, 18.0, -2.5, 0.0, -2.5], description="Axis ___ . ___")
    doc.layers.get("D-HIDDEN").dxf.linetype = "RC_DASHED"
    doc.layers.get("D-AXIS").dxf.linetype = "RC_AXIS"
    if "RC_TEXT" not in doc.styles:
        doc.styles.add("RC_TEXT", font="arial.ttf")
    for k in (25, 10):
        name = f"RC_D{k}"
        if name not in doc.dimstyles:
            t = 0.2 * k
            doc.dimstyles.new(name, dxfattribs={
                "dimtxt": t, "dimasz": 0.45 * t, "dimblk": "OBLIQUE", "dimexo": 0.25 * t, "dimexe": 0.35 * t,
                "dimgap": 0.2 * t, "dimdec": 1, "dimzin": 8, "dimdsep": ord("."), "dimtad": 1, "dimtih": 0,
                "dimtoh": 0, "dimclrd": 3, "dimclre": 3, "dimclrt": 3, "dimtxsty": "RC_TEXT", "dimlunit": 2,
                "dimtmove": 2})


# ============================================================================
# drawing sheet (local coordinates, extents, dry run for the layout)
# ============================================================================
class Sheet:
    def __init__(self, msp, ox, oy, scale=25):
        self.msp, self.ox, self.oy, self.k = msp, ox, oy, scale
        self.h = 0.25 * scale            # 2.5 mm text on paper
        self.box = [math.inf, math.inf, -math.inf, -math.inf]
        self.dimstyle = f"RC_D{scale}"

    # ---------------------------------------------------------------- extents
    def _u(self, *pts):
        b = self.box
        for x, y in pts:
            b[0], b[1], b[2], b[3] = min(b[0], x), min(b[1], y), max(b[2], x), max(b[3], y)

    @property
    def size(self):
        return self.box[2] - self.box[0], self.box[3] - self.box[1]

    def P(self, p):
        return (self.ox + p[0], self.oy + p[1])

    # ---------------------------------------------------------------- entities
    def line(self, a, b, layer="D-CONCRETE"):
        self._u(a, b)
        if self.msp is not None:
            self.msp.add_line(self.P(a), self.P(b), dxfattribs={"layer": layer})

    def pline(self, pts, layer="D-CONCRETE", closed=False):
        self._u(*pts)
        if self.msp is not None:
            self.msp.add_lwpolyline([self.P(p) for p in pts], close=closed, dxfattribs={"layer": layer})

    def rect(self, x0, y0, x1, y1, layer="D-CONCRETE"):
        self.pline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer, closed=True)

    def circle(self, c, r, layer="D-TEXT"):
        self._u((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
        if self.msp is not None:
            self.msp.add_circle(self.P(c), r, dxfattribs={"layer": layer})

    def dot(self, c, d_mm, layer="D-BARS"):
        r = max(d_mm / 20.0, 0.5)
        self._u((c[0] - r, c[1] - r), (c[0] + r, c[1] + r))
        if self.msp is not None:
            h = self.msp.add_hatch(color=256, dxfattribs={"layer": layer})
            h.set_solid_fill()
            h.paths.add_edge_path().add_arc(self.P(c), r, 0, 360)

    def text(self, s, p, h=None, rot=0.0, align=MC, layer="D-TEXT"):
        h = h or self.h
        w = 0.62 * h * len(s)
        if abs(rot) < 1:
            dx = {MC: -w / 2, BC: -w / 2, ML: 0, BL: 0, MR: -w}.get(align, -w / 2)
            self._u((p[0] + dx, p[1] - h), (p[0] + dx + w, p[1] + h))
        else:
            self._u((p[0] - h, p[1] - w / 2), (p[0] + h, p[1] + w / 2))
        if self.msp is not None:
            t = self.msp.add_text(s, height=h, rotation=rot, dxfattribs={"layer": layer, "style": "RC_TEXT"})
            t.set_placement(self.P(p), align=align)

    def bubble(self, n, p, to=None):
        """Position number in a circle, with a leader line to the point 'to'."""
        r = 0.85 * self.h
        if to is not None:
            dx, dy = to[0] - p[0], to[1] - p[1]
            L = math.hypot(dx, dy)
            if L > r:
                self.line((p[0] + dx / L * r, p[1] + dy / L * r), to, "D-TEXT")
        self.circle(p, r)
        self.text(str(n), p, 0.9 * self.h)

    def dim(self, p1, p2, base, vertical=False, text=None):
        """Linear dimension between p1 and p2; base = a point on the dimension line."""
        a, b, c = p1, p2, base
        self._u(a, b, c)
        if vertical:
            self._u((c[0] - 1.5 * self.h, c[1]), (c[0] + 1.5 * self.h, c[1]))
        else:
            self._u((c[0], c[1] - 0.5 * self.h), (c[0], c[1] + 1.8 * self.h))
        if self.msp is None or math.dist(a, b) < 0.5:
            return
        d = self.msp.add_linear_dim(base=self.P(c), p1=self.P(a), p2=self.P(b), angle=90 if vertical else 0,
                                    dimstyle=self.dimstyle, text=text or "<>", dxfattribs={"layer": "D-DIM"})
        d.render()

    def hchain(self, xs, y_obj, y_dim):
        for a, b in zip(xs, xs[1:]):
            if b - a > 0.5:
                self.dim((a, y_obj), (b, y_obj), (a, y_dim))

    def vchain(self, ys, x_obj, x_dim):
        for a, b in zip(ys, ys[1:]):
            if b - a > 0.5:
                self.dim((x_obj, a), (x_obj, b), (x_dim, a), vertical=True)

    def table(self, x0, y0, cols, rows, title=None):
        h = 0.8 * self.h
        rh = 2.0 * h
        W = sum(w for _, w in cols)
        if title:
            self.text(title, (x0, y0 + 0.8 * h), 1.15 * h, align=BL)
        y = y0
        lines = [y]
        for r in [[c for c, _ in cols]] + rows:
            x = x0
            for (hd, w), v in zip(cols, r):
                self.text(str(v), (x + w / 2, y - rh / 2), h)
                x += w
            y -= rh
            lines.append(y)
        for yy in lines:
            self.line((x0, yy), (x0 + W, yy), "D-TEXT")
        x = x0
        for _, w in cols + [(None, 0)]:
            self.line((x, y0), (x, y), "D-TEXT")
            x += w
        return y


# ============================================================================
# bars of an element
# ============================================================================
@dataclass
class DBar:
    pos: int
    phi: int
    segs: list               # lengths of the parts [cm]
    n: int = 0
    desc: str = ""
    kind: str = "bar"        # bar / link / tie

    @property
    def L(self):
        return sum(self.segs)

    def label(self):
        return f"{self.n}Ø{self.phi} L={fmt(self.L)}"


@dataclass
class Element:
    key: str
    title: str
    scale: int
    bars: list = field(default_factory=list)

    def bar(self, phi, segs, desc, kind="bar"):
        segs = [float(round(s)) for s in segs]
        for b in self.bars:
            if b.phi == phi and b.segs == segs and b.kind == kind:
                return b
        b = DBar(len(self.bars) + 1, int(phi), segs, 0, desc, kind)
        self.bars.append(b)
        return b

    @property
    def mass(self):
        return sum(b.L * b.n / 100 * MASS[b.phi] for b in self.bars)


def link_segs(w, h, phi_w):
    """Closed link, outside dimensions w x h, two 135° hooks of 10Φ (≥ 7 cm)."""
    hook = max(10 * phi_w / 10, 7.0)
    return [w, h, w, h, hook, hook]


def draw_link(sh, el, b, x0, y0, w, h):
    """Link shape with the lengths of its sides."""
    sh.rect(x0, y0, x0 + w, y0 + h, "D-LINKS")
    hk = min(b.segs[-1], 0.4 * min(w, h))
    sh.line((x0 + w, y0 + h), (x0 + w - 0.7 * hk, y0 + h - 0.7 * hk), "D-LINKS")
    sh.line((x0 + w, y0 + h - 1.2), (x0 + w - 0.7 * hk, y0 + h - 1.2 - 0.7 * hk), "D-LINKS")
    t = 0.75 * sh.h
    sh.text(fmt(w), (x0 + w / 2, y0 - 0.9 * t), t)
    sh.text(fmt(h), (x0 - 0.9 * t, y0 + h / 2), t, rot=90)
    sh.bubble(b.pos, (x0 + w + 2.2 * sh.h, y0 + h / 2), (x0 + w, y0 + h / 2))
    sh.text(b.label(), (x0 + w + 3.6 * sh.h, y0 + h / 2), 0.85 * sh.h, align=ML)


def draw_tie(sh, el, b, x0, y0, w):
    sh.line((x0, y0), (x0 + w, y0), "D-LINKS")
    for x, s in ((x0, 1), (x0 + w, -1)):
        sh.line((x, y0), (x + s * 3, y0 + 3), "D-LINKS")
    t = 0.75 * sh.h
    sh.text(fmt(w), (x0 + w / 2, y0 - 0.9 * t), t)
    sh.bubble(b.pos, (x0 + w + 2.2 * sh.h, y0), (x0 + w, y0))
    sh.text(b.label(), (x0 + w + 3.6 * sh.h, y0), 0.85 * sh.h, align=ML)


def draw_shape(sh, b, pts, label_at=None, label=None, segs=None):
    """A bar drawn separately: polyline pts (cm), lengths of the parts written
    along the parts, position number and label."""
    sh.pline(pts, "D-BARS")
    t = 0.75 * sh.h
    for (a, c), L in zip(zip(pts, pts[1:]), segs or b.segs):
        mx, my = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
        dx, dy = c[0] - a[0], c[1] - a[1]
        ang = math.degrees(math.atan2(dy, dx))
        if 90 < ang % 360 <= 270:
            ang -= 180
        Ln = math.hypot(dx, dy) or 1
        nx, ny = -dy / Ln, dx / Ln
        if abs(dx) < 1e-6:
            nx, ny = (-1, 0) if a[0] <= pts[0][0] + 1e-6 else (1, 0)
        sh.text(fmt(L), (mx + nx * 0.9 * t, my + ny * 0.9 * t), t, rot=ang)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    if label_at is None:
        label_at = ((min(xs) + max(xs)) / 2, min(ys) - 1.6 * sh.h)
    sh.bubble(b.pos, (label_at[0] - 4.0 * sh.h, label_at[1]))
    sh.text(label or b.label(), (label_at[0] - 2.6 * sh.h, label_at[1]), 0.9 * sh.h, align=ML)


def schedule(sh, el, x0, y0):
    rows = [[str(b.pos), f"Ø{b.phi}", "+".join(fmt(s) for s in b.segs[:4]) + ("..." if len(b.segs) > 4 else ""),
             fmt(b.L), str(b.n), fmt(b.L * b.n / 100), fmt(b.L * b.n / 100 * MASS[b.phi])] for b in el.bars]
    rows.append(["", "", "", "", "", "Total", fmt(el.mass)])
    w = 2.2 * sh.h
    cols = [("Pos.", 1.6 * w), ("Ø", 1.6 * w), ("Shape [cm]", 5.0 * w), ("L [cm]", 2.2 * w), ("n", 1.6 * w),
            ("Total [m]", 2.6 * w), ("Mass [kg]", 2.6 * w)]
    return sh.table(x0, y0, cols, rows, f"Bar schedule - {el.title.split(' - ')[0]}")


# ============================================================================
# beams (elevation + sections + bars)
# ============================================================================
@dataclass
class BeamSpec:
    el: Element
    bw: float
    h: float
    hf: float
    supports: list           # dict(x, t, kind 'col'/'wall'/'beam', depth, label)
    runs: list               # dict(bar, level 'bot'/'top'/'side', x0, x1, legs=(l0, l1), n)
    zones: list              # (x0, x1, s) - links
    link: DBar = None
    sections: list = field(default_factory=list)   # (label, x, bot[(bar, n)], top[(bar, n)], side (bar, n/face))
    hangers: list = field(default_factory=list)     # (x, n) extra links
    phi_w: int = 8
    below: float = 60.0      # columns drawn below the soffit
    tie: DBar = None
    shift: dict = None       # data of the tension-shift diagram


def bar_y(level, h, phi, phi_w, k=0):
    off = C + phi_w / 10 + phi / 20 + 1.0 * k
    return off if level == "bot" else h - off


def lap_dims(sh, sp, h, up):
    """Dimension lines at every overlap of two bars at the same level (laps
    over the supports, assembly bars lapped with the support bars)."""
    for level, y_d, step in (("top", h + 0.35 * up, 1.7 * sh.h), ("bot", -0.35 * sp.below, -1.7 * sh.h)):
        runs = [r for r in sp.runs if r["level"] == level]
        laps = []
        for i in range(len(runs)):
            for j in range(i + 1, len(runs)):
                a, b = runs[i], runs[j]
                a0, a1 = sorted((a["x0"], a["x1"]))
                b0, b1 = sorted((b["x0"], b["x1"]))
                o0, o1 = max(a0, b0), min(a1, b1)
                if o1 - o0 < 0.5:
                    continue
                if (a0 <= b0 + 0.5 and a1 >= b1 - 0.5) or (b0 <= a0 + 0.5 and b1 >= a1 - 0.5):
                    continue                              # one bar inside the other: no lap
                laps.append((o0, o1, a.get("_y", 0)))
        used = []
        for o0, o1, yb in sorted(set((round(a, 1), round(b, 1), yb) for a, b, yb in laps)):
            k = sum(1 for u0, u1 in used if not (o1 < u0 - 8 or o0 > u1 + 8))
            used.append((o0, o1))
            sh.dim((o0, yb), (o1, yb), (o0, y_d + k * step))


def bar_list(sh, runs, y, x_shift=0.0):
    """The bars drawn separately (bending schedule), every run - also the
    mirrored ones - with its own label; runs of one position share a row."""
    rows = []
    for r in runs:
        for row in rows:
            if row[0]["bar"].pos == r["bar"].pos and all(
                    min(r["x0"], r["x1"]) > max(q["x0"], q["x1"]) + 20 or max(r["x0"], r["x1"]) < min(q["x0"], q["x1"]) - 20
                    for q in row):
                row.append(r)
                break
        else:
            rows.append([r])
    for row in rows:
        up_ = max(max(r.get("legs", (0, 0))) if r["level"] == "bot" else 0 for r in row)
        dn_ = max(max(r.get("legs", (0, 0))) if r["level"] != "bot" else 0 for r in row)
        y -= up_ + 2.0 * sh.h
        for r in row:
            b = r["bar"]
            l0, l1 = r.get("legs", (0, 0))
            sgn = 1 if r["level"] == "bot" else -1
            x0, x1 = r["x0"] + x_shift, r["x1"] + x_shift
            pts = []
            if l0:
                pts.append((x0, y + sgn * l0))
            pts += [(x0, y), (x1, y)]
            if l1:
                pts.append((x1, y + sgn * l1))
            main = max(b.segs)
            segs = ([l0] if l0 else []) + [main] + ([l1] if l1 else [])
            draw_shape(sh, b, pts, label_at=((x0 + x1) / 2, y - 1.6 * sh.h - dn_),
                       label=f"{r['n']}Ø{b.phi} L={fmt(b.L)}", segs=segs)
        y -= dn_ + 3.4 * sh.h
    return y


def draw_shift(sh, sp, y0):
    """Diagram of the tensile force M_Ed/z, shifted by a_l = 0.45·d·cotθ
    (EC2 9.2.1.3), compared with the force the bars can take (A_s·f_yd per
    bar). Positive moments (bottom bars) are drawn downwards."""
    import numpy as np
    S = sp.shift
    x_org = S["x0"]
    X = np.array(S["X"]) * 100.0 + x_org
    fyd = S["fyd"]
    al = 0.45 * S["d"] / 10 * S["cot"]
    xx = np.linspace(X[0], X[-1], 600)
    Fp = np.interp(xx, X, np.maximum(np.array(S["Mpos"]), 0)) / S["zp"]
    Fn = np.interp(xx, X, np.maximum(-np.array(S["Mneg"]), 0)) / S["zn"] if S.get("Mneg") else np.zeros_like(xx)

    def shift(F):
        out = np.empty_like(F)
        for i, x in enumerate(xx):
            m = abs(xx - x) <= al
            out[i] = F[m].max()
        return out
    Fps, Fns = shift(Fp), shift(Fn)
    cap_b = [(b, n) for b, n in S["bot"]]
    cap_t = list(S.get("top", []))
    Fbar = lambda b: BAR_AREA[b.phi] * fyd / 1000.0
    Rb = sum(n * Fbar(b) for b, n in cap_b)
    Rt = (cap_t[0][1] * Fbar(cap_t[0][0]) + max([it[1] * Fbar(it[0]) for it in cap_t[1:]] or [0])) if cap_t else 0.0
    Fmax = max(Fps.max(), Fns.max(), Rb, Rt, 1.0)
    target = 4.0 * sh.h * 3.5
    cands = sorted(b_ * 10 ** e for b_ in (1, 2, 2.5, 5) for e in range(0, 5))
    k = next((c_ for c_ in cands if Fmax / c_ <= target), Fmax / target)   # kN per drawing unit (cm)
    ytop = y0 - (max(Fns.max(), Rt) / k if (S.get("Mneg") or cap_t) else 0) - 2 * sh.h
    ya = ytop                                 # axis of the diagram
    sh.text("Diagram of the tensile force (shifted by a_l)", (x_org, ya + 2.2 * sh.h +
            (max(Fns.max(), Rt) / k if S.get("Mneg") else 0)), sh.h, align=BL)
    sh.line((X[0], ya), (X[-1], ya), "D-TEXT")
    for F, Fs, sgn in ((Fp, Fps, -1), (Fn, Fns, 1)):
        if F.max() <= 0:
            continue
        sh.pline([(x, ya + sgn * f / k) for x, f in zip(xx, F)], "D-HIDDEN")
        pts = [(xx[0], ya)] + [(x, ya + sgn * f / k) for x, f in zip(xx, Fs)] + [(xx[-1], ya)]
        sh.pline(pts, "D-LINKS")
        if sh.msp is not None:
            h_ = sh.msp.add_hatch(color=254, dxfattribs={"layer": "D-TEXT"})
            h_.set_solid_fill(color=254)
            h_.paths.add_polyline_path([sh.P(p) for p in pts], is_closed=True)
    # force the bars can take: one line per bar
    for grp, sgn, x_rng in ((cap_b, -1, (X[0], X[-1])), (cap_t, 1, None)):
        base = 0.0
        for k_, item in enumerate(grp):
            b, n = item[0], item[1]
            acc = 0.0 if k_ == 0 else base          # bars over a support stack on the continuous bars
            for i in range(n):
                acc += Fbar(b)
                xa, xb = item[2] if len(item) > 2 and item[2] else (x_rng or (X[0], X[-1]))
                y = ya + sgn * acc / k
                sh.line((xa, y), (xb, y), "D-BARS")
                sh.text(f"F Ø{b.phi}", (xa - 0.6 * sh.h, y), 0.75 * sh.h, align=MR)
            if k_ == 0:
                base = acc
    # texts
    b1 = cap_b[0][0]
    Mmax = max(np.array(S["Mpos"]))
    xt = X[-1] + 2 * sh.h
    lines = [f"F Ø{b1.phi} = A_s·f_yd = {fmt(BAR_AREA[b1.phi])}·{fmt(fyd)} = {fmt(Fbar(b1))} kN",
             f"M_Ed/z = M_Ed/(ζ·d) = {fmt(Mmax)}/({fmt(S['zp'] / S['d'] * 1000)}·{fmt(S['d'] / 1000)}) = "
             f"{fmt(Mmax / S['zp'])} kN",
             f"a_l = 0.45·d·cotθ = 0.45·{fmt(S['d'] / 10)}·{fmt(S['cot'])} = {fmt(al)} cm",
             f"ΔF_td = 0.5·V_Ed·cotθ = 0.5·{fmt(S['V'])}·{fmt(S['cot'])} = {fmt(0.5 * S['V'] * S['cot'])} kN",
             f"Scale of the forces: 1 cm = {fmt(k)} kN"]
    for i, t in enumerate(lines):
        sh.text(t, (xt, ya - (i + 0.5) * 1.8 * sh.h), 0.85 * sh.h, align=ML)
    # a_l marked at the maximum
    i = int(np.argmax(Fp))
    sh.dim((xx[i], ya - Fp[i] / k), (xx[i] + al, ya - Fp[i] / k), (xx[i], ya - Fp[i] / k - 1.8 * sh.h),
           text=f"a_l = {fmt(al)}")
    return min(ya - max(Fps.max(), Rb) / k - 4 * sh.h, ya - 10 * sh.h)


def draw_beam(sh, sp, x_off=0.0, draw_sections=True, draw_list=True, sched=True):
    """Elevation of a beam: supports, bars, links, dimensions; sections to
    the right, the bars drawn separately underneath, the bar schedule.
    Returns the lowest y used."""
    el, h, bw = sp.el, sp.h, sp.bw
    sups = sorted(sp.supports, key=lambda s: s["x"])
    x_l = sups[0]["x"] - sups[0]["t"] / 2
    x_r = sups[-1]["x"] + sups[-1]["t"] / 2
    up = 60.0
    # ------------------------------------------------------------ concrete
    sh.line((x_l, h), (x_r, h))
    if sp.hf > 0:
        sh.line((x_l - 15, h - sp.hf), (x_r + 15, h - sp.hf), "D-HIDDEN")
    for a, b in zip(sups, sups[1:]):
        sh.line((a["x"] + a["t"] / 2, 0), (b["x"] - b["t"] / 2, 0))
    for s in sups:
        xa, xb = s["x"] - s["t"] / 2, s["x"] + s["t"] / 2
        if s["kind"] == "beam":
            y0 = h - s["depth"]
            sh.rect(xa, y0, xb, h)
        else:
            y0 = -s.get("below", sp.below)
            sh.line((xa, y0), (xa, h + up))
            sh.line((xb, y0), (xb, h + up))
            for yy in (y0, h + up):                    # break lines
                sh.pline([(xa - 4, yy), (s["x"] - 2, yy), (s["x"], yy + 3), (s["x"] + 2, yy - 3),
                          (xb + 4, yy)], "D-HIDDEN")
        if s.get("label"):
            sh.text(s["label"], (s["x"], h + up + 1.6 * sh.h), 1.1 * sh.h)
        sh.line((s["x"], -sp.below - 15), (s["x"], h + up + 8), "D-AXIS")
    # ------------------------------------------------------------ bars
    level_count = {}
    for r in sp.runs:
        b = r["bar"]
        k = level_count.get(r["level"], 0)
        level_count[r["level"]] = k + 1
        if r["level"] == "side":
            y = h / 2
        else:
            y = bar_y(r["level"], h, b.phi, sp.phi_w, k)
        sgn = 1 if r["level"] == "bot" else -1
        l0, l1 = r.get("legs", (0, 0))
        pts = []
        if l0:
            pts.append((r["x0"], y + sgn * l0))
        pts += [(r["x0"], y), (r["x1"], y)]
        if l1:
            pts.append((r["x1"], y + sgn * l1))
        sh.pline(pts, "D-BARS")
        b.n += r["n"]
        xm = r["x0"] + r.get("tag", 0.5) * (r["x1"] - r["x0"])
        yb = y + (-2.2 if r["level"] == "bot" else 2.2) * sh.h
        if r["level"] == "side":
            yb = y + 1.8 * sh.h
        sh.bubble(b.pos, (xm, yb), (xm, y))
        r["_y"] = y
    lap_dims(sh, sp, h, up)
    # links
    yl0, yl1 = C, h - C
    total = 0
    for x0, x1, s in sp.zones:
        n = link_count(x0, x1, s)
        total += n
        step = (x1 - x0 - 10) / max(n - 1, 1)
        for i in range(n):
            x = x0 + 5 + i * step
            sh.line((x, yl0), (x, yl1), "D-LINKS")
    for x, n in sp.hangers:
        for i in range(n):
            xx = x + (i - (n - 1) / 2) * 5.0
            sh.line((xx, yl0), (xx, yl1), "D-LINKS")
        total += n
        sh.text(f"{n}Ø{sp.link.phi} hangers", (x, h + 1.2 * sh.h), 0.8 * sh.h)
    if sp.link is not None:
        sp.link.n += total
        if sp.zones:
            x0, x1, s = sp.zones[0]
            sh.bubble(sp.link.pos, (x0 + 0.5 * (x1 - x0), -2.6 * sh.h), (x0 + 0.5 * (x1 - x0), yl0 + 3))
    if sp.tie is not None:
        sp.tie.n += total
    # link zones dimensioned above
    yz = h + up + 4.0 * sh.h
    for x0, x1, s in sp.zones:
        n = link_count(x0, x1, s)
        sh.dim((x0, h), (x1, h), (x0, yz), text=f"{n}Ø{sp.phi_w}/{fmt(s)}")
    # supports and spans dimensioned below
    xs = []
    for s in sups:
        xs += [s["x"] - s["t"] / 2, s["x"] + s["t"] / 2]
    yd = -sp.below - 2.5 * sh.h
    sh.hchain(xs, -sp.below, yd)
    sh.dim((x_l, -sp.below), (x_r, -sp.below), (x_l, yd - 2.6 * sh.h))
    sh.dim((x_r, 0), (x_r, h), (x_r + 3.0 * sh.h, 0), vertical=True)
    # section marks
    for lab, x, *_ in sp.sections:
        for y0_, y1_ in ((-sp.below + 6, -sp.below + 14), (h + up - 14, h + up - 6)):
            sh.line((x, y0_), (x, y1_), "D-CONCRETE")
        sh.text(lab.split("-")[0], (x + 1.2 * sh.h, -sp.below + 10), 0.9 * sh.h)
        sh.text(lab.split("-")[0], (x + 1.2 * sh.h, h + up - 10), 0.9 * sh.h)
    y_low = yd - 5.5 * sh.h
    # ------------------------------------------------------------ sections
    xs0 = x_r + 9 * sh.h
    y_sec = -sp.below
    if draw_sections:
        xs0, y_sec = draw_beam_sections(sh, sp, xs0, h)
    # ------------------------------------------------------------ bars drawn separately
    if draw_list:
        y_low = bar_list(sh, sp.runs, y_low)
    if getattr(sp, "shift", None):
        y_low = draw_shift(sh, sp, y_low - 4 * sh.h)
    if sched:
        y_low = min(schedule(sh, el, x_r + 9 * sh.h, y_sec - 3 * sh.h) - 2 * sh.h, y_low)
    return y_low


def draw_beam_sections(sh, sp, x0, h):
    bw = sp.bw
    x_first = x0
    for lab, x, bot, top, side in sp.sections:
        fl = min(30.0, 1.5 * bw) if sp.hf > 0 else 0.0
        sh.text(lab, (x0 + bw / 2, h + 3.0 * sh.h), 1.1 * sh.h)
        if fl:
            sh.pline([(x0 - fl, h - sp.hf), (x0, h - sp.hf), (x0, 0), (x0 + bw, 0), (x0 + bw, h - sp.hf),
                      (x0 + bw + fl, h - sp.hf)])
            sh.line((x0 - fl, h), (x0 + bw + fl, h))
            sh.line((x0 - fl, h), (x0 - fl, h - sp.hf), "D-HIDDEN")
            sh.line((x0 + bw + fl, h), (x0 + bw + fl, h - sp.hf), "D-HIDDEN")
        else:
            sh.rect(x0, 0, x0 + bw, h)
        sh.rect(x0 + C, C, x0 + bw - C, h - C, "D-LINKS")
        pw = sp.phi_w / 10
        for grp, level in ((bot, "bot"), (top, "top")):
            for k, (b, n) in enumerate(grp):
                y = bar_y(level, h, b.phi, sp.phi_w) + (k * (b.phi / 10 + 2.5) * (1 if level == "bot" else -1))
                xa, xb = x0 + C + pw + b.phi / 20, x0 + bw - C - pw - b.phi / 20
                xs_ = [xa + i * (xb - xa) / max(n - 1, 1) for i in range(n)] if n > 1 else [(xa + xb) / 2]
                for xx in xs_:
                    sh.dot((xx, y), b.phi)
                ly = -2.4 * sh.h - 2.4 * sh.h * k if level == "bot" else h + 1.6 * sh.h + 2.4 * sh.h * k
                lx = x0 + bw + fl + 2.5 * sh.h
                sh.bubble(b.pos, (lx, ly), (xs_[-1], y))
                sh.text(f"{n}Ø{b.phi}", (lx + 1.5 * sh.h, ly), 0.9 * sh.h, align=ML)
        if side:
            b, n = side
            for xx in (x0 + C + pw + b.phi / 20, x0 + bw - C - pw - b.phi / 20):
                ys_ = [h * (i + 1) / (n + 1) for i in range(n)]
                for yy in ys_:
                    sh.dot((xx, yy), b.phi)
            lx = x0 + bw + fl + 2.5 * sh.h
            sh.bubble(b.pos, (lx, h / 2), (x0 + bw - C - pw - b.phi / 20, h / 2))
            sh.text(f"2x{n}Ø{b.phi}", (lx + 1.5 * sh.h, h / 2), 0.9 * sh.h, align=ML)
        if sp.link is not None:
            sh.bubble(sp.link.pos, (x0 - fl - 2.0 * sh.h, h * 0.35), (x0 + C, h * 0.35))
        sh.dim((x0, 0), (x0 + bw, 0), (x0, -1.3 * sh.h))
        sh.dim((x0 - fl, 0), (x0 - fl, h), (x0 - fl - 3.6 * sh.h, 0), vertical=True)
        if fl:
            sh.dim((x0 - fl, h), (x0 - fl, h - sp.hf), (x0 - fl - 1.6 * sh.h, h), vertical=True)
        x0 += bw + 2 * fl + 14 * sh.h
    # link (and tie) shapes under the sections
    y = -7.0 * sh.h
    if sp.link is not None:
        b = sp.link
        w, hh = b.segs[0], b.segs[1]
        draw_link(sh, sp.el, b, x_first + 2 * sh.h, y - hh, w, hh)
        y -= hh + 3 * sh.h
    if sp.tie is not None:
        draw_tie(sh, sp.el, sp.tie, x_first + 2 * sh.h, y, sp.tie.segs[0])
        y -= 3 * sh.h
    return x0, y


# ---------------------------------------------------------------- B21
def beam_B21(P):
    inp, R = P.inp, P.res["VI"]
    D = R["design"]
    r, shr = D["r"], D["sh"]
    bw, h, lcl, t = inp.B21_b, R["h"], D["lcl"], 25.0
    hf = P.res.get("IV", {}).get("hf", 12)
    el = Element("B21", "Beam B21 - simply supported beam (axis 5, A-B)", 25)
    phiw = shr["phi_w"]
    L = t + lcl + t
    b1 = el.bar(r["phi"], [], "bottom")
    l1 = anchor_leg(r["phi"], h)
    b1.segs = [l1, L - 2 * C, l1]
    _, _, phit, nt_ = beam_bars(max(0.15 * r["As_prov"], 2 * BAR_AREA[12]), bw * 10, dias=(12, 14, 16, 18, 20))
    l2 = anchor_leg(phit, h)
    b2 = el.bar(phit, [l2, L - 2 * C, l2], "top")
    lk = el.bar(phiw, link_segs(bw - 2 * C, h - 2 * C, phiw), "links", "link")
    s1 = shr["s"] / 10
    s2 = min(2 * s1, 0.75 * D["d"] / 10, 30.0)
    s2 = max(s2, s1)
    zones = [(t, t + lcl / 4, s1), (t + lcl / 4, t + 3 * lcl / 4, s2), (t + 3 * lcl / 4, t + lcl, s1)]
    if abs(s2 - s1) < 0.1:
        zones = [(t, t + lcl, s1)]
    sp = BeamSpec(el, bw, h, hf,
                  supports=[dict(x=t / 2, t=t, kind="col", label="C13"), dict(x=L - t / 2, t=t, kind="col",
                                                                               label="C10")],
                  runs=[dict(bar=b1, level="bot", x0=C, x1=L - C, legs=(l1, l1), n=r["n"], tag=0.3),
                        dict(bar=b2, level="top", x0=C, x1=L - C, legs=(l2, l2), n=nt_, tag=0.7)],
                  zones=zones, link=lk, phi_w=phiw,
                  sections=[("1-1", L / 2, [(b1, r["n"])], [(b2, nt_)], None)])
    dg = D.get("diag")
    if dg:
        sp.shift = dict(x0=t / 2, X=dg["X"], Mpos=dg["M"], zp=r["zeta"] * D["d"] / 1000, d=D["d"],
                        cot=dg["cot"], V=dg["V"], fyd=inp.fyk / 1.15, bot=[(b1, r["n"])])
    return el, sp


# ---------------------------------------------------------------- torsion beam
def beam_torsion(P):
    inp, R = P.inp, P.res["VII"]
    D = R["design"]
    bw, h, lcl, t = inp.BT_b, R["h"], D["lcl"], 25.0
    el = Element("BT", "Beam on axis E (3-4) - bending and torsion", 25)
    phiw = D["phi_w"]
    L = t + lcl + t
    (pb, nb), (pt, ntp), (ps, ns) = D["bot"], D["top"], D["side"]
    lb, lt = anchor_leg(pb, h), anchor_leg(pt, h)
    b1 = el.bar(pb, [lb, L - 2 * C, lb], "bottom")
    b2 = el.bar(pt, [lt, L - 2 * C, lt], "top")
    b3 = el.bar(ps, [L - 2 * C], "side bars (torsion)")
    lk = el.bar(phiw, link_segs(bw - 2 * C, h - 2 * C, phiw), "closed links (torsion)", "link")
    sp = BeamSpec(el, bw, h, 0.0,
                  supports=[dict(x=t / 2, t=t, kind="wall", label="axis 3"),
                            dict(x=L - t / 2, t=t, kind="wall", label="axis 4")],
                  runs=[dict(bar=b1, level="bot", x0=C, x1=L - C, legs=(lb, lb), n=nb, tag=0.3),
                        dict(bar=b2, level="top", x0=C, x1=L - C, legs=(lt, lt), n=ntp, tag=0.7),
                        dict(bar=b3, level="side", x0=C, x1=L - C, legs=(0, 0), n=2 * ns, tag=0.5)],
                  zones=[(t, t + lcl, D["s"] / 10)], link=lk, phi_w=phiw,
                  sections=[("1-1", L / 2, [(b1, nb)], [(b2, ntp)], (b3, ns))])
    return el, sp


# ---------------------------------------------------------------- B5
def beam_B5(P):
    inp, R = P.inp, P.res["VIII"]
    D = R["design"]
    r1, rB, shr = D["r1"], D["rB"], D["sh"]
    bw, h, lcl = inp.B5_b, R["h"], D["lcl"]
    t1, t2 = 25.0, inp.B15_b
    hf = P.res.get("II", {}).get("hf", 12)
    hB15 = P.res.get("X", {}).get("hB15", h + 20)
    el = Element("B5", "Beam B5 - continuous beam over the frame beam B15", 25)
    phiw = shr["phi_w"]
    xB = t1 + lcl + t2 / 2                      # axis of B15
    L = t1 + 2 * lcl + t2 + t1
    l1 = anchor_leg(r1["phi"], h)
    b1 = el.bar(r1["phi"], [l1, (t1 - C) + lcl + (t2 - C)], "bottom, each span")
    ext = ceil5(0.3 * lcl)
    b2 = el.bar(rB["phi"], [t2 + 2 * ext], "top over B15")
    phia = 10
    lap = ceil5(40 * phia / 10)
    la = 15.0
    b3 = el.bar(phia, [la, (t1 - C) + lcl + t2 / 2 + lap / 2], "top assembly bars")
    _, _, p4, n4 = beam_bars(max(0.25 * r1["As_prov"], 2 * BAR_AREA[12]), bw * 10, dias=(12, 14, 16, 18, 20))
    l4 = anchor_leg(p4, h)
    b4 = el.bar(p4, [l4, (t1 - C) + ceil5(0.2 * lcl)], "top at the end supports")
    lk = el.bar(phiw, link_segs(bw - 2 * C, h - 2 * C, phiw), "links", "link")
    s1 = shr["s"] / 10
    s2 = max(min(2 * s1, 30.0, 0.75 * (h - 5)), s1)
    zones = []
    for xa in (t1, xB + t2 / 2):
        xb = xa + lcl
        if abs(s2 - s1) < 0.1:
            zones.append((xa, xb, s1))
        else:
            zones += [(xa, xa + lcl / 4, s1), (xa + lcl / 4, xb - lcl / 4, s2), (xb - lcl / 4, xb, s1)]
    runs = [dict(bar=b1, level="bot", x0=C, x1=t1 + lcl + t2 - C, legs=(l1, 0), n=r1["n"], tag=0.35),
            dict(bar=b1, level="bot", x0=L - C - b1.segs[1], x1=L - C, legs=(0, l1), n=r1["n"], tag=0.65,
                 silent=True),
            dict(bar=b2, level="top", x0=xB - t2 / 2 - ext, x1=xB + t2 / 2 + ext, n=rB["n"], tag=0.5),
            dict(bar=b3, level="top", x0=C, x1=C + b3.segs[1], legs=(la, 0), n=2, tag=0.45),
            dict(bar=b3, level="top", x0=L - C - b3.segs[1], x1=L - C, legs=(0, la), n=2, silent=True),
            dict(bar=b4, level="top", x0=C, x1=C + b4.segs[1], legs=(l4, 0), n=n4, tag=0.6),
            dict(bar=b4, level="top", x0=L - C - b4.segs[1], x1=L - C, legs=(0, l4), n=n4, silent=True)]
    sp = BeamSpec(el, bw, h, hf,
                  supports=[dict(x=t1 / 2, t=t1, kind="wall", label="axis 1"),
                            dict(x=xB, t=t2, kind="beam", depth=hB15, label="B15"),
                            dict(x=L - t1 / 2, t=t1, kind="wall", label="axis 3")],
                  runs=runs, zones=zones, link=lk, phi_w=phiw,
                  sections=[("1-1", t1 + lcl / 2, [(b1, r1["n"])], [(b3, 2)], None),
                            ("2-2", xB - t2 / 2 - 25, [(b1, r1["n"])], [(b2, rB["n"]), (b3, 2)], None)])
    dg = D.get("diag")
    if dg:
        sp.shift = dict(x0=t1 / 2, X=dg["X"], Mpos=dg["Mmax"], Mneg=dg["Mmin"], zp=r1["zeta"] * D["d"] / 1000,
                        zn=rB["zeta"] * D["d"] / 1000, d=D["d"], cot=dg["cot"], V=dg["V"], fyd=inp.fyk / 1.15,
                        bot=[(b1, r1["n"])],
                        top=[(b3, 2, (C, L - C)), (b2, rB["n"], (xB - t2 / 2 - ext, xB + t2 / 2 + ext))])
    return el, sp


# ============================================================================
# columns
# ============================================================================
def column_section(sh, x0, y0, W, D_, n, phi, phi_w, bar, link, tie=None, title=None, dims=True,
                   layout=None, tie2=None):
    """Column section W (horizontal) x D_ (vertical); n/2 bars on the left and
    right faces (the faces perpendicular to the bending). layout=(n_long, n_mid): frame
    column - n_long bars along the top and bottom faces (W), n_mid extra bars on the left and
    right faces, cross ties at the interior bars (tie across D_, tie2 across W)."""
    if layout is not None:
        return _column_section_frame(sh, x0, y0, W, D_, n, phi, phi_w, bar, link, tie, tie2, title, dims, layout)
    sh.rect(x0, y0, x0 + W, y0 + D_)
    sh.rect(x0 + C, y0 + C, x0 + W - C, y0 + D_ - C, "D-LINKS")
    k = max(n // 2, 1)
    off = C + phi_w / 10 + phi / 20
    ys = [y0 + off + i * (D_ - 2 * off) / max(k - 1, 1) for i in range(k)] if k > 1 else [y0 + D_ / 2]
    for xx in (x0 + off, x0 + W - off):
        for yy in ys:
            sh.dot((xx, yy), phi)
    if tie is not None and k > 2:
        for yy in ys[1:-1]:
            sh.line((x0 + C, yy), (x0 + W - C, yy), "D-LINKS")
    if title:
        sh.text(title, (x0 + W / 2, y0 + D_ + 2.2 * sh.h), 1.1 * sh.h)
    sh.bubble(bar.pos, (x0 + W + 2.4 * sh.h, y0 + D_ + 1.0 * sh.h), (x0 + W - off, ys[-1]))
    sh.text(f"{n}Ø{phi}", (x0 + W + 3.8 * sh.h, y0 + D_ + 1.0 * sh.h), 0.9 * sh.h, align=ML)
    sh.bubble(link.pos, (x0 - 2.4 * sh.h, y0 + D_ / 2), (x0 + C, y0 + D_ / 2))
    if tie is not None and k > 2:
        sh.bubble(tie.pos, (x0 + W + 2.4 * sh.h, y0 + D_ / 2), (x0 + W - C, ys[1]))
    if dims:
        sh.dim((x0, y0), (x0 + W, y0), (x0, y0 - 1.6 * sh.h))
        sh.dim((x0 + W, y0), (x0 + W, y0 + D_), (x0 + W + 1.6 * sh.h, y0), vertical=True)


def _column_section_frame(sh, x0, y0, W, D_, n, phi, phi_w, bar, link, tie, tie2, title, dims, layout):
    nl, nm = layout
    sh.rect(x0, y0, x0 + W, y0 + D_)
    sh.rect(x0 + C, y0 + C, x0 + W - C, y0 + D_ - C, "D-LINKS")
    off = C + phi_w / 10 + phi / 20
    xs = [x0 + off + i * (W - 2 * off) / (nl - 1) for i in range(nl)]
    ys = [y0 + off + i * (D_ - 2 * off) / (nm + 1) for i in range(1, nm + 1)]
    for xx in xs:
        for yy in (y0 + off, y0 + D_ - off):
            sh.dot((xx, yy), phi)
    for xx in (x0 + off, x0 + W - off):
        for yy in ys:
            sh.dot((xx, yy), phi)
    if tie is not None:
        for xx in xs[1:-1]:
            sh.line((xx, y0 + C), (xx, y0 + D_ - C), "D-LINKS")
        if len(xs) > 2:
            sh.bubble(tie.pos, (xs[1] + 1.5 * sh.h, y0 - 2.2 * sh.h), (xs[1], y0 + C + 2))
    if tie2 is not None:
        for yy in ys:
            sh.line((x0 + C, yy), (x0 + W - C, yy), "D-LINKS")
        if ys:
            sh.bubble(tie2.pos, (x0 - 2.4 * sh.h, ys[0] - 1.6 * sh.h), (x0 + C, ys[0]))
    if title:
        sh.text(title, (x0 + W / 2, y0 + D_ + 2.2 * sh.h), 1.1 * sh.h)
    sh.bubble(bar.pos, (x0 + W + 2.4 * sh.h, y0 + D_ + 1.0 * sh.h), (xs[-1], y0 + D_ - off))
    sh.text(f"{n}Ø{phi}", (x0 + W + 3.8 * sh.h, y0 + D_ + 1.0 * sh.h), 0.9 * sh.h, align=ML)
    sh.bubble(link.pos, (x0 - 2.4 * sh.h, y0 + D_ - 0.3 * D_), (x0 + C, y0 + D_ - 0.3 * D_))
    if dims:
        sh.dim((x0, y0), (x0 + W, y0), (x0, y0 - 5.6 * sh.h))
        sh.dim((x0 + W, y0), (x0 + W, y0 + D_), (x0 + W + 1.6 * sh.h, y0), vertical=True)


def column_C10(P):
    inp, R = P.inp, P.res["IX"]
    D = R["design"]
    (_, _, p0, n0), (_, _, p1, n1) = D["sec"][0], D["sec"][1]
    el = Element("C10", "Column C10 - first and second storey", 25)
    hB = P.res.get("VI", {}).get("h", 60)
    return el, _column(el, P, inp.C10_b, inp.C10_h, p0, n0, p1, n1, D["s_link"] / 10, hB)


def column_frame(P, tag):
    """Column C7 of the frame on axis 2: first storey as designed in section X,
    the same bars continued in the second storey."""
    inp, R = P.inp, P.res["X"]
    bc, hc = (inp.C7_b, inp.C7_h) if tag == "C7" else (inp.C1_b, inp.C1_h)
    name = "Column C7 (axis 2 / C)" if tag == "C7" else "Columns C1, C12 (axis 2 / A, E)"
    el = Element(tag, f"{name} - frame on axis 2, first and second storey", 25)
    c7 = R["design"].get("c7")
    if c7 is None:
        txt, As, phi, n = R["design"]["cols"][tag]
        return el, _column(el, P, bc, hc, phi, n, phi, n, min(20 * phi / 10, bc, 40.0), R["hB15"])
    L1, L2 = c7["lay"][1], c7["lay"][2]
    return el, _column(el, P, bc, hc, L1["phi"], L1["n"], L2["phi"], L2["n"], c7["s"], R["hB15"],
                       lays=((L1["n_long"], L1["n_mid"]), (L2["n_long"], L2["n_mid"])), s_c=c7["s_c"],
                       phiw=c7["phiw"], names=("4-4", "6-6"))


def _column(el, P, bc, hc, p0, n0, p1, n1, s, hB, lays=None, s_c=None, phiw=None, names=("0-0", "1-1")):
    inp = P.inp
    phiw = phiw or (10 if max(p0, p1) >= 25 else 8)
    s_cr = s_c or math.floor(0.6 * s)
    base = -50.0
    lv1, lv2 = inp.hb, inp.hb + inp.hs
    lap1 = ceil5(50 * p1 / 10)
    lap2 = ceil5(50 * p1 / 10)
    b1 = el.bar(p0, [lv1 + lap1 - base], f"storey 1 (section {names[0]})")
    b2 = el.bar(p1, [lv2 + lap2 - lv1], f"storey 2 (section {names[1]})")
    lk = el.bar(phiw, link_segs(hc - 2 * C, bc - 2 * C, phiw), "links", "link")
    hook = max(10 * phiw / 10, 7.0)
    tie2 = None
    if lays is None:
        tie = el.bar(phiw, [bc - 2 * C, hook, hook], "cross ties", "tie") if max(n0, n1) // 2 > 2 else None
        nties = (1, 1)
        nties2 = (0, 0)
    else:
        nties = tuple(max(L[0] - 2, 0) for L in lays)       # across b, at the interior bars of the long sides
        nties2 = tuple(L[1] for L in lays)                   # across h, at the extra bars of the short sides
        tie = el.bar(phiw, [bc - 2 * C, hook, hook], "cross ties (across b)", "tie") if max(nties) else None
        tie2 = el.bar(phiw, [hc - 2 * C, hook, hook], "cross ties (across h)", "tie") if max(nties2) else None
    return dict(bc=bc, hc=hc, b1=b1, b2=b2, n0=n0, n1=n1, p0=p0, p1=p1, lk=lk, tie=tie, tie2=tie2, s=s, s_cr=s_cr,
                base=base, lv1=lv1, lv2=lv2, hB=hB, lap1=lap1, lap2=lap2, phiw=phiw, lays=lays, names=names,
                nties=nties, nties2=nties2)


def draw_column_C10(sh, el, d):
    hc, bc = d["hc"], d["bc"]
    base, lv1, lv2, hB = d["base"], d["lv1"], d["lv2"], d["hB"]
    top = lv2 + 60
    x0, x1 = 0.0, hc
    # concrete: column, beams at the floors (stubs), slab
    for xx in (x0, x1):
        sh.line((xx, base), (xx, lv1 - hB))
        sh.line((xx, lv1), (xx, lv2 - hB))
        sh.line((xx, lv2), (xx, top))
    for lv in (lv1, lv2):
        sh.rect(x0 - 80, lv - hB, x0, lv)
        sh.rect(x1, lv - hB, x1 + 80, lv)
    sh.line((x0 - 100, base), (x1 + 100, base))
    sh.text("top of the footing", (x1 + 102, base + 0.8 * sh.h), 0.8 * sh.h, align=ML)
    # bars: storey 1 and 2 (offset inside to show the laps)
    off = C + d["phiw"] / 10 + d["p0"] / 20
    lays = d.get("lays")
    k0 = lays[0][0] if lays else max(d["n0"] // 2, 1)
    xs0 = [x0 + off + i * (hc - 2 * off) / max(k0 - 1, 1) for i in range(k0)]
    for xx in xs0:
        sh.line((xx, base), (xx, lv1 + d["lap1"]), "D-BARS")
    k1 = lays[1][0] if lays else max(d["n1"] // 2, 1)
    off1 = off + 2.5
    xs1 = [x0 + off1 + i * (hc - 2 * off1) / max(k1 - 1, 1) for i in range(k1)]
    for xx in xs1:
        sh.line((xx, lv1), (xx, lv2 + d["lap2"]), "D-BARS")
    d["b1"].n += d["n0"]
    d["b2"].n += d["n1"]
    sh.bubble(d["b1"].pos, (x1 + 3 * sh.h, base + 0.45 * (lv1 - base)), (xs0[-1], base + 0.45 * (lv1 - base)))
    sh.bubble(d["b2"].pos, (x1 + 3 * sh.h, lv1 + 0.55 * (lv2 - lv1)), (xs1[-1], lv1 + 0.55 * (lv2 - lv1)))
    # links: critical zones (0.6·s) at the ends of every storey and in the laps
    s, s_cr = d["s"], d["s_cr"]
    lcr = max(hc, 60.0)
    zones = [(base, base + lcr, s_cr), (base + lcr, lv1 - hB - lcr, s), (lv1 - hB - lcr, lv1, s_cr),
             (lv1, lv1 + max(lcr, d["lap1"]), s_cr), (lv1 + max(lcr, d["lap1"]), lv2 - hB - lcr, s),
             (lv2 - hB - lcr, lv2, s_cr), (lv2, top, s_cr)]
    tot = 0
    nties, nties2 = d.get("nties", (1, 1)), d.get("nties2", (0, 0))
    for iz, (ya, yb, ss) in enumerate(zones):
        if yb - ya < 5:
            continue
        n = link_count(ya, yb, ss)
        tot += n
        st = 0 if iz < 3 else 1
        if d["tie"] is not None:
            d["tie"].n += n * nties[st]
        if d.get("tie2") is not None:
            d["tie2"].n += n * nties2[st]
        step = (yb - ya - 10) / max(n - 1, 1)
        for i in range(n):
            y = ya + 5 + i * step
            sh.line((x0 + C, y), (x1 - C, y), "D-LINKS")
        sh.dim((x0 - 100, ya), (x0 - 100, yb), (x0 - 100 - 2.0 * sh.h, ya), vertical=True,
               text=f"{n}Ø{d['phiw']}/{fmt(ss)}")
    d["lk"].n += tot
    sh.bubble(d["lk"].pos, (x0 - 2.5 * sh.h, lv1 - hB - lcr / 2), (x0 + C, lv1 - hB - lcr / 2))
    # levels and dimensions
    for lv, name in ((lv1, f"+{lv1 / 100:.2f}"), (lv2, f"+{lv2 / 100:.2f}")):
        sh.text(name, (x1 + 85, lv + 0.9 * sh.h), 0.9 * sh.h, align=BL)
    sh.vchain([base, lv1 - hB, lv1, lv2 - hB, lv2], x1 + 80, x1 + 80 + 6 * sh.h)
    sh.dim((x0, top), (x1, top), (x0, top + 2 * sh.h))
    sh.dim((x1, lv1), (x1, lv1 + d["lap1"]), (x1 + 2.6 * sh.h, lv1), vertical=True, text=f"lap {fmt(d['lap1'])}")
    sh.dim((x1, lv2), (x1, lv2 + d["lap2"]), (x1 + 2.6 * sh.h, lv2), vertical=True, text=f"lap {fmt(d['lap2'])}")
    # section marks
    names = d.get("names", ("0-0", "1-1"))
    for lab, y in ((names[0].split("-")[0], base + 0.5 * (lv1 - hB - base)),
                   (names[1].split("-")[0], lv1 + 0.5 * (lv2 - hB - lv1))):
        sh.line((x0 - 14, y), (x0 - 6, y))
        sh.line((x1 + 6, y), (x1 + 14, y))
        sh.text(lab, (x0 - 10, y + 1.2 * sh.h), 0.9 * sh.h)
        sh.text(lab, (x1 + 10, y + 1.2 * sh.h), 0.9 * sh.h)
    # sections
    xs = x1 + 80 + 18 * sh.h
    column_section(sh, xs, lv1 - 120, hc, bc, d["n0"], d["p0"], d["phiw"], d["b1"], d["lk"],
                   d["tie"] if not lays or nties[0] else None, f"Section {names[0]}",
                   layout=lays[0] if lays else None, tie2=d.get("tie2") if lays and nties2[0] else None)
    column_section(sh, xs, lv2 - 80, hc, bc, d["n1"], d["p1"], d["phiw"], d["b2"], d["lk"],
                   d["tie"] if not lays or nties[1] else None, f"Section {names[1]}",
                   layout=lays[1] if lays else None, tie2=d.get("tie2") if lays and nties2[1] else None)
    # bars drawn separately
    xb = xs + hc + 16 * sh.h
    draw_shape(sh, d["b1"], [(xb, base), (xb, base + d["b1"].segs[0])],
               label_at=(xb + 6 * sh.h, base - 2 * sh.h))
    draw_shape(sh, d["b2"], [(xb + 12 * sh.h, lv1), (xb + 12 * sh.h, lv1 + d["b2"].segs[0])],
               label_at=(xb + 18 * sh.h, lv1 - 2 * sh.h))
    draw_link(sh, el, d["lk"], xs, base + 40, d["lk"].segs[0], d["lk"].segs[1])
    if d["tie"] is not None:
        draw_tie(sh, el, d["tie"], xs, base + 10, d["tie"].segs[0])
    if d.get("tie2") is not None:
        draw_tie(sh, el, d["tie2"], xs, base + 25, d["tie2"].segs[0])
    schedule(sh, el, xs, base - 6 * sh.h)


# ============================================================================
# frame on axis 2
# ============================================================================
def frame_axis2(P):
    inp, G, R = P.inp, P.G, P.res["X"]
    D = R["design"]
    r1, r2, r3, shr = D["r1"], D["r2"], D["r3"], D["sh"]
    hB, bw = R["hB15"], inp.B15_b
    hf = P.res.get("II", {}).get("hf", 12)
    yC = G.Y["C"]
    tA, tC = inp.C1_h, inp.C7_h
    el = Element("FR", "Frame on axis 2 - beam B15 and column C7 (first storey)", 25)
    phiw = shr["phi_w"]
    xA, xC, xE = tA / 2, tA / 2 + yC, tA / 2 + 2 * yC
    L = xE + tA / 2
    lcl = yC - tA / 2 - tC / 2
    l1 = anchor_leg(r1["phi"], hB)
    b1 = el.bar(r1["phi"], [l1, (tA - C) + lcl + (tC - C)], "B15 bottom, each span")
    ext = ceil5(0.3 * lcl)
    b2 = el.bar(r2["phi"], [tC + 2 * ext], "B15 top over C7")
    l3 = max(hB - 2 * C - 5, 20.0)
    b3 = el.bar(r3["phi"], [l3, (tA - C) + ext], "B15 top over C1 / C12")
    phia = 12
    lap = ceil5(40 * phia / 10)
    b4 = el.bar(phia, [15.0, (tA - C) + lcl + tC / 2 + lap / 2], "B15 top assembly bars")
    lk = el.bar(phiw, link_segs(bw - 2 * C, hB - 2 * C, phiw), "B15 links", "link")
    s1 = shr["s"] / 10
    s2 = max(min(2 * s1, 30.0, 0.75 * (hB - 5)), s1)
    zones = []
    for xa in (tA, xC + tC / 2):
        xb = xa + lcl
        if abs(s2 - s1) < 0.1:
            zones.append((xa, xb, s1))
        else:
            zones += [(xa, xa + lcl / 4, s1), (xa + lcl / 4, xb - lcl / 4, s2), (xb - lcl / 4, xb, s1)]
    hang = [(xA + y * 100, D["nhang"]) for y in D["ys_sec"] if abs(y * 100 - yC) > 1]
    runs = [dict(bar=b1, level="bot", x0=C, x1=C + b1.segs[1], legs=(l1, 0), n=r1["n"], tag=0.35),
            dict(bar=b1, level="bot", x0=L - C - b1.segs[1], x1=L - C, legs=(0, l1), n=r1["n"], silent=True),
            dict(bar=b2, level="top", x0=xC - tC / 2 - ext, x1=xC + tC / 2 + ext, n=r2["n"], tag=0.5),
            dict(bar=b3, level="top", x0=C, x1=C + b3.segs[1], legs=(l3, 0), n=r3["n"], tag=0.6),
            dict(bar=b3, level="top", x0=L - C - b3.segs[1], x1=L - C, legs=(0, l3), n=r3["n"], silent=True),
            dict(bar=b4, level="top", x0=C, x1=C + b4.segs[1], legs=(15.0, 0), n=2, tag=0.45),
            dict(bar=b4, level="top", x0=L - C - b4.segs[1], x1=L - C, legs=(0, 15.0), n=2, silent=True)]
    # columns (first storey): bars with a foot in the footing, lap above the slab
    Hf = P.res.get("XI", {}).get("H", 80)
    Lf = P.res.get("XI", {}).get("L", 300)
    below = inp.hb - hB                      # soffit of the beam above the top of the footing
    cols = {}
    for tag, (txt, As, phi, n) in D["cols"].items():
        lapc = ceil5(50 * phi / 10)
        foot = 30.0
        vert = (Hf - C_FOOT - 3) + below + hB + lapc
        cb = el.bar(phi, [foot, vert], f"column {tag}")
        cw = 10 if phi >= 25 else 8
        bcol, hcol = (inp.C7_b, inp.C7_h) if tag == "C7" else (inp.C1_b, inp.C1_h)
        c7 = D.get("c7") if tag == "C7" else None
        if c7:
            cw = c7["phiw"]
        ck = el.bar(cw, link_segs(hcol - 2 * C, bcol - 2 * C, cw), f"links {tag}", "link")
        cols[tag] = dict(bar=cb, link=ck, phi=phi, n=n, phiw=cw, b=bcol, h=hcol, lap=lapc,
                         s=c7["s"] if c7 else min(20 * phi / 10, bcol, 40.0),
                         s_c=c7["s_c"] if c7 else None,
                         lay=(c7["lay"][1]["n_long"], c7["lay"][1]["n_mid"]) if c7 else None)
    sp = BeamSpec(el, bw, hB, hf,
                  supports=[dict(x=xA, t=tA, kind="col", label="C1 (axis A)", below=below),
                            dict(x=xC, t=tC, kind="col", label="C7 (axis C)", below=below + Hf),
                            dict(x=xE, t=tA, kind="col", label="C12 (axis E)", below=below)],
                  runs=runs, zones=zones, link=lk, phi_w=phiw, hangers=hang, below=below + Hf,
                  sections=[("1-1", tA + lcl / 2, [(b1, r1["n"])], [(b4, 2)], None),
                            ("2-2", xC - tC / 2 - 25, [(b1, r1["n"])], [(b2, r2["n"]), (b4, 2)], None)])
    dg = D.get("diag")
    if dg:
        sp.shift = dict(x0=xA, X=dg["X"], Mpos=dg["Mmax"], Mneg=dg["Mmin"], zp=r1["zeta"] * D["d"] / 1000,
                        zn=r2["zeta"] * D["d"] / 1000, d=D["d"], cot=dg["cot"], V=dg["V"], fyd=inp.fyk / 1.15,
                        bot=[(b1, r1["n"])],
                        top=[(b4, 2, (C, L - C)), (b2, r2["n"], (xC - tC / 2 - ext, xC + tC / 2 + ext)),
                             (b3, r3["n"], (C, C + b3.segs[1])), (b3, r3["n"], (L - C - b3.segs[1], L - C))])
    return el, sp, dict(cols=cols, below=below, Hf=Hf, Lf=Lf, xs={"C1": xA, "C7": xC, "C12": xE})


def draw_frame(sh, el, sp, fd):
    """Frame: beam B15 (draw_beam) + columns with bars and links + footings."""
    below, Hf, Lf = fd["below"], fd["Hf"], fd["Lf"]
    y_ft = -below                                  # top of the footings
    for tag, x in fd["xs"].items():
        c = fd["cols"].get(tag)
        if c is None:                              # C1, C12: not designed - outline only
            sh.line((x - 60, y_ft), (x + 60, y_ft))
            sh.text(f"{tag} - outline only (not designed)", (x, y_ft - 2.0 * sh.h), 0.8 * sh.h)
            continue
        # footing outline (size of the footing under C7)
        sh.rect(x - Lf / 2, y_ft - Hf, x + Lf / 2, y_ft)
        sh.rect(x - Lf / 2 - 10, y_ft - Hf - 10, x + Lf / 2 + 10, y_ft - Hf, "D-HIDDEN")
        hcol = c["h"]
        off = C + c["phiw"] / 10 + c["phi"] / 20
        yb = y_ft - Hf + C_FOOT + 3
        ytop = sp.h + c["lap"]
        for xx, sgn in ((x - hcol / 2 + off, -1), (x + hcol / 2 - off, 1)):
            sh.pline([(xx + sgn * c["bar"].segs[0], yb), (xx, yb), (xx, ytop)], "D-BARS")
        c["bar"].n += c["n"]
        # links: 0.6·s near the footing and the beam, s in the middle, 0.6·s in the joint
        s = c["s"]
        s_cr = c.get("s_c") or math.floor(0.6 * s)
        lcr = max(hcol, 60.0)
        zones = [(y_ft, y_ft + lcr, s_cr), (y_ft + lcr, -lcr, s), (-lcr, 0, s_cr), (0, sp.h, s_cr),
                 (sp.h, ytop, s_cr)]
        tot = 0
        for ya, yb_, ss in zones:
            if yb_ - ya < 6:
                continue
            n = link_count(ya, yb_, ss)
            tot += n
            st = (yb_ - ya - 10) / max(n - 1, 1)
            for i in range(n):
                y = ya + 5 + i * st
                sh.line((x - hcol / 2 + C, y), (x + hcol / 2 - C, y), "D-LINKS")
        c["link"].n += tot
        sh.dim((x + hcol / 2, sp.h), (x + hcol / 2, ytop), (x + hcol / 2 + 1.8 * sh.h, sp.h), vertical=True)
        if tag != "C12":
            sh.bubble(c["bar"].pos, (x + hcol / 2 + 3 * sh.h, y_ft + 0.4 * below), (x + hcol / 2 - off, y_ft + 0.4 * below))
            sh.bubble(c["link"].pos, (x - hcol / 2 - 3 * sh.h, y_ft + 0.55 * below), (x - hcol / 2 + C, y_ft + 0.55 * below))
            sh.dim((x - hcol / 2 - 4 * sh.h, y_ft + lcr), (x - hcol / 2 - 4 * sh.h, -lcr),
                   (x - hcol / 2 - 6 * sh.h, y_ft + lcr), vertical=True,
                   text=f"{link_count(y_ft + lcr, -lcr, s)}Ø{c['phiw']}/{fmt(s)}")
    y_low = draw_beam(sh, sp, draw_list=False, sched=False)
    # levels
    sh.text("±0.00 (top of footing)", (fd["xs"]["C12"] + Lf / 2 + 10, y_ft + 0.8 * sh.h), 0.8 * sh.h, align=BL)
    xr = fd["xs"]["C12"] + Lf / 2 + 10
    sh.vchain([y_ft - Hf, y_ft, 0, sp.h], xr, xr + 8 * sh.h)
    # vertical bars of the columns drawn separately, with the lengths of their parts
    xv = xr + 20 * sh.h
    for tag, c in fd["cols"].items():
        who = tag
        b = c["bar"]
        yb = y_ft - Hf + C_FOOT + 3
        ytop = sp.h + c["lap"]
        draw_shape(sh, b, [(xv + b.segs[0], yb), (xv, yb), (xv, ytop)],
                   label_at=(xv + 5.5 * sh.h, yb - 2.8 * sh.h), label=f"{c['n']}Ø{b.phi} L={fmt(b.L)} ({who})")
        sh.vchain([yb, y_ft, 0, sp.h, ytop], xv, xv - 3.0 * sh.h)
        sh.text(f"lap {fmt(c['lap'])}", (xv + 1.2 * sh.h, sp.h + c["lap"] / 2), 0.75 * sh.h, rot=90)
        xv += 30 * sh.h
    # column sections
    xs = sh.box[2] + 6 * sh.h
    for tag, c in fd["cols"].items():
        column_section(sh, xs, -c["b"] - 20, c["h"], c["b"], c["n"], c["phi"], c["phiw"], c["bar"], c["link"],
                       None, f"Column {tag}", layout=c.get("lay"))
        xs += c["h"] + 16 * sh.h
    # bars of the beam drawn separately (also the mirrored ones)
    y = bar_list(sh, sp.runs, min(y_low, y_ft - Hf - 14 * sh.h))
    # links
    x = 0.0
    yb = y - 2 * sh.h
    hmax = 0.0
    for c in fd["cols"].values():
        draw_link(sh, el, c["link"], x, yb - c["link"].segs[1], c["link"].segs[0], c["link"].segs[1])
        x += c["link"].segs[0] + 40 * sh.h
        hmax = max(hmax, c["link"].segs[1])
    link = sp.link
    draw_link(sh, el, link, x, yb - link.segs[1], link.segs[0], link.segs[1])
    schedule(sh, el, sh.box[2] - 26 * sh.h, -fd["below"] - Hf - 4 * sh.h)


# ============================================================================
# pad footing
# ============================================================================
def footing(P):
    inp, R = P.inp, P.res["XI"]
    D = R["design"]
    r = D["r"]
    Lf, Bf, Hf = R["L"], R["B"], R["H"]
    el = Element("F", "Pad footing under column C7", 25)
    s = r["s"] / 10
    leg = 20.0
    b1 = el.bar(r["phi"], [leg, Lf - 2 * C_FOOT, leg], "bottom bars along L")
    b2 = el.bar(r["phi"], [leg, Bf - 2 * C_FOOT, leg], "bottom bars along B")
    b1.n = n_bars(Bf - 2 * C_FOOT, s, 0)
    b2.n = n_bars(Lf - 2 * C_FOOT, s, 0)
    cols = P.res.get("X", {}).get("design", {}).get("cols", {})
    txt, As, phic, nc = cols.get("C7", ("", 0, 16, 8))
    lapc = ceil5(50 * phic / 10)
    b3 = el.bar(phic, [30.0, Hf - C_FOOT - 2 * r["phi"] / 10 + lapc], "starter bars of C7")
    b3.n = nc
    cw = 10 if phic >= 25 else 8
    b4 = el.bar(cw, link_segs(inp.C7_h - 2 * C, inp.C7_b - 2 * C, cw), "links of the starter bars", "link")
    b4.n = 3
    return el, dict(L=Lf, B=Bf, H=Hf, s=s, b1=b1, b2=b2, b3=b3, b4=b4, hc=inp.C7_h, bc=inp.C7_b, nc=nc,
                    phic=phic, lapc=lapc, leg=leg, phi=r["phi"])


def draw_footing(sh, el, d):
    L, B, H, s = d["L"], d["B"], d["H"], d["s"]
    hc, bc = d["hc"], d["bc"]
    # ---------------------------------------------------------------- plan
    sh.text("Plan", (L / 2, B + 7.5 * sh.h), 1.1 * sh.h)
    sh.rect(0, 0, L, B)
    sh.rect((L - hc) / 2, (B - bc) / 2, (L + hc) / 2, (B + bc) / 2)
    cf = C_FOOT
    n1, n2 = d["b1"].n, d["b2"].n
    for i in range(n1):                               # bars along L
        y = cf + i * (B - 2 * cf) / max(n1 - 1, 1)
        sh.line((cf, y), (L - cf, y), "D-LINKS" if i not in (2,) else "D-BARS")
    for i in range(n2):                               # bars along B
        x = cf + i * (L - 2 * cf) / max(n2 - 1, 1)
        sh.line((x, cf), (x, B - cf), "D-LINKS" if i not in (2,) else "D-BARS")
    y2 = cf + 2 * (B - 2 * cf) / max(n1 - 1, 1)
    x2 = cf + 2 * (L - 2 * cf) / max(n2 - 1, 1)
    sh.bubble(d["b1"].pos, (L + 3 * sh.h, y2), (L - cf, y2))
    sh.text(f"{n1}Ø{d['phi']}/{fmt(s)}", (L + 4.5 * sh.h, y2), 0.9 * sh.h, align=ML)
    sh.bubble(d["b2"].pos, (x2, -3 * sh.h), (x2, cf))
    sh.text(f"{n2}Ø{d['phi']}/{fmt(s)}", (x2 + 1.6 * sh.h, -3 * sh.h), 0.9 * sh.h, align=ML)
    sh.hchain([0, (L - hc) / 2, (L + hc) / 2, L], B, B + 1.8 * sh.h)
    sh.dim((0, B), (L, B), (0, B + 4.6 * sh.h))
    sh.vchain([0, (B - bc) / 2, (B + bc) / 2, B], 0, -1.8 * sh.h)
    sh.dim((0, 0), (0, B), (-4.2 * sh.h, 0), vertical=True)
    # ---------------------------------------------------------------- section
    x0 = L + 22 * sh.h
    sh.text("Section", (x0 + L / 2, H + 80 + 3 * sh.h), 1.1 * sh.h)
    sh.rect(x0, 0, x0 + L, H)
    sh.rect(x0 - 10, -10, x0 + L + 10, 0, "D-HIDDEN")
    sh.text("lean concrete 10 cm", (x0 + L + 12, -5), 0.8 * sh.h, align=ML)
    xc0, xc1 = x0 + (L - hc) / 2, x0 + (L + hc) / 2
    sh.line((xc0, H), (xc0, H + 80))
    sh.line((xc1, H), (xc1, H + 80))
    yb1 = cf + d["phi"] / 20
    sh.pline([(x0 + cf, yb1 + d["leg"]), (x0 + cf, yb1), (x0 + L - cf, yb1), (x0 + L - cf, yb1 + d["leg"])],
             "D-BARS")
    yb2 = cf + 3 * d["phi"] / 20
    for i in range(n2):
        sh.dot((x0 + cf + i * (L - 2 * cf) / max(n2 - 1, 1), yb2), d["phi"])
    sh.bubble(d["b1"].pos, (x0 + 0.25 * L, -3.2 * sh.h), (x0 + 0.25 * L, yb1))
    sh.bubble(d["b2"].pos, (x0 + 0.40 * L, -3.2 * sh.h), (x0 + 0.40 * L, yb2))
    off = C + 1 + d["phic"] / 20
    ys = cf + 2 * d["phi"] / 10 + d["phic"] / 20
    for xx, sgn in ((xc0 + off, -1), (xc1 - off, 1)):
        sh.pline([(xx + sgn * 30, ys), (xx, ys), (xx, H + d["lapc"] - 0 * 1)], "D-BARS")
    for i in range(3):
        y = H - 10 - i * (H - 30) / 2
        sh.line((xc0 + C, y), (xc1 - C, y), "D-LINKS")
    sh.bubble(d["b3"].pos, (xc1 + 3 * sh.h, H + 0.5 * d["lapc"]), (xc1 - off, H + 0.5 * d["lapc"]))
    sh.bubble(d["b4"].pos, (xc0 - 3 * sh.h, H - 10), (xc0 + C, H - 10))
    sh.hchain([x0, xc0, xc1, x0 + L], 0, -6 * sh.h)
    sh.vchain([0, H], x0 + L, x0 + L + 2.5 * sh.h)
    sh.dim((xc1, H), (xc1, H + d["lapc"]), (xc1 + 6 * sh.h, H), vertical=True)
    # ---------------------------------------------------------------- bars
    y = -12 * sh.h
    for b in (d["b1"], d["b2"]):
        Lm = b.segs[1]
        draw_shape(sh, b, [(0, y + d["leg"]), (0, y), (Lm, y), (Lm, y + d["leg"])])
        y -= d["leg"] + 5 * sh.h
    b = d["b3"]
    y -= 30
    draw_shape(sh, b, [(0, y - 30), (0, y), (b.segs[1], y)], label_at=(b.segs[1] / 2, y - 4 * sh.h))
    draw_link(sh, el, d["b4"], b.segs[1] + 12 * sh.h, y - d["b4"].segs[1], d["b4"].segs[0], d["b4"].segs[1])
    schedule(sh, el, x0, -14 * sh.h)


# ============================================================================
# stairs
# ============================================================================
def stairs(P):
    inp, R = P.inp, P.res["V"]
    D = R["design"]
    r = D["r"]
    el = Element("ST", "Stairs - flight and landing (axes 3-4)", 10)
    return el, dict(h=R["h"], n=R["n"], hst=R["hst"], bst=R["bst"], lfl=D["lfl"], lla=D["lla"], phi=r["phi"],
                    s=r["s"] / 10, d=inp.d, alpha=D["alpha"], Hfl=inp.hb / 2)


def draw_stairs(sh, el, d):
    h, n, hst, bst = d["h"], d["n"], d["hst"], d["bst"]
    lfl, lla, Hfl = d["lfl"], d["lla"], d["Hfl"]
    a = math.radians(d["alpha"])
    ta, ca = math.tan(a), math.cos(a)
    hv = h / ca                                   # vertical thickness of the waist
    # ---------------------------------------------------------------- concrete
    pts = [(-60, 0), (0, 0)]
    for i in range(n - 1):
        pts += [(i * bst, (i + 1) * hst), ((i + 1) * bst, (i + 1) * hst)]
    pts += [(lfl, Hfl), (lfl + lla, Hfl)]
    sh.pline(pts)
    xk = (Hfl - h + hv) / ta                      # kink of the soffit (flight / landing)
    sh.pline([(-60, -h), (-hv / ta + 0, -h) if False else (0 - 0, -h), (0, -hv), (xk, Hfl - h),
              (lfl + lla, Hfl - h)])
    wall = lfl + lla
    sh.rect(wall, Hfl - h - 60, wall + 25, Hfl + 60)
    sh.line((-60, 0), (-60, -h), "D-HIDDEN")
    sh.text(f"{n - 1} steps {fmt(bst)}/{fmt(hst)}", (0.5 * lfl - 4 * sh.h, 0.5 * Hfl + 6 * sh.h), 1.2 * sh.h,
            rot=math.degrees(a))
    sh.text("±0.00", (-55, 1.2 * sh.h), sh.h, align=BL)
    sh.text(f"+{Hfl / 100:.2f}", (lfl + 10, Hfl + 1.2 * sh.h), sh.h, align=BL)
    # ---------------------------------------------------------------- bars
    cb = C + d["phi"] / 20
    s = d["s"]
    nmain = n_bars(d["d"], s)
    lbd = ceil5(40 * d["phi"] / 10)
    # pos 1: bottom of the flight, continued into the landing (crossing at the kink)
    y_off = -hv + cb / ca                         # line y = x·tanα + y_off
    x_s = -40.0
    y_s = x_s * ta + y_off
    if y_s < -h + cb:                             # stay in the floor slab
        x_s = (-h + cb - y_off) / ta
        y_s = -h + cb
    x_e = (Hfl - cb - y_off) / ta                 # reaches the top of the landing
    b1 = el.bar(d["phi"], [math.hypot(x_e - x_s, (x_e - x_s) * ta)], "bottom of the flight")
    b1.n = nmain
    sh.line((x_s, y_s), (x_e, x_e * ta + y_off), "D-BARS")
    # pos 2: bottom of the landing, continued into the flight
    y2 = Hfl - h + cb
    x2s = wall + 25 - C
    x2e = (y2 - (hst * 0.0) + cb / ca - 0) / ta    # top surface of the waist ~ y = x·tanα
    x2e = min(x2e, xk - lbd)
    b2 = el.bar(d["phi"], [x2s - x2e], "bottom of the landing")
    b2.n = nmain
    sh.line((x2e, y2), (x2s, y2), "D-BARS")
    # pos 3: top bars at the lower support, pos 4: at the wall
    Lt = ceil5(0.25 * (lfl + lla))
    p3s = (-50.0, -cb)
    p3e = (Lt, Lt * ta - cb / ca)
    b3 = el.bar(8, [50.0, math.hypot(p3e[0], p3e[1] + cb)], "top at the lower support")
    b3.n = n_bars(d["d"], 20.0)
    sh.pline([p3s, (0, -cb), p3e], "D-BARS")
    y4 = Hfl - cb
    b4 = el.bar(8, [15.0, (25 - C) + Lt], "top at the wall")
    b4.n = n_bars(d["d"], 20.0)
    sh.pline([(wall + 25 - C, y4 - 15), (wall + 25 - C, y4), (wall - Lt, y4)], "D-BARS")
    # pos 5: distribution bars Ø8/20 (dots)
    b5 = el.bar(8, [d["d"] - 2 * C], "distribution bars")
    cnt = 0
    for x in [x_s + 10 + i * 20 * ca for i in range(int((x_e - x_s - 20) * 1 / (20 * ca)) + 1)]:
        sh.dot((x, x * ta + y_off + 0.9), 8)
        cnt += 1
    for x in [x2s - 10 - i * 20 for i in range(int((x2s - x2e - 20) / 20) + 1)]:
        sh.dot((x, y2 + 0.9), 8)
        cnt += 1
    b5.n = cnt
    sh.bubble(b1.pos, (0.45 * lfl, 0.45 * lfl * ta + y_off - 4 * sh.h), (0.45 * lfl, 0.45 * lfl * ta + y_off))
    sh.bubble(b2.pos, (wall - 0.4 * lla, y2 - 4 * sh.h), (wall - 0.4 * lla, y2))
    sh.bubble(b3.pos, (0.5 * Lt, 0.5 * Lt * ta + 6 * sh.h), (0.5 * Lt, 0.5 * Lt * ta - cb / ca))
    sh.bubble(b4.pos, (wall - 0.5 * Lt, y4 + 4 * sh.h), (wall - 0.5 * Lt, y4))
    sh.bubble(b5.pos, (x_s + 30, (x_s + 30) * ta + y_off - 7 * sh.h), (x_s + 30, (x_s + 30) * ta + y_off))
    # ---------------------------------------------------------------- dimensions
    sh.hchain([0, lfl, wall, wall + 25], -h, -h - 12 * sh.h)
    sh.vchain([0, Hfl], wall + 25, wall + 25 + 4 * sh.h)
    sh.dim((wall, Hfl - h), (wall, Hfl), (wall - 3 * sh.h, Hfl - h), vertical=True)
    # ---------------------------------------------------------------- section across the flight
    x0 = wall + 60 + 8 * sh.h
    sh.text("Section 1-1", (x0 + d["d"] / 2, h + 5 * sh.h), 1.2 * sh.h)
    sh.rect(x0, 0, x0 + d["d"], h)
    for i in range(nmain):
        sh.dot((x0 + 5 + i * (d["d"] - 10) / max(nmain - 1, 1), cb), d["phi"])
    sh.line((x0 + C, cb + d["phi"] / 20 + 0.8), (x0 + d["d"] - C, cb + d["phi"] / 20 + 0.8), "D-BARS")
    sh.bubble(b1.pos, (x0 + d["d"] + 4 * sh.h, cb), (x0 + d["d"] - 5, cb))
    sh.text(f"{nmain}Ø{d['phi']}/{fmt(s)}", (x0 + d["d"] + 6 * sh.h, cb), sh.h, align=ML)
    sh.bubble(b5.pos, (x0 + 0.3 * d["d"], h + 3 * sh.h), (x0 + 0.3 * d["d"], cb + 1.5))
    sh.dim((x0, 0), (x0 + d["d"], 0), (x0, -4 * sh.h))
    sh.dim((x0, 0), (x0, h), (x0 - 4 * sh.h, 0), vertical=True)
    # ---------------------------------------------------------------- bars drawn separately
    y = -h - 40 * sh.h
    ang = math.degrees(a)
    L1 = b1.segs[0]
    draw_shape(sh, b1, [(0, y), (L1 * ca, y + L1 * math.sin(a))], label_at=(L1 * ca / 2, y - 4 * sh.h))
    draw_shape(sh, b2, [(L1 * ca + 30, y), (L1 * ca + 30 + b2.segs[0], y)],
               label_at=(L1 * ca + 30 + b2.segs[0] / 2, y - 4 * sh.h))
    y -= 22 * sh.h
    draw_shape(sh, b3, [(0, y), (50, y), (50 + b3.segs[1] * ca, y + b3.segs[1] * math.sin(a))],
               label_at=(60, y - 4 * sh.h))
    draw_shape(sh, b4, [(L1 * ca + 30, y - 15), (L1 * ca + 30, y), (L1 * ca + 30 + b4.segs[1], y)],
               label_at=(L1 * ca + 30 + b4.segs[1] / 2, y - 6 * sh.h))
    y -= 22 * sh.h
    draw_shape(sh, b5, [(0, y), (b5.segs[0], y)], label_at=(b5.segs[0] / 2, y - 4 * sh.h))
    _ = ang
    schedule(sh, el, x0, -h - 20 * sh.h)


# ============================================================================
# all elements
# ============================================================================
def build(P):
    """List of (element, draw function) for the elements designed in the note."""
    out = []
    res = P.res
    if "VI" in res and "design" in res["VI"]:
        el, sp = beam_B21(P)
        out.append((el, lambda sh, el=el, sp=sp: draw_beam(sh, sp)))
    if "VII" in res and "design" in res["VII"]:
        el, sp = beam_torsion(P)
        out.append((el, lambda sh, el=el, sp=sp: draw_beam(sh, sp)))
    if "VIII" in res and "design" in res["VIII"]:
        el, sp = beam_B5(P)
        out.append((el, lambda sh, el=el, sp=sp: draw_beam(sh, sp)))
    if "X" in res and "design" in res["X"]:
        el, sp, fd = frame_axis2(P)
        out.append((el, lambda sh, el=el, sp=sp, fd=fd: draw_frame(sh, el, sp, fd)))
    if "X" in res and "design" in res["X"]:
        for tag in ("C7",):
            if tag in res["X"]["design"].get("cols", {}):
                el, d = column_frame(P, tag)
                out.append((el, lambda sh, el=el, d=d: draw_column_C10(sh, el, d)))
    if "IX" in res and "design" in res["IX"]:
        el, d = column_C10(P)
        out.append((el, lambda sh, el=el, d=d: draw_column_C10(sh, el, d)))
    if "XI" in res and "design" in res["XI"]:
        el, d = footing(P)
        out.append((el, lambda sh, el=el, d=d: draw_footing(sh, el, d)))
    if "V" in res and "design" in res["V"]:
        el, d = stairs(P)
        out.append((el, lambda sh, el=el, d=d: draw_stairs(sh, el, d)))
    return out


def _reset(el, keep_fixed):
    for b in el.bars:
        if b.kind in ("bar", "link", "tie") and b.desc not in keep_fixed:
            b.n = 0


def place(msp, P, x0, y_top, max_width):
    """Draw all element details in rows under y_top. Returns (elements, lowest y)."""
    items = build(P)
    fixed = {}                              # counts set when the element is created (footing, stairs)
    for el, _ in items:
        fixed[el.key] = {b.pos: b.n for b in el.bars}
    # dry run: sizes
    sizes = []
    for el, fn in items:
        sh = Sheet(None, 0, 0, el.scale)
        fn(sh)
        sizes.append((sh.box[0], sh.box[1], sh.box[2], sh.box[3]))
        for b in el.bars:                   # counts are accumulated while drawing: reset
            b.n = fixed[el.key].get(b.pos, 0)
    # rows
    gap = 250.0
    x, y_row, row_h = x0, y_top, 0.0
    placed = []
    for (el, fn), (bx0, by0, bx1, by1) in zip(items, sizes):
        w, hgt = bx1 - bx0, by1 - by0
        if x > x0 and x + w > x0 + max_width:
            y_row -= row_h + gap
            x, row_h = x0, 0.0
        placed.append((el, fn, x - bx0, y_row - by1 - 60))
        x += w + gap
        row_h = max(row_h, hgt + 60)
    y_low = y_row - row_h
    for el, fn, ox, oy in placed:
        sh = Sheet(msp, ox, oy, el.scale)
        fn(sh)
        sh.text(f"{el.title.upper()}   M 1:{el.scale}", (sh.box[0] + 0.5 * (sh.box[2] - sh.box[0]),
                                                        sh.box[3] + 3 * sh.h), 2.0 * sh.h)
    return [el for el, _ in items], y_low


# ============================================================================
# one DXF file per element
# ============================================================================
FILE_NAMES = {"B21": "Beam_B21", "BT": "Beam_axis_E_torsion", "B5": "Beam_B5", "FR": "Frame_axis_2",
              "C7": "Column_C7", "C10": "Column_C10", "F": "Footing_C7",
              "ST": "Stairs"}


def title_block(sh, el, inp, x1, y0):
    """Title block (right bottom corner of the sheet, x1 = right edge, y0 = bottom edge)."""
    h = sh.h
    rows = [("Project", "RC course project - reinforcement drawing"),
            ("Element", el.title),
            ("Student", f"{inp.student}  {inp.faculty_no}  {inp.date}".strip()),
            ("Materials", f"C{int(inp.fck)}/{int(inp.fck + 5)}, B{int(inp.fyk)}, c_nom = 25 mm"),
            ("Scale", f"1:{el.scale}  (drawing unit = 1 cm)"),
            ("Steel", f"{fmt(el.mass)} kg")]
    w1 = 11 * h
    w2 = max(max(0.72 * (1.1 if k == 1 else 0.9) * h * len(v) for k, (_, v) in enumerate(rows)) + 3 * h, 45 * h)
    rh = 2.2 * h
    x0 = x1 - w1 - w2
    y = y0 + rh * len(rows)
    sh.rect(x0, y0, x1, y, "D-TEXT")
    sh.line((x0 + w1, y0), (x0 + w1, y), "D-TEXT")
    for k, (a, v) in enumerate(rows):
        yy = y - k * rh
        if k:
            sh.line((x0, yy), (x1, yy), "D-TEXT")
        sh.text(a, (x0 + 0.8 * h, yy - rh / 2), 0.9 * h, align=ML)
        sh.text(v, (x0 + w1 + 0.8 * h, yy - rh / 2), (1.1 if k == 1 else 0.9) * h, align=ML)
    return w1 + w2, rh * len(rows)


def export(P, out_dir, name, png=False, png_dir=None):
    """Write every element drawing into its own DXF file (with border and title block).
    Returns a list of (element, dxf path, png path or None)."""
    import ezdxf
    if png_dir:
        os.makedirs(png_dir, exist_ok=True)
    out = []
    for el, fn in build(P):
        doc = ezdxf.new("R2010")
        doc.units = ezdxf.units.CM
        setup(doc)
        msp = doc.modelspace()
        sh = Sheet(msp, 0, 0, el.scale)
        fn(sh)
        bx0, by0, bx1, by1 = sh.box
        sh.text(f"{el.title.upper()}   M 1:{el.scale}", ((bx0 + bx1) / 2, by1 + 3 * sh.h), 2.0 * sh.h)
        m = 6 * sh.h
        tw, th = title_block(Sheet(None, 0, 0, el.scale), el, P.inp, 0, 0)
        X0, Y0, X1, Y1 = sh.box[0] - m, sh.box[1] - m - th - m, sh.box[2] + m, sh.box[3] + m
        X1 = max(X1, X0 + tw + 2 * m)
        title_block(sh, el, P.inp, X1 - m / 2, Y0 + m / 2)
        sh.rect(X0, Y0, X1, Y1, "D-TEXT")
        sh.rect(X0 - m / 2, Y0 - m / 2, X1 + m / 2, Y1 + m / 2, "D-TEXT")
        doc.header["$EXTMIN"] = (X0 - m, Y0 - m, 0)
        doc.header["$EXTMAX"] = (X1 + m, Y1 + m, 0)
        f = os.path.join(out_dir, f"Reinforcement_{FILE_NAMES.get(el.key, el.key)}_{name}.dxf")
        doc.saveas(f)
        p = None
        if png or png_dir:
            from .dxf_formwork import render_png
            p = os.path.join(png_dir or out_dir, os.path.basename(f)[:-4] + ".png")
            W = X1 - X0 + 2 * m
            render_png(doc, p, box=(X0 - m, Y0 - m, X1 + m, Y1 + m), width_px=int(min(3600, max(1800, W * 4))))
        out.append((el, f, p))
    return out
