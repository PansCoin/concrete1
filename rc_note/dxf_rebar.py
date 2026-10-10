# -*- coding: utf-8 -*-
"""
dxf_rebar.py - reinforcement plans of the slab (ezdxf)
=====================================================

Draws two plans side by side in one DXF file:

  * bottom reinforcement of the slab above the first floor
  * top reinforcement of the slab above the first floor

Background: the outline of the beams, walls and columns of the formwork plan
(axes, beam / column / wall names and slab numbers; no section marks,
dimensions, levels or stairs), light grey, one block under each plan.

Hall slabs (1..n): welded wire meshes - every mesh piece is drawn as a
rectangle with a diagonal and the label "M<pos> R188 - L/B m".
Other slabs: bars - one representative bar per group with its shape and the
lengths of its parts and the label "N<pos> <mark> <n>Ø<d>x<L>/<s>".
The width over which a group of bars (or a zone of meshes) is spread is given
with dimension lines (DIMENSION entities); collinear dimensions are chained
so that they touch each other (the widths of the supports in between are
dimensioned too). Next to each plan: bar schedule, mesh schedule, mass.

Units of the drawing: cm (1 drawing unit = 1 cm), scale 1:50.
"""
from __future__ import annotations

import math
import re

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.enums import TextEntityAlignment

from .engine import fmt
from .rebar import AR_SPACING, MASS, Schedule

BG_BLOCK = "FORMWORK_BACKGROUND"
DIMSTYLE = "RC_DIM"
H_LAB = 9.0          # height of the bar labels
H_LEN = 7.5          # height of the lengths of the bar parts
H_MESH = 8.0         # height of the mesh labels
H_TAB = 10.0         # height of the texts in the tables
CHAIN_GAP = 80.0     # cm, gaps up to this width between collinear dimensions are dimensioned too
LAYERS = {
    "R-BARS-BOTTOM": dict(color=1, lineweight=50),
    "R-BARS-TOP": dict(color=5, lineweight=50),
    "R-MESH-BOTTOM": dict(color=30, lineweight=35),
    "R-MESH-TOP": dict(color=140, lineweight=35),
    "R-TEXT": dict(color=7, lineweight=18),
    "R-DIM": dict(color=3, lineweight=18),
    "R-TABLE": dict(color=7, lineweight=18),
    "R-TITLE": dict(color=7, lineweight=35),
}
MC = TextEntityAlignment.MIDDLE_CENTER
ML = TextEntityAlignment.MIDDLE_LEFT

# background: what is kept of the formwork plan
BG_LAYERS = {"035", "!Column", "!Hatch", "Osi"}
BG_TYPES = {"LINE", "LWPOLYLINE", "HATCH", "CIRCLE", "ARC"}
LABEL_RE = re.compile(r"(B\d+|C\d+|SW\d+.*|[A-E]|5')")


# ============================================================================
# background
# ============================================================================
def _text(e):
    return (e.dxf.text if e.dxftype() == "TEXT" else e.plain_text()).strip()


def _height(e):
    return e.dxf.get("height", 0.0) if e.dxftype() == "TEXT" else e.dxf.get("char_height", 0.0)


def merge_beam_lines(msp, holes, gap_max=70.0):
    """Close the gaps in the beam lines left by the section marks: collinear
    segments on layer 035 are joined when the gap is short and does not lie
    in a column or a wall."""
    groups = {}
    for ln in list(msp.query("LINE")):
        if ln.dxf.layer != "035":
            continue
        s, e = ln.dxf.start, ln.dxf.end
        if abs(s.y - e.y) < 0.05:
            groups.setdefault(("h", round(s.y, 1)), []).append((min(s.x, e.x), max(s.x, e.x), ln))
        elif abs(s.x - e.x) < 0.05:
            groups.setdefault(("v", round(s.x, 1)), []).append((min(s.y, e.y), max(s.y, e.y), ln))

    def in_hole(o, c, m):
        x, y = (m, c) if o == "h" else (c, m)
        return any(h[0] - 1 <= x <= h[2] + 1 and h[1] - 1 <= y <= h[3] + 1 for h in holes)

    for (o, c), segs in groups.items():
        segs.sort(key=lambda t: t[0])
        runs = [[segs[0][0], segs[0][1], [segs[0][2]]]]
        for a, b, ln in segs[1:]:
            r = runs[-1]
            g = a - r[1]
            if g <= gap_max and (g <= 0.05 or not in_hole(o, c, (a + r[1]) / 2)):
                r[1] = max(r[1], b)
                r[2].append(ln)
            else:
                runs.append([a, b, [ln]])
        for a, b, lns in runs:
            if len(lns) < 2:
                continue
            keep = lns[0]
            for ln in lns[1:]:
                msp.delete_entity(ln)
            if o == "h":
                keep.dxf.start, keep.dxf.end = (a, c), (b, c)
            else:
                keep.dxf.start, keep.dxf.end = (c, a), (c, b)


def prepare_background(doc, lay):
    """Grey outline of the structure (beams, walls, columns, axes, names,
    slab numbers) in a block."""
    msp = doc.modelspace()
    circles = [e for e in msp.query("CIRCLE") if 18.0 <= e.dxf.radius <= 21.0]   # slab numbers
    for e in list(msp):
        t = e.dxftype()
        keep = e.dxf.layer in BG_LAYERS and t in BG_TYPES
        if t in ("TEXT", "MTEXT"):
            s = _text(e)
            if s.isdigit():
                p = e.dxf.insert
                keep = _height(e) >= 25 or any(math.dist((p.x, p.y), (c.dxf.center.x, c.dxf.center.y)) < 25
                                               for c in circles)
            else:
                keep = bool(LABEL_RE.fullmatch(s)) and e.dxf.insert.x < lay.X["7"] + 300
        elif t == "CIRCLE" and 18.0 <= e.dxf.radius <= 21.0:
            keep = True
        if not keep:
            msp.delete_entity(e)
    holes = []
    for h in msp.query("HATCH"):
        bb = ezbbox.extents([h])
        if bb.has_data:
            holes.append((bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y))
    merge_beam_lines(msp, holes)
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
    if DIMSTYLE not in doc.dimstyles:
        doc.dimstyles.new(DIMSTYLE, dxfattribs={
            "dimtxt": 9.0, "dimasz": 4.5, "dimblk": "OBLIQUE", "dimexo": 0.0, "dimexe": 3.0,
            "dimgap": 1.2, "dimdec": 1, "dimzin": 8, "dimdsep": ord("."), "dimtad": 1,
            "dimtih": 0, "dimtoh": 0, "dimclrd": 3, "dimclre": 3, "dimclrt": 3, "dimtxsty": "RC_TEXT",
            "dimlunit": 2, "dimscale": 1.0, "dimtmove": 2,
        })


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
    """One representative bar with its lengths, label and assembly bars."""
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
    # the bar crosses its dimension line: small circle
    if rep.rng is not None:
        r0 = (rep.rng[0][0] + dx, rep.rng[0][1])
        r1 = (rep.rng[1][0] + dx, rep.rng[1][1])
        ip = _intersection(p0, p1, r0, r1)
        if ip is not None:
            msp.add_circle(ip, 3.0, dxfattribs={"layer": "R-DIM"})


def draw_mesh_zone(msp, z, dx=0.0):
    """Mesh pieces: rectangle, diagonal and label along the diagonal."""
    layer = "R-MESH-BOTTOM" if z.face == "bottom" else "R-MESH-TOP"
    for i, (mt, (x0, y0, x1, y1)) in enumerate(z.pieces):
        x0, x1 = x0 + dx, x1 + dx
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True,
                           dxfattribs={"layer": layer})
        if i % 2 == 0:
            a, b = (x0, y0), (x1, y1)
        else:
            a, b = (x0, y1), (x1, y0)
        msp.add_line(a, b, dxfattribs={"layer": layer})
        narrow = min(x1 - x0, y1 - y0) < 100
        if narrow and i > 0:                 # narrow strips: one label per zone
            continue
        ang = math.degrees(math.atan2(b[1] - a[1], b[0] - a[0]))
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        t = 0.5 if len(z.pieces) == 1 else 0.40 + 0.2 * (i % 2)
        c = (a[0] + ux * L * t + nx * H_MESH * 0.8, a[1] + uy * L * t + ny * H_MESH * 0.8)
        text(msp, mt.label(), c, H_MESH, ang, layer="R-TEXT")


def dimension_chains(msp, segments, dx=0.0):
    """segments: [((x0, y0), (x1, y1))] horizontal or vertical. Collinear
    segments are put on one line and chained: short gaps between them (the
    supports) are dimensioned as well, so that the dimensions touch."""
    lines = {}
    for (a, b) in segments:
        if abs(a[1] - b[1]) < 0.01:
            o, c, s, e = "h", a[1], min(a[0], b[0]), max(a[0], b[0])
        elif abs(a[0] - b[0]) < 0.01:
            o, c, s, e = "v", a[0], min(a[1], b[1]), max(a[1], b[1])
        else:
            continue
        if e - s < 1.0:
            continue
        key = None
        for (ko, kc) in lines:
            if ko == o and abs(kc - c) < 1.0:
                key = (ko, kc)
                break
        lines.setdefault(key or (o, c), []).append((s, e))
    n = 0
    for (o, c), segs in lines.items():
        segs = sorted(set((round(s, 1), round(e, 1)) for s, e in segs))
        chain = []
        for s, e in segs:
            if chain:
                ps, pe = chain[-1]
                if abs(s - ps) < 0.5 and abs(e - pe) < 0.5:
                    continue
                if 0.5 < s - pe <= CHAIN_GAP:
                    chain.append((pe, s))                   # support between two zones
                elif s < pe - 0.5:                          # overlap: start after the previous one
                    s = pe
                    if e - s < 1.0:
                        continue
            chain.append((s, e))
        for s, e in chain:
            if o == "h":
                d = msp.add_linear_dim(base=(s + dx, c), p1=(s + dx, c), p2=(e + dx, c), angle=0,
                                       dimstyle=DIMSTYLE, dxfattribs={"layer": "R-DIM"})
            else:
                d = msp.add_linear_dim(base=(c + dx, s), p1=(c + dx, s), p2=(c + dx, e), angle=90,
                                       dimstyle=DIMSTYLE, dxfattribs={"layer": "R-DIM"})
            d.render()
            n += 1
    return n


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
    for r in [[c[0] for c in cols]] + rows:
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


def _short(s, n=48):
    return s if len(s) <= n else s[:n - 2] + "..."


def mesh_mass(meshes):
    return sum(m.mass * m.n_total for m in meshes)


def schedule_tables(msp, x0, y0, bars, meshes, title, slab_total=None):
    y = y0
    if bars:
        cols = [("Pos.", 45, "c"), ("Mark", 45, "c"), ("Ø [mm]", 55, "c"), ("Shape [cm]", 125, "c"),
                ("L [cm]", 60, "c"), ("n [pcs]", 60, "c"), ("Total [m]", 75, "c"), ("Location", 330, "l")]
        rows = [[f"N{b.pos}", b.mark, str(b.phi), shape_text(b), fmt(b.L), str(b.n_total),
                 fmt(b.L * b.n_total / 100.0), _short("; ".join(b.where))] for b in bars]
        y = draw_table(msp, x0, y, cols, rows, f"{title} - bars") - 70
    if meshes:
        cols = [("Pos.", 45, "c"), ("Mesh", 60, "c"), ("L [m]", 60, "c"), ("B [m]", 60, "c"),
                ("n [pcs]", 60, "c"), ("Area [m²]", 75, "c"), ("kg/pc", 60, "c"), ("Total [kg]", 75, "c"),
                ("Location", 300, "l")]
        rows = [[f"M{m.pos}", m.name, f"{m.L / 100:.2f}", f"{m.B / 100:.2f}", str(m.n_total),
                 fmt(m.L * m.B * m.n_total / 1e4), fmt(m.mass), fmt(m.mass * m.n_total),
                 _short("; ".join(m.where), 44)] for m in meshes]
        y = draw_table(msp, x0, y, cols, rows, f"{title} - welded wire meshes") - 70
    tot, mass = Schedule.totals(bars)
    mm = mesh_mass(meshes)
    cols2 = [("Steel", 90, "c"), ("Length [m]", 100, "c"), ("kg/m", 80, "c"), ("Mass [kg]", 100, "c")]
    rows2 = [[f"Ø{d}", fmt(v[0]), fmt(MASS[d]), fmt(v[1])] for d, v in tot.items()]
    if meshes:
        rows2.append(["Meshes", "", "", fmt(mm)])
    rows2.append(["Total", "", "", fmt(mass + mm)])
    if slab_total is not None:
        rows2.append(["Slab", "", "", fmt(slab_total)])
    y = draw_table(msp, x0, y, cols2, rows2, "Steel B500 - mass")
    return y, mass + mm


# ============================================================================
# the drawing
# ============================================================================
def write(formwork_path, out_path, lay, plan, inp, title_extra="", P=None):
    """Writes the reinforcement plans. formwork_path = DXF of the formwork
    plan written for the same layout (used as background)."""
    doc = ezdxf.readfile(formwork_path)
    X, Y = lay.X, lay.Y
    prepare_background(doc, lay)
    msp = doc.modelspace()
    ext = ezbbox.extents(doc.blocks.get(BG_BLOCK), fast=True)
    left = ext.extmin.x
    tab_x = X["7"] + 380
    pitch = math.ceil(((tab_x + 900) - left + 400) / 500.0) * 500.0
    sch = plan.schedule
    bars = {f: sch.rows(f) for f in ("bottom", "top")}
    meshes = {f: sch.mesh_rows(f) for f in ("bottom", "top")}
    total = sum(sch.totals(bars[f])[1] + mesh_mass(meshes[f]) for f in ("bottom", "top"))
    title_y = ext.extmax.y + 60
    lvl = f"+{lay.level:.2f}"
    specs = [(0.0, "bottom", plan.bottom, plan.mesh_bottom, None),
             (pitch, "top", plan.top, plan.mesh_top, total)]
    for dx, face, reps, zones, slab_total in specs:
        msp.add_blockref(BG_BLOCK, (dx, 0))
        for z in zones:
            draw_mesh_zone(msp, z, dx)
        for rep in reps:
            draw_rep(msp, rep, dx)
        dimension_chains(msp, [r.rng for r in reps if r.rng] + [z.rng for z in zones if z.rng]
                         + plan.dims.get(face, []), dx)
        if face == "bottom":
            for (x, y, s, h, rot) in plan.texts:
                text(msp, s, (x + dx, y), h, rot)
        title = f"{face.upper()} REINFORCEMENT OF THE SLAB ABOVE THE FIRST FLOOR (LEVEL {lvl})   M 1:50"
        text(msp, title, ((X["1"] + X["7"]) / 2 + dx, title_y), 22.0, layer="R-TITLE")
        if title_extra:
            text(msp, title_extra, ((X["1"] + X["7"]) / 2 + dx, title_y - 34), 13.0, layer="R-TITLE")
        schedule_tables(msp, tab_x + dx, Y["E"] + 250, bars[face], meshes[face],
                        f"Schedule - {face}", slab_total)
        notes = [
            f"Concrete C{int(inp.fck)}/{int(inp.fck + 5)}, reinforcing steel B{int(inp.fyk)}, "
            f"concrete cover c_nom = 25 mm.",
            "Bars: N<position> <mark> <number>Ø<diameter> x <length [cm]> / <spacing [cm]>; "
            "BR bottom, DR distribution, TR top, AR assembly bars under the top bars (dots).",
            "Meshes: M<position> <type> - <length along the main bars> / <width> [m]; "
            "the diagonal marks one mesh piece.",
            "The dimension lines give the width over which the bars / meshes are placed.",
            "Bottom bars run into the supports up to the far face minus the cover; "
            "top bars are bent down to the bottom cover. Laps of bars: 50Ø.",
        ] + plan.notes
        yy = ext.extmin.y - 60
        for i, s in enumerate(notes):
            text(msp, f"{i + 1}. {s}", (X["1"] + dx, yy - i * 20), 11.0, layer="R-TEXT", align=ML)
    # detail drawings of the elements under the slab plans
    details_ = []
    if P is not None:
        from . import details
        details.setup(doc)
        y_top = ext.extmin.y - 60 - 20 * (len(plan.notes) + 6) - 250
        details_, _ = details.place(msp, P, X["1"] - 300, y_top, 2 * pitch)
    plan.details = details_
    try:
        e = ezbbox.extents(msp, fast=True)
        doc.header["$EXTMIN"] = e.extmin
        doc.header["$EXTMAX"] = e.extmax
    except Exception:
        pass
    doc.saveas(out_path)
    return doc, pitch
