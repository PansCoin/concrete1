# -*- coding: utf-8 -*-
"""
sheets.py - drawing sheets: paper, frame and title block, PDF output
====================================================================

Every drawing gets a sheet in model space (1 unit = 1 cm): the smallest ISO A
paper (A4 ... A0) on which the drawing fits at its scale, the frame (20 mm
binding margin on the left, 10 mm on the other sides) and the title block of
the department in the bottom right corner:

    University of Architecture, Civil Engineering and Geodesy
    Department of Reinforced Concrete Structures
    Project  | Office building
    Drawing: | <name of the drawing>          | S 1:50
    Student  | <name>                         | <faculty no>
    Adviser  | <adviser>                      | <date>

The sheets are printed to PDF at true scale (sheet_pdf_pages).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ezdxf.enums import TextEntityAlignment

UNIVERSITY = "University of Architecture, Civil Engineering and Geodesy"
DEPARTMENT = "Department of Reinforced Concrete Structures"
PAPERS = [("A4", 297.0, 210.0), ("A3", 420.0, 297.0), ("A2", 594.0, 420.0),
          ("A1", 841.0, 594.0), ("A0", 1189.0, 841.0)]
M_LEFT, M_OTHER = 20.0, 10.0            # mm, frame margins
GAP = 8.0                               # mm, frame -> drawing
TB_COLS = (40.0, 110.0, 30.0)           # mm, columns of the title block
TB_ROW = 9.0                            # mm, row height
TB_W, TB_H = sum(TB_COLS), 6 * TB_ROW
LAYER = "SHEET"
MC = TextEntityAlignment.MIDDLE_CENTER


@dataclass
class Sheet:
    paper: str
    W: float              # mm
    H: float
    scale: int
    rect: tuple           # paper in drawing units (x0, y0, x1, y1)
    title: str
    content: tuple = None  # drawing extents (x0, y0, x1, y1)


def choose_paper(cw, ch, min_paper=None):
    """smallest paper (mm) for a drawing of cw x ch mm with the title block below or beside it"""
    names = [p[0] for p in PAPERS]
    start = names.index(min_paper) if min_paper in names else 0
    for name, a, b in PAPERS[start:]:
        for W, H in ((a, b), (b, a)):
            iw, ih = W - M_LEFT - M_OTHER, H - 2 * M_OTHER
            below = cw + 2 * GAP <= iw and ch + TB_H + 3 * GAP <= ih
            beside = cw + TB_W + 3 * GAP <= iw and ch + 2 * GAP <= ih
            if below or beside:
                return name, W, H, ("below" if below else "beside")
    name, a, b = PAPERS[-1]
    return name, a, b, "below"


def _styles(doc):
    for name, font in (("TB", "arial.ttf"), ("TB_B", "arialbd.ttf"), ("TB_I", "ariali.ttf")):
        if name not in doc.styles:
            doc.styles.add(name, font=font)
    if LAYER not in doc.layers:
        doc.layers.add(LAYER, color=7, lineweight=35)


# lengths on the paper [mm] (ISO 128): dashed line = dash 3, gap 1.2;
# dash-dot line (axes) = long dash 12, gap 2, dot 0.5, gap 2
LT_PAPER = {"dashed": (3.0, -1.2), "axis": (12.0, -2.0, 0.5, -2.0)}


def set_linetypes(doc, scale):
    """Every dashed (2 elements) and dash-dot (more elements) linetype of the drawing gets
    the lengths of LT_PAPER on the paper at the scale 1:scale (drawing unit = 1 cm);
    LTSCALE = 1 and no entity has its own linetype scale, so the lines print alike in
    every CAD program and in the PDF."""
    k = scale / 10.0                                  # drawing units per mm of paper
    for name, kind in (("RC_DASHED", "dashed"), ("RC_AXIS", "axis")):
        if name not in doc.linetypes:
            doc.linetypes.add(name, pattern=[1.0, 0.5, -0.5] if kind == "dashed" else [1.0, 0.5, -0.2, 0.0, -0.3],
                              description="Dashed __ __" if kind == "dashed" else "Axis ___ . ___")
    for lt in doc.linetypes:
        try:
            elems = [t.value for t in lt.pattern_tags.tags if t.code == 49]
        except AttributeError:
            continue
        if len(elems) < 2:
            continue
        pat = [v * k for v in LT_PAPER["dashed" if len(elems) == 2 else "axis"]]
        lt.setup_pattern([sum(abs(v) for v in pat)] + pat)
    doc.header["$LTSCALE"] = 1.0
    doc.header["$CELTSCALE"] = 1.0
    for layout in [doc.modelspace()] + list(doc.blocks):
        for e in layout:
            if e.dxf.hasattr("ltscale") and abs(e.dxf.ltscale - 1.0) > 1e-9:
                e.dxf.ltscale = 1.0


def add_sheet(doc, msp, box, scale, inp, title, min_paper=None):
    """Frame and title block around the drawing extents box (drawing units). Returns a Sheet."""
    _styles(doc)
    set_linetypes(doc, scale)
    k = scale / 10.0                                  # drawing units per mm of paper
    x0, y0, x1, y1 = box
    cw, ch = (x1 - x0) / k, (y1 - y0) / k
    name, W, H, where = choose_paper(cw, ch, min_paper)
    iw, ih = W - M_LEFT - M_OTHER, H - 2 * M_OTHER
    # paper origin so that the drawing is centred in the free part of the frame
    if where == "below":
        cx_mm = M_LEFT + iw / 2
        cy_mm = M_OTHER + TB_H + GAP + (ih - TB_H - GAP) / 2
    else:
        cx_mm = M_LEFT + (iw - TB_W - GAP) / 2
        cy_mm = M_OTHER + ih / 2
    px0 = (x0 + x1) / 2 - cx_mm * k
    py0 = (y0 + y1) / 2 - cy_mm * k
    P = lambda u, v: (px0 + u * k, py0 + v * k)       # paper mm -> drawing units
    att = lambda lw: {"layer": LAYER, "lineweight": lw, "color": 7}
    msp.add_lwpolyline([P(0, 0), P(W, 0), P(W, H), P(0, H)], close=True, dxfattribs=att(13))
    msp.add_lwpolyline([P(M_LEFT, M_OTHER), P(W - M_OTHER, M_OTHER), P(W - M_OTHER, H - M_OTHER),
                        P(M_LEFT, H - M_OTHER)], close=True, dxfattribs=att(50))
    # title block
    tx1, ty0 = W - M_OTHER, M_OTHER
    tx0 = tx1 - TB_W
    c1, c2 = tx0 + TB_COLS[0], tx0 + TB_COLS[0] + TB_COLS[1]
    rows = [ty0 + i * TB_ROW for i in range(7)]       # bottom -> top
    msp.add_lwpolyline([P(tx0, ty0), P(tx1, ty0), P(tx1, rows[6]), P(tx0, rows[6])], close=True,
                       dxfattribs=att(50))
    for r in rows[1:6]:
        msp.add_line(P(tx0, r), P(tx1, r), dxfattribs=att(25))
    msp.add_line(P(c1, ty0), P(c1, rows[4]), dxfattribs=att(25))
    msp.add_line(P(c2, ty0), P(c2, rows[3]), dxfattribs=att(25))

    def txt(s, u, v, h, style, w_max):
        h_ = min(h, w_max / max(0.55 * len(s), 1.0))
        t = msp.add_text(s, height=h_ * k, dxfattribs={"layer": LAYER, "style": style, "color": 7})
        t.set_placement(P(u, v), align=MC)
    mid = lambda r: (rows[r] + rows[r + 1]) / 2
    txt(UNIVERSITY, (tx0 + tx1) / 2, mid(5), 4.0, "TB_B", TB_W - 6)
    txt(DEPARTMENT, (tx0 + tx1) / 2, mid(4), 4.5, "TB_B", TB_W - 6)
    txt("Project", (tx0 + c1) / 2, mid(3), 4.0, "TB_B", TB_COLS[0] - 4)
    txt(getattr(inp, "project", "") or "Office building", (c1 + tx1) / 2, mid(3), 3.5, "TB", TB_W - TB_COLS[0] - 6)
    txt("Drawing:", (tx0 + c1) / 2, mid(2), 4.0, "TB_B", TB_COLS[0] - 4)
    txt(title, (c1 + c2) / 2, mid(2), 3.5, "TB_I", TB_COLS[1] - 6)
    txt(f"S 1:{scale}", (c2 + tx1) / 2, mid(2), 3.5, "TB_I", TB_COLS[2] - 4)
    txt("Student", (tx0 + c1) / 2, mid(1), 4.0, "TB_B", TB_COLS[0] - 4)
    txt(inp.student or "", (c1 + c2) / 2, mid(1), 3.5, "TB_I", TB_COLS[1] - 6)
    txt(str(inp.faculty_no or ""), (c2 + tx1) / 2, mid(1), 3.5, "TB_I", TB_COLS[2] - 4)
    txt("Adviser", (tx0 + c1) / 2, mid(0), 4.0, "TB_B", TB_COLS[0] - 4)
    txt(getattr(inp, "adviser", "") or "", (c1 + c2) / 2, mid(0), 3.5, "TB_I", TB_COLS[1] - 6)
    txt(inp.date or "", (c2 + tx1) / 2, mid(0), 3.0, "TB_I", TB_COLS[2] - 4)
    return Sheet(name, W, H, scale, (px0, py0, px0 + W * k, py0 + H * k), title, box)


def content_box(entities, limit=1e5):
    """extents of entities (ignores junk far away from the drawing)"""
    from ezdxf import bbox as ezbbox
    b = [math.inf, math.inf, -math.inf, -math.inf]
    for e in entities:
        try:
            bb = ezbbox.extents([e], fast=True)
        except Exception:
            continue
        if not bb.has_data or max(abs(bb.extmin.x), abs(bb.extmin.y), abs(bb.extmax.x), abs(bb.extmax.y)) > limit:
            continue
        b = [min(b[0], bb.extmin.x), min(b[1], bb.extmin.y), max(b[2], bb.extmax.x), max(b[3], bb.extmax.y)]
    return tuple(b)


# ============================================================================
# PDF
# ============================================================================
FONT_MAP = {"arial.ttf": "LiberationSans-Regular.ttf", "arialbd.ttf": "LiberationSans-Bold.ttf",
            "ariali.ttf": "LiberationSans-Italic.ttf", "arialbi.ttf": "LiberationSans-BoldItalic.ttf"}


def _map_fonts(doc):
    """metric-compatible fonts where Arial is not installed (rendering only)"""
    from ezdxf.fonts import fonts
    if "arial" in fonts.find_font_face("arial.ttf").filename.lower():
        return
    for st in doc.styles:
        f = (st.dxf.get("font", "") or "").lower()
        if f in FONT_MAP:
            st.dxf.font = FONT_MAP[f]


def sheet_pdf_pages(doc, sheets, pdf, mono=True):
    """Render the sheets of a DXF document into an open matplotlib PdfPages
    object, one page per sheet, at true scale."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf import bbox as ezbbox
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy, ColorPolicy, LineweightPolicy
    _map_fonts(doc)
    msp = doc.modelspace()
    centre = {}
    cache = ezbbox.Cache()
    for e in msp:
        try:
            bb = ezbbox.extents([e], fast=True, cache=cache)
        except Exception:
            continue
        if bb.has_data:
            centre[id(e)] = ((bb.extmin.x + bb.extmax.x) / 2, (bb.extmin.y + bb.extmax.y) / 2)
    for sh in sheets:
        x0, y0, x1, y1 = sh.rect
        fig = plt.figure(figsize=(sh.W / 25.4, sh.H / 25.4))
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        cfg = Configuration(background_policy=BackgroundPolicy.WHITE,
                            color_policy=ColorPolicy.BLACK if mono else ColorPolicy.COLOR,
                            lineweight_policy=LineweightPolicy.ABSOLUTE, min_lineweight=0.13)

        def inside(e, r=(x0, y0, x1, y1)):
            c = centre.get(id(e))
            return c is not None and r[0] <= c[0] <= r[2] and r[1] <= c[1] <= r[3]
        Frontend(RenderContext(doc), MatplotlibBackend(ax, adjust_figure=False), config=cfg).draw_layout(
            msp, finalize=False, filter_func=inside)
        ax.set_xlim(x0, x1)
        ax.set_ylim(y0, y1)
        ax.set_aspect("auto")
        fig.set_size_inches(sh.W / 25.4, sh.H / 25.4)
        pdf.savefig(fig)
        plt.close(fig)
