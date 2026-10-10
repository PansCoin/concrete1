# -*- coding: utf-8 -*-
"""
dxf_rebar.py - reinforcement plans of the slab (ezdxf)
=====================================================

Draws two plans side by side in one DXF file:

  * bottom reinforcement of the slab above the first floor
  * top reinforcement of the slab above the first floor

The formwork plan written by dxf_formwork.py is used as a light grey
background (one block inserted under each plan). On top of it every bar
group is drawn the usual way: one representative bar with its shape and the
lengths of its parts, the label "N<pos> <mark> <n>Ø<d>x<L>/<s>" and a range
line with arrows over the width in which the group is spread. Assembly bars
under the top bars are shown as dots on the top bars. Next to each plan:
the bar schedule and the mass of the steel.

Units of the drawing: cm (1 drawing unit = 1 cm), scale 1:50.
"""
from __future__ import annotations

import math

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.enums import TextEntityAlignment

from .engine import fmt
from .rebar import AR_SPACING, MASS

BG_BLOCK = "FORMWORK_BACKGROUND"
H_LAB = 9.0          # height of the bar labels
H_LEN = 7.5          # height of the lengths of the bar parts
H_TAB = 10.0         # height of the texts in the tables
LAYERS = {
    "R-BARS-BOTTOM": dict(color=1, lineweight=50),
    "R-BARS-TOP": dict(color=5, lineweight=50),
    "R-TEXT": dict(color=7, lineweight=18),
    "R-RANGE": dict(color=3, lineweight=18),
    "R-TABLE": dict(color=7, lineweight=18),
    "R-TITLE": dict(color=7, lineweight=35),
}
MC = TextEntityAlignment.MIDDLE_CENTER
ML = TextEntityAlignment.MIDDLE_LEFT


# ============================================================================
# background
# ============================================================================
def prepare_background(doc, lay, box):
    """Grey copy of the formwork plan in a block; dimensions inside the
    building, the title and the size table are removed."""
    msp = doc.modelspace()
    x0, y0, x1, y1 = box
    for e in list(msp):
        t = e.dxftype()
        drop = False
        if t == "DIMENSION":
            p = e.dxf.defpoint
            drop = x0 <= p.x <= x1 and y0 <= p.y <= y1
        elif t in ("TEXT", "MTEXT"):
            s = e.dxf.text if t == "TEXT" else e.plain_text()
            drop = "Formwork at level" in s or e.dxf.insert.x > lay.X["7"] + 300
        elif t == "LINE":
            drop = min(e.dxf.start.x, e.dxf.end.x) > lay.X["7"] + 300
        if drop:
            msp.delete_entity(e)
    for blk in doc.blocks:
        if blk.name.lower().startswith(("*model_space", "*paper_space")):
            continue
        for e in blk:
            if e.dxf.get("color", 256) != 0:
                e.dxf.color = 8
            if e.dxf.hasattr("lineweight") or e.dxftype() != "HATCH":
                e.dxf.lineweight = 13
    bg = doc.blocks.new(BG_BLOCK)
    for e in list(msp):
        e.dxf.color = 8
        e.dxf.lineweight = 13
        msp.move_to_layout(e, bg)
    for name, attr in LAYERS.items():
        if name not in doc.layers:
            doc.layers.add(name, **attr)
    if "RC_TEXT" not in doc.styles:
        doc.styles.add("RC_TEXT", font="arial.ttf")


# ============================================================================
# drawing helpers
# ============================================================================
def _readable(angle):
    a = angle % 360.0
    if 90.0 < a <= 270.0:
        a -= 180.0
    return a


def text(msp, s, p, h, rot=0.0, layer="R-TEXT", align=MC):
    t = msp.add_text(s, height=h, rotation=_readable(rot),
                     dxfattribs={"layer": layer, "style": "RC_TEXT"})
    t.set_placement(p, align=align)
    return t


def arrow(msp, tip, direction, layer="R-RANGE", size=7.0, half=2.6):
    ux, uy = direction
    nx, ny = -uy, ux
    for sgn in (1, -1):
        msp.add_line(tip, (tip[0] - ux * size + sgn * nx * half, tip[1] - uy * size + sgn * ny * half),
                     dxfattribs={"layer": layer})


def dot(msp, c, r, layer):
    h = msp.add_hatch(color=256, dxfattribs={"layer": layer})
    h.set_solid_fill()
    ep = h.paths.add_edge_path()
    ep.add_arc(c, r, 0, 360)


def _intersection(a0, a1, b0, b1):
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = a0, a1, b0, b1
    den = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if abs(den) < 1e-9:
        return None
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / den
    u = -((x1 - x2) * (y1 - y3) - (y1 - y2) * (x1 - x3)) / den
    if -1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6:
        return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))
    return None


def draw_rep(msp, rep, dx=0.0):
    b = rep.bar
    layer = "R-BARS-BOTTOM" if b.face == "bottom" else "R-BARS-TOP"
    p0 = (rep.p0[0] + dx, rep.p0[1])
    p1 = (rep.p1[0] + dx, rep.p1[1])
    L = math.dist(p0, p1)
    if L < 1e-6:
        return
    ux, uy = (p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L
    nx, ny = -uy, ux
    sd = rep.side
    ang = math.degrees(math.atan2(uy, ux))
    leg0, leg1 = rep.legs
    pts = []
    if leg0 > 0:
        pts.append((p0[0] + sd * nx * leg0, p0[1] + sd * ny * leg0))
    pts += [p0, p1]
    if leg1 > 0:
        pts.append((p1[0] + sd * nx * leg1, p1[1] + sd * ny * leg1))
    msp.add_lwpolyline(pts, dxfattribs={"layer": layer})
    # lengths of the parts
    segs = b.segs
    main = segs[len(segs) // 2]
    off = sd * (H_LEN * 0.9)
    text(msp, fmt(main), (p0[0] + ux * L / 2 + nx * off, p0[1] + uy * L / 2 + ny * off), H_LEN, ang)
    if leg0 > 0:
        q = (p0[0] + sd * nx * leg0 / 2 - ux * H_LEN * 0.9, p0[1] + sd * ny * leg0 / 2 - uy * H_LEN * 0.9)
        text(msp, fmt(segs[0]), q, H_LEN, ang + 90)
    if leg1 > 0:
        q = (p1[0] + sd * nx * leg1 / 2 + ux * H_LEN * 0.9, p1[1] + sd * ny * leg1 / 2 + uy * H_LEN * 0.9)
        text(msp, fmt(segs[-1]), q, H_LEN, ang + 90)
    # label on the other side
    t = rep.lab_t
    c = (p0[0] + ux * L * t, p0[1] + uy * L * t)
    o1 = -sd * (H_LAB * 1.25)
    text(msp, b.label(rep.n), (c[0] + nx * o1, c[1] + ny * o1), H_LAB, ang)
    if rep.ar is not None:
        a, k, ntot = rep.ar
        o2 = -sd * (H_LAB * 2.65)
        text(msp, a.label(ntot), (c[0] + nx * o2, c[1] + ny * o2), H_LAB, ang)
        span = (k - 1) * AR_SPACING
        s0 = (L - span) / 2
        for i in range(k):
            d = s0 + i * AR_SPACING
            dot(msp, (p0[0] + ux * d, p0[1] + uy * d), 2.2, layer)
    # range line
    if rep.rng is not None:
        r0 = (rep.rng[0][0] + dx, rep.rng[0][1])
        r1 = (rep.rng[1][0] + dx, rep.rng[1][1])
        Lr = math.dist(r0, r1)
        if Lr > 1e-6:
            vx, vy = (r1[0] - r0[0]) / Lr, (r1[1] - r0[1]) / Lr
            msp.add_line(r0, r1, dxfattribs={"layer": "R-RANGE"})
            arrow(msp, r1, (vx, vy))
            arrow(msp, r0, (-vx, -vy))
            ip = _intersection(p0, p1, r0, r1)
            if ip is not None:
                msp.add_circle(ip, 3.0, dxfattribs={"layer": "R-RANGE"})


# ============================================================================
# tables
# ============================================================================
def draw_table(msp, x0, y0, cols, rows, title=None, h=H_TAB):
    """cols = [(header, width, align)], rows = list of lists of strings.
    Returns the y of the bottom line."""
    rh = 2.0 * h
    W = sum(c[1] for c in cols)
    y = y0
    if title:
        text(msp, title, (x0, y + 0.9 * h), 1.3 * h, layer="R-TABLE", align=TextEntityAlignment.BOTTOM_LEFT)
    lines = [y]
    for r_i, r in enumerate([[c[0] for c in cols]] + rows):
        x = x0
        for (hd, w, al), v in zip(cols, r):
            if al == "l":
                text(msp, str(v), (x + 0.5 * h, y - rh / 2), h, layer="R-TABLE", align=ML)
            else:
                text(msp, str(v), (x + w / 2, y - rh / 2), h, layer="R-TABLE")
            x += w
        y -= rh
        lines.append(y)
    for i, yy in enumerate(lines):
        msp.add_line((x0, yy), (x0 + W, yy), dxfattribs={"layer": "R-TABLE",
                                                       "lineweight": 35 if i in (0, 1, len(lines) - 1) else 13})
    x = x0
    for c in cols + [None]:
        msp.add_line((x, y0), (x, y), dxfattribs={"layer": "R-TABLE"})
        if c:
            x += c[1]
    return y


def shape_text(b):
    return "+".join(fmt(s) for s in b.segs)


def schedule_tables(msp, x0, y0, bars, title, extra_total=None):
    cols = [("Pos.", 45, "c"), ("Mark", 45, "c"), ("Ø [mm]", 55, "c"), ("Shape [cm]", 125, "c"),
            ("L [cm]", 60, "c"), ("n [pcs]", 60, "c"), ("Total [m]", 75, "c"), ("Location", 330, "l")]
    rows = []
    for b in bars:
        where = "; ".join(b.where)
        if len(where) > 48:
            where = where[:46] + "..."
        rows.append([f"N{b.pos}", b.mark, str(b.phi), shape_text(b), fmt(b.L), str(b.n_total),
                     fmt(b.L * b.n_total / 100.0), where])
    y = draw_table(msp, x0, y0, cols, rows, title)
    # steel per diameter
    from .rebar import Schedule
    tot, mass = Schedule.totals(bars)
    cols2 = [("Ø [mm]", 70, "c"), ("Length [m]", 100, "c"), ("kg/m", 80, "c"), ("Mass [kg]", 100, "c")]
    rows2 = [[str(d), fmt(v[0]), fmt(MASS[d]), fmt(v[1])] for d, v in tot.items()]
    rows2.append(["Total", "", "", fmt(mass)])
    if extra_total is not None:
        rows2.append(["Slab", "", "", fmt(extra_total)])
    y = draw_table(msp, x0, y - 70, cols2, rows2, "Steel B500 - mass")
    return y, mass


# ============================================================================
# the drawing
# ============================================================================
def write(formwork_path, out_path, lay, plan, inp, title_extra=""):
    """Writes the reinforcement plans. formwork_path = DXF of the formwork
    plan written for the same layout (used as background)."""
    doc = ezdxf.readfile(formwork_path)
    X, Y = lay.X, lay.Y
    box = (X["1"] - 40, Y["A"] - 40 - inp.d, X["7"] + 40, Y["E"] + 400)
    prepare_background(doc, lay, box)
    msp = doc.modelspace()
    ext = ezbbox.extents(doc.blocks.get(BG_BLOCK), fast=True)
    left = ext.extmin.x
    tab_x = X["7"] + 380
    pitch = math.ceil(((tab_x + 900) - left + 400) / 500.0) * 500.0
    sch = plan.schedule
    bottom_bars, top_bars = sch.rows("bottom"), sch.rows("top")
    _, m_bot = sch.totals(bottom_bars)
    _, m_top = sch.totals(top_bars)
    title_y = ext.extmax.y + 60
    lvl = f"+{lay.level:.2f}"
    specs = [
        (0.0, plan.bottom, bottom_bars,
         f"BOTTOM REINFORCEMENT OF THE SLAB ABOVE THE FIRST FLOOR (LEVEL {lvl})", "Bar schedule - bottom bars",
         None),
        (pitch, plan.top, top_bars,
         f"TOP REINFORCEMENT OF THE SLAB ABOVE THE FIRST FLOOR (LEVEL {lvl})", "Bar schedule - top bars",
         m_bot + m_top),
    ]
    for dx, reps, bars, title, ttab, slab_total in specs:
        msp.add_blockref(BG_BLOCK, (dx, 0))
        for rep in reps:
            draw_rep(msp, rep, dx)
        if dx == 0.0:
            for (x, y, s, h, rot) in plan.texts:
                text(msp, s, (x + dx, y), h, rot)
        text(msp, title + "   M 1:50", ((X["1"] + X["7"]) / 2 + dx, title_y), 22.0, layer="R-TITLE")
        if title_extra:
            text(msp, title_extra, ((X["1"] + X["7"]) / 2 + dx, title_y - 34), 13.0, layer="R-TITLE")
        schedule_tables(msp, tab_x + dx, Y["E"] + 250, bars, ttab, slab_total)
        notes = [
            f"Concrete C{int(inp.fck)}/{int(inp.fck + 5)}, reinforcing steel B{int(inp.fyk)}, "
            f"concrete cover c_nom = 25 mm.",
            "Label: N<position> <mark> <number>Ø<diameter> x <length [cm]> / <spacing [cm]>.",
            "BR - bottom bars, DR - distribution bars, TR - top bars, AR - assembly bars "
            "under the top bars (dots).",
            "Bottom bars run into the supports up to the far face minus the cover; "
            "top bars are bent down to the bottom cover.",
            "Laps of bars: 50Ø. Lengths in cm, measured along the outside of the bar.",
        ] + plan.notes
        yy = ext.extmin.y - 60
        for i, s in enumerate(notes):
            text(msp, f"{i + 1}. {s}", (X["1"] + dx, yy - i * 20), 11.0, layer="R-TEXT", align=ML)
    try:
        e = ezbbox.extents(msp, fast=True)
        doc.header["$EXTMIN"] = e.extmin
        doc.header["$EXTMAX"] = e.extmax
    except Exception:
        pass
    doc.saveas(out_path)
    return doc, pitch
