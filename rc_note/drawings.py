# -*- coding: utf-8 -*-
"""
drawings.py - DXF drawings from the results of the calculations
==============================================================

  Formwork_<name>.dxf             formwork plan of the slab above the first
                                  floor (template redrawn for the input data,
                                  slab thicknesses and element sizes from the
                                  calculations)
  Slab_reinforcement_<name>.dxf   bottom and top reinforcement of the slabs
                                  with bar schedules (bars from the
                                  calculations)

Needs ezdxf (pip install ezdxf).
"""
from __future__ import annotations

import os

from .engine import fmt
from .project import HF_TIP

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(os.path.dirname(HERE), "templates", "formwork_template.dxf")


def size_rows(P):
    """Rows (element, size) for the table on the formwork plan."""
    inp, G, res = P.inp, P.G, P.res
    rows = []
    if "II" in res:
        rows.append((f"Slabs {G.no_hall} (exhibition hall)", f"h_f = {fmt(res['II']['hf'])} cm"))
    if "III" in res:
        rows.append((f"Slabs {G.no_room[0]}-{G.no_room[-1]} (meeting room)", f"h_f = {fmt(res['III']['hf'])} cm"))
    if "I" in res:
        rows.append((f"Slab {G.no_corr} (corridor)", f"h_f = {fmt(res['I']['hf'])} cm"))
    if "IV" in res:
        o = G.no_office
        rows.append((f"Slabs {G.no_10}, {G.no_lobby}, {o[0]}-{o[-1]} (two-way)", f"h_f = {fmt(res['IV']['hf'])} cm"))
        rows.append((f"Balconies {G.no_balcony[0]}, {G.no_balcony[1]}",
                     f"h_f = {fmt(res['IV']['hf'])} -> {fmt(HF_TIP)} cm, l = {fmt(inp.d)} cm"))
    if "VII" in res:
        rows.append((f"Canopy slab {G.no_stairs[0]}", f"h_f = {fmt(inp.hf_canopy)} cm, l = {fmt(1.25 * inp.d)} cm"))
    if "V" in res:
        v = res["V"]
        rows.append((f"Stairs {G.no_stairs[1]}, {G.no_stairs[2]}",
                     f"h = {fmt(v['h'])} cm, {v['n']} x {fmt(v['hst'])}/{fmt(v['bst'])} cm"))
    if "VIII" in res:
        rows.append(("Beams B5-B9 (hall)", f"{fmt(inp.B5_b)}/{fmt(res['VIII']['h'])} cm"))
    if "VI" in res:
        rows.append(("Beam B21", f"{fmt(inp.B21_b)}/{fmt(res['VI']['h'])} cm"))
    if "VII" in res and "h" in res["VII"]:
        rows.append(("Beam on axis E, 3-4 (torsion)", f"{fmt(inp.BT_b)}/{fmt(res['VII']['h'])} cm"))
    if "X" in res:
        rows.append(("Frame beam B15 (axis 2)", f"{fmt(inp.B15_b)}/{fmt(res['X']['hB15'])} cm"))
    rows.append(("Columns C1, C12", f"{fmt(inp.C1_b)}/{fmt(inp.C1_h)} cm"))
    rows.append(("Column C7", f"{fmt(inp.C7_b)}/{fmt(inp.C7_h)} cm"))
    rows.append(("Column C10", f"{fmt(inp.C10_b)}/{fmt(inp.C10_h)} cm"))
    if "XI" in res and "L" in res["XI"]:
        f = res["XI"]
        rows.append(("Pad footing under C7", f"{fmt(f['L'])} x {fmt(f['B'])} x {fmt(f['H'])} cm"))
    return rows


def make(P, out_dir, name, png=False, template=TEMPLATE):
    """Write the drawings. Returns dict(files, plan, layout, report)."""
    from . import dxf_formwork, dxf_rebar, rebar
    inp = P.inp
    lay = dxf_formwork.redraw(template, inp.a, inp.b, inp.c, inp.d, inp.hb / 100.0,
                              hf_by_slab=rebar.slab_thickness(P), size_rows=size_rows(P))
    f_form = os.path.join(out_dir, f"Formwork_{name}.dxf")
    lay.doc.saveas(f_form)
    plan = rebar.build(P, lay)
    f_reb = os.path.join(out_dir, f"Slab_reinforcement_{name}.dxf")
    title = f"{inp.student}  {inp.faculty_no}".strip()
    doc, pitch = dxf_rebar.write(f_form, f_reb, lay, plan, inp, title_extra=title, P=P)
    files = [f_form, f_reb]
    from . import details
    elems = details.export(P, out_dir, name, png=png, png_dir=None if png else os.path.join(P.workdir, "elements"))
    files += [f for _, f, _ in elems]
    if png:
        X, Y = lay.X, lay.Y
        box = (X["1"] - 350, Y["A"] - inp.d - 350, X["7"] + 1300, Y["E"] + 650)
        p1 = f_form[:-4] + ".png"
        dxf_formwork.render_png(lay.doc, p1, box=box)
        p2 = f_reb[:-4] + "_bottom.png"
        p3 = f_reb[:-4] + "_top.png"
        dxf_formwork.render_png(doc, p2, box=box)
        dxf_formwork.render_png(doc, p3, box=(box[0] + pitch, box[1], box[2] + pitch, box[3]))
        files += [p1, p2, p3]
        if plan.details:
            from ezdxf import bbox as ezbbox
            e = ezbbox.extents(doc.modelspace(), fast=True)
            p4 = f_reb[:-4] + "_details.png"
            dxf_formwork.render_png(doc, p4, box=(box[0], e.extmin.y - 50, box[0] + 2 * pitch,
                                                  Y["A"] - inp.d - 500), width_px=4000)
            files.append(p4)
        files += [p for _, _, p in elems if p]
    return dict(files=files, plan=plan, layout=lay, report=lay.report + lay.warnings, elements=elems)


def note_section(nt, P, out):
    """Section of the explanatory note: drawings and bar schedule."""
    from .rebar import Schedule, MASS
    plan = out["plan"]
    nt.h1("XII. Drawings and bar schedules")
    nt.p("The following drawings were produced from the results of the calculations (DXF, drawing unit = 1 cm; "
         "formwork and slabs 1:50, elements 1:25, stairs 1:10):")
    for f in out["files"]:
        if f.endswith(".dxf"):
            nt.bullet(os.path.basename(f))
    nt.p("The slabs of the hall are reinforced with the welded wire meshes adopted in section II (part 8); "
         "the bar diameters and spacings of the other slabs are the ones adopted in sections I, III, IV and VII. "
         "Distribution bars, top bars at the end supports and along the edges parallel to the span and the "
         "assembly bars follow the detailing rules given there (EC2 9.3).")
    for s in plan.notes:
        nt.p(s, italic=True)
    sch = plan.schedule
    rows = []
    for b in sch.rows():
        rows.append((f"N{b.pos}", b.mark, f"Φ{b.phi}", "+".join(fmt(s) for s in b.segs),
                     fmt(b.s) if b.s else "-", str(b.n_total), fmt(b.L * b.n_total / 100.0),
                     "; ".join(b.where)))
    nt.table(["Pos.", "Mark", "Φ", "Shape [cm]", "s [cm]", "n", "Total [m]", "Location"], rows,
             caption="Bar schedule of the slabs (BR/DR bottom, TR/AR top)")
    if plan.details:
        nt.h2("Reinforcement drawings of the elements")
        nt.p("Every element designed in the note has its own reinforcement drawing (a separate DXF file with "
             "elevation, cross-sections, bars drawn separately, bar schedule and title block); the same drawings "
             "are also placed under the slab plans in the slab reinforcement file: " +
             "; ".join(el.title for el in plan.details) + ".")
        for el, f, p in out.get("elements", []):
            if p and os.path.exists(p):
                from PIL import Image
                with Image.open(p) as im:
                    ar = im.height / im.width
                nt.fig(p, f"{el.title} - reinforcement drawing ({os.path.basename(f)})", min(16.0, 21.0 / ar))
        rows = []
        for el in plan.details:
            for b in el.bars:
                rows.append((el.title.split(" - ")[0], str(b.pos), f"Φ{b.phi}", "+".join(fmt(x) for x in b.segs),
                             str(b.n), fmt(b.L * b.n / 100), fmt(b.L * b.n / 100 * MASS.get(b.phi, 0))))
        nt.table(["Element", "Pos.", "Φ", "Shape [cm]", "n", "Total [m]", "Mass [kg]"], rows,
                 caption="Bar schedule of the elements")
        nt.table(["Element", "Mass [kg]"], [(el.title.split(" - ")[0], fmt(el.mass)) for el in plan.details] +
                 [("Total", fmt(sum(el.mass for el in plan.details)))], caption="Mass of the reinforcement of the elements")
        nt.h2("Slabs")
    meshes = sch.mesh_rows()
    if meshes:
        nt.table(["Pos.", "Mesh", "L × B [m]", "n", "Area [m²]", "kg/pc", "Total [kg]", "Location"],
                 [(f"M{m.pos}", m.name, f"{m.L / 100:.2f} × {m.B / 100:.2f}", str(m.n_total),
                   fmt(m.L * m.B * m.n_total / 1e4), fmt(m.mass), fmt(m.mass * m.n_total), "; ".join(m.where))
                  for m in meshes], caption="Mesh schedule of the slabs (welded wire meshes, R-type)")
    tot, mass = Schedule.totals(sch.rows())
    mm = sum(m.mass * m.n_total for m in meshes)
    nt.table(["Steel", "Length [m]", "kg/m", "Mass [kg]"],
             [(f"Φ{d}", fmt(v[0]), fmt(MASS[d]), fmt(v[1])) for d, v in tot.items()] +
             ([("Meshes", "", "", fmt(mm))] if meshes else []) +
             [("Total", "", "", fmt(mass + mm))], caption="Mass of the reinforcement of the slabs")
