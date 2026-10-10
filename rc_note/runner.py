# -*- coding: utf-8 -*-
"""runner.py - builds the whole explanatory note."""
from __future__ import annotations

import datetime
import math
import os
import tempfile

from .design import NullNote
from .engine import fmt
from .note import Note
from .plots import Plotter
from .project import Geometry, Inputs


class ProjectRun:
    def __init__(self, inp: Inputs, workdir=None):
        self.inp = inp
        self.G = Geometry(inp)
        self.workdir = workdir or tempfile.mkdtemp(prefix="rcnote_")
        self.plot = Plotter(os.path.join(self.workdir, "figs"))
        self.res = {}
        self.log = []


def auto_size(nt, fn, P, start, given=0, step=1, maxsteps=15, label=""):
    """Run fn(NullNote) with increasing size until all checks pass, then
    write it into the real note."""
    if given:
        fn(nt, P, given)
        return given
    v = start
    for _ in range(maxsteps):
        try:
            ok = fn(NullNote(), P, v)
        except Exception:
            ok = False
        if ok:
            break
        v += step
    P.log.append(f"{label}: {fmt(v)}")
    fn(nt, P, v)
    return v


def title_page(nt, P):
    inp, G = P.inp, P.G
    nt.p("")
    nt.p("UNIVERSITY OF ARCHITECTURE, CIVIL ENGINEERING AND GEODESY", bold=True, align="center", size=12)
    nt.p("Department of Reinforced Concrete Structures", align="center")
    for _ in range(4):
        nt.p("")
    nt.p("COURSE PROJECT IN REINFORCED CONCRETE", bold=True, align="center", size=18)
    nt.p("Explanatory note with static analysis and design calculations", align="center", size=13)
    nt.p("Reinforced concrete structure of the slab above the first floor of an administrative building",
         italic=True, align="center")
    for _ in range(4):
        nt.p("")
    nt.table(["", ""], [("Student", inp.student or "-"), ("Faculty number", inp.faculty_no or "-"),
                        ("Date", inp.date or datetime.date.today().strftime("%d.%m.%Y"))])
    nt.p("")
    nt.table(["Input data", "Value"],
             [("a [cm]", fmt(inp.a)), ("b [cm]", fmt(inp.b)), ("c [cm]", fmt(inp.c)), ("d [cm]", fmt(inp.d)),
              ("h_s [cm]", fmt(inp.hs)), ("h_b [cm]", fmt(inp.hb)), ("q_k1 [kN/m²]", fmt(inp.qk1)),
              ("q_k2 [kN/m²]", fmt(inp.qk2)), ("R_0 [kN/m²]", fmt(inp.R0))],
             caption="Input data (assignment)")
    nt.page_break()
    nt.p("Contents", bold=True, size=14)
    nt.toc()
    nt.h1("General data", new_page=True)
    nt.p("Codes: EN 1990, EN 1991-1-1, EN 1992-1-1 (Eurocode 2) with the recommended values. Units: "
         "kN, m (statics); N, mm (design of sections).")
    nt.p(f"Materials: concrete C{int(inp.fck)}/{int(inp.fck + 5)}, reinforcing steel B{int(inp.fyk)}. "
         "Partial factors: γ_G = 1.35, γ_Q = 1.5, γ_c = 1.5, γ_s = 1.15.")
    X, Y = G.X, G.Y
    nt.table(["Axis", "x [cm]", "", "Axis", "y [cm]"],
             [("1", fmt(X["1"]), "", "A (А)", fmt(Y["A"])), ("2", fmt(X["2"]), "", "B (Б)", fmt(Y["B"])),
              ("3", fmt(X["3"]), "", "C (В)", fmt(Y["C"])), ("4", fmt(X["4"]), "", "D (Г)", fmt(Y["D"])),
              ("5'", fmt(X["5'"]), "", "E (Д)", fmt(Y["E"])), ("5", fmt(X["5"]), "", "", ""),
              ("6", fmt(X["6"]), "", "", ""), ("7", fmt(X["7"]), "", "", "")],
             caption="Structural grid (from the formwork plan)")
    nt.p(f"Exhibition hall: {2 * G.n_half} one-way slabs per bay, secondary beams every "
         f"{fmt(G.s_h)} cm (l/l = {fmt(inp.a / G.s_h)} ≥ 2). Meeting room: {G.n_room} one-way slabs, "
         f"secondary beams every {fmt(G.s_r)} cm (l/l = {fmt(inp.b / G.s_r)} ≥ 2).")
    nt.p(f"Storey heights: first storey h_b = {fmt(inp.hb)} cm, upper storeys h_s = {fmt(inp.hs)} cm "
         f"({inp.n_floors} storeys). Level of the designed slab: +{fmt(inp.hb / 100)} m.")


def build(inp: Inputs, out_path: str, workdir=None, sections=None, verbose=True):
    from . import sec_slabs, sec_members, sec_frame
    P = ProjectRun(inp, workdir)
    nt = Note()
    title_page(nt, P)
    sel = sections or ["I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]
    steps = [
        ("I", lambda: auto_size(nt, sec_slabs.section_I, P, 10, inp.hf_corridor, label="h_f slab I")),
        ("II", lambda: auto_size(nt, sec_slabs.section_II, P, 10, inp.hf_hall, label="h_f slab II")),
        ("III", lambda: auto_size(nt, sec_slabs.section_III, P, 10, inp.hf_room, label="h_f slab III")),
        ("IV", lambda: auto_size(nt, sec_slabs.section_IV, P, 12, inp.hf_office, label="h_f slab IV")),
        ("V", lambda: auto_size(nt, sec_members.section_V, P, 14, inp.hf_stair, label="h stair")),
        ("VI", lambda: sec_members.section_VI(nt, P)),
        ("VII", lambda: sec_members.section_VII(nt, P)),
        ("VIII", lambda: sec_members.section_VIII(nt, P)),
        ("IX", lambda: sec_frame.section_IX(nt, P)),
        ("X", lambda: sec_frame.section_X(nt, P)),
        ("XI", lambda: sec_frame.section_XI(nt, P)),
    ]
    for key, fn in steps:
        if key in sel:
            if verbose:
                print(f"  section {key} ...", flush=True)
            fn()
    if "summary" in P.res or True:
        summary(nt, P)
    nt.save(out_path)
    return P


def summary(nt, P):
    nt.h1("Summary of the results")
    rows = []
    for k, v in P.res.items():
        if isinstance(v, dict) and "summary" in v:
            rows += v["summary"]
    if P.log:
        nt.p("Sizes chosen automatically by the program: " + "; ".join(P.log))
    if rows:
        nt.table(["Element", "Result"], rows, caption="Main results")
