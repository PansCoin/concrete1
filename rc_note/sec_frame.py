# -*- coding: utf-8 -*-
"""Sections IX - XI : column, frame on axis 2, pad footing."""
from __future__ import annotations

import math

import numpy as np

from .engine import S, N, P, sqrt, emin, emax, eabs, fmt
from .design import (NullNote, materials, bending, shear_links, flange_check, beam_bars,
                     required_As, interaction_curve, column_bars, BAR_AREA)
from .project import ceil_to, roof_actions
from .statics import ContinuousBeam, Frame2D
from .sec_members import beam_eff_depth, beff_T


def dry(nt):
    return isinstance(nt, NullNote)


def alpha_n(n, psi0=0.7):
    return 1.0 if n <= 1 else (2 + (n - 2) * psi0) / n


# ----------------------------------------------------------------------------
# column design helper (axial force + bending, symmetric reinforcement)
# ----------------------------------------------------------------------------
def column_design(nt, P_, name, NEd, M01, M02, b_mm, h_mm, l_col, l0, mat, plane, As_guess=None,
                  phi_ef=2.0):
    """b_mm: width (perpendicular to bending), h_mm: depth in the direction of bending.
    NEd [kN], M01/M02 [kNm] first order end moments (|M02| ≥ |M01|), l0 [m]"""
    fcd_ax = 0.85 * mat["fck"] / 1.5
    fyd = mat["fyd"]
    if not dry(nt) or As_guess is None or As_guess >= 0:
        # iterate the reinforcement ratio ω (used in λ_lim and K_r) silently
        g = As_guess or 0.01 * b_mm * h_mm
        for _ in range(12):
            r_ = column_design(NullNote(), P_, name, NEd, M01, M02, b_mm, h_mm, l_col, l0, mat, plane,
                               As_guess=-g - 1e-9, phi_ef=phi_ef)
            if not r_["ok"] or abs(r_["As"] - g) < 1:
                break
            g = max(r_["As"], 0.002 * b_mm * h_mm)
        As_guess = g
    As_guess = abs(As_guess) if As_guess is not None else None
    nt.p(f"{name} - bending {plane}: b = {fmt(b_mm)} mm, h = {fmt(h_mm)} mm", bold=True)
    hS = S("h", h_mm, "mm")
    l0S = nt.given("l_0", l0, "m", "Effective length")
    i = nt.calc("i", hS / sqrt(N(12)), "mm", "Radius of gyration")
    lam = nt.calc("λ", l0S * N(1000) / i, "", "Slenderness")
    Ac = b_mm * h_mm
    n = nt.calc("n", S("N_Ed", NEd, "kN") * N(1000) / (S("A_c", Ac, "mm²") * S("f_cd", fcd_ax, "N/mm²")), "",
                "Relative normal force (f_cd with α_cc = 0.85)")
    As0 = As_guess or max(0.002 * Ac, 0.1 * NEd * 1000 / fyd)
    om = As0 * fyd / (Ac * fcd_ax)
    B = math.sqrt(1 + 2 * om)
    if abs(M02) > 1e-6:
        rm = M01 / M02
    else:
        rm = 1.0
    C = 1.7 - rm
    lim = nt.calc("λ_lim", N(20) * S("A", 0.7) * S("B", B, digits=3) * S("C", C, digits=3) / sqrt(n), "",
                  "EC2 5.8.3.1: A = 0.7, B = √(1+2ω), C = 1.7 − r_m")
    slender = lam.v > lim.v
    ei = nt.calc("e_i", emax(l0S * N(1000) / N(400), hS / N(30), N(20)), "mm",
                 "Eccentricity from imperfections (EC2 6.1(4), 5.2(7))")
    m02 = abs(M02)
    m01 = M01 * (1 if M02 >= 0 else -1)
    M0e = max(0.6 * m02 + 0.4 * m01, 0.4 * m02)
    if not slender:
        nt.ok("λ ≤ λ_lim - second order effects may be ignored", True)
        MEd = nt.calc("M_Ed", S("M_02", abs(M02), "kNm") + S("N_Ed", NEd, "kN") * ei / N(1000), "kNm",
                      "M_Ed = M_02 + N_Ed·e_i")
    else:
        nt.info("λ > λ_lim - second order effects are taken into account (nominal curvature method, EC2 5.8.8)")
        d = h_mm - 45
        nu_ = om + 1
        Kr = max(min((nu_ - n.v) / (nu_ - 0.4), 1.0), 0.0)
        beta = 0.35 + mat["fck"] / 200 - lam.v / 150
        Kphi = max(1 + beta * phi_ef, 1.0)
        nt.given("K_r", Kr, "", "K_r = (n_u − n)/(n_u − n_bal) ≤ 1")
        nt.given("K_φ", Kphi, "", f"K_φ = 1 + β·φ_ef, φ_ef = {fmt(phi_ef)}")
        r0 = nt.calc("1/r_0", mat["f_yd"] / (S("E_s", 200000, "N/mm²") * N(0.45) * S("d", d, "mm")), "1/mm",
                     digits=7)
        r = nt.calc("1/r", S("K_r", Kr) * S("K_φ", Kphi) * r0, "1/mm", digits=7)
        e2 = nt.calc("e_2", r * (l0S * N(1000))**2 / N(10), "mm", "Second order eccentricity")
        MEd = nt.calc("M_Ed", emax(S("M_0e", M0e, "kNm") + S("N_Ed", NEd, "kN") * ei / N(1000),
                                    S("M_02", abs(M02), "kNm") + S("N_Ed", NEd) * ei / N(1000))
                      + S("N_Ed", NEd) * e2 / N(1000), "kNm", "M_Ed = max(M_0e; M_02) + N_Ed·e_i + N_Ed·e_2")
    mu = nt.calc("μ_Ed", MEd * N(1e6, "10⁶") / (S("b", b_mm) * hS**2 * S("f_cd", fcd_ax)), "",
                 "Relative moment")
    nt.p("Required reinforcement from the N-M interaction diagram of the section (symmetric "
         "reinforcement, d_1 = 45 mm, rectangular stress block, ε_cu = 3.5 ‰):")
    As = required_As(NEd * 1000, MEd.v * 1e6, b_mm, h_mm, 45, fcd_ax, fyd)
    if As is None:
        nt.ok("The section is too small for N_Ed, M_Ed - increase the column", False)
        return dict(As=float("nan"), MEd=MEd.v, ok=False)
    nt.p(f"(ω used for λ_lim and K_r: ω = {fmt(om)} - iterated until it agrees with the result)", italic=True)
    om_tot = nt.given("ω_tot", As * fyd / (Ac * fcd_ax), "", "Mechanical reinforcement ratio (from the diagram)",
                      digits=3)
    Ast = nt.calc("A_s,tot", om_tot * S("b", b_mm) * hS * S("f_cd", fcd_ax) / mat["f_yd"], "mm²")
    return dict(As=Ast.v, MEd=MEd.v, ok=True, slender=slender, lam=lam.v, lim=lim.v)


# ============================================================================
# IX  column C10
# ============================================================================
def section_IX(nt, P_):
    G, inp, pl = P_.G, P_.inp, P_.plot
    nt.h1("IX. Design of reinforced concrete columns")
    nt.p(f"Column C10 at the intersection of axes 5 and B (offices). It carries beam B21 (axis 5) "
         f"and the continuous beam B12 (axis B, axes 4-7) on every floor, and the roof.")
    vi = P_.res.get("VI", {})
    hB21 = vi.get("h", 60)
    gk_off = P_.res.get("IV", {}).get("gk", 4.96)
    hf_off = P_.res.get("IV", {}).get("hf", 14)
    gk_corr = P_.res.get("I", {}).get("gk", 4.46)
    hf_corr = P_.res.get("I", {}).get("hf", 12)
    h12 = inp.B12_h or 60
    nt.h2("1. Static scheme")
    bc, hc = inp.C10_b, inp.C10_h
    nt.p(f"Cross-section {fmt(bc)}/{fmt(hc)} cm. Storeys: first h_b = {fmt(inp.hb)} cm, then "
         f"{inp.n_floors} × h_s = {fmt(inp.hs)} cm. The column is part of a braced structure "
         "(walls) - effective length l_0 = 0.7·l.")
    nt.h2("2. Actions")
    nt.h3("2.1 From beam B21 (section VI)")
    Rg21 = nt.given("R_gd,B21", vi.get("Rg", 100), "kN", "Design reaction - permanent")
    Rq21 = nt.given("R_qd,B21", vi.get("Rq", 40), "kN", "Design reaction - variable")
    nt.h3("2.2 From the continuous beam B12 (axis B)")
    a = inp.a / 100
    hs = inp.hs / 100
    g1 = nt.calc("g_k,1", S("b", inp.B12_b / 100, "m") * S("h", h12 / 100, "m") * N(25) +
                 S("t_w", inp.wall_t, "m") * (S("h_s", hs, "m") - S("h", h12 / 100, "m")) * S("γ_w", inp.wall_gamma) +
                 N(2) * N(0.02) * (S("h_s", hs, "m") - S("h_f", hf_off / 100, "m")) * N(18), "kN/m",
                 "Self-weight of B12 + brick wall + plaster")
    gcor = nt.calc("g_k,2", S("g_k,corr", gk_corr, "kN/m²") * S("c", inp.c / 200, "m"), "kN/m",
                   f"From the corridor slab {G.no_corr} (one-way, span c)")
    qcor = nt.calc("q_k,2", S("q_k", inp.q_office, "kN/m²") * S("c", inp.c / 200, "m"), "kN/m")
    short = min(inp.a, inp.b) / 100
    peak = short / 2
    tri = inp.a <= inp.b
    goff = nt.calc("g_k,3", S("g_k,off", gk_off, "kN/m²") * S("l_s", short, "m") / 2, "kN/m",
                   "Peak value from the office slabs (" + ("triangle" if tri else "trapezoid") + ")")
    qoff = nt.calc("q_k,3", S("q_k", inp.q_office, "kN/m²") * S("l_s", short, "m") / 2, "kN/m")
    ramp = peak / a

    def prof(xi):
        return 1 - abs(2 * xi - 1) if tri else min(1.0, xi / ramp, (1 - xi) / ramp)

    cb = ContinuousBeam([a, a, a])
    gfun = lambda xi: 1.35 * (g1.v + gcor.v + goff.v * prof(xi))
    qfun = lambda xi: 1.5 * (qcor.v + qoff.v * prof(xi))
    env = cb.envelope({i: gfun for i in range(3)}, {i: qfun for i in range(3)})
    Rg12 = nt.given("R_gd,B12", env["Rg"][1], "kN", "Design reaction on axis 5 - permanent (stiffness method)")
    Rq12 = nt.given("R_qd,B12", env["Rmax"][1] - env["Rg"][1], "kN",
                    "Design reaction on axis 5 - variable, pattern loading for max R")
    nt.h3("2.3 From the roof")
    gkr, sk = roof_actions(nt, hf_off, inp.s_k, "roof (offices / corridor)")
    gr1 = S("g_k,b", inp.B12_b / 100 * h12 / 100 * 25 + 2 * 0.02 * (h12 - hf_off) / 100 * 18, "kN/m")
    grfun = lambda xi: 1.35 * (gr1.v + gkr.v * inp.c / 200 + gkr.v * peak * prof(xi))
    srfun = lambda xi: 1.5 * (sk.v * inp.c / 200 + sk.v * peak * prof(xi))
    envr = cb.envelope({i: grfun for i in range(3)}, {i: srfun for i in range(3)})
    L21 = inp.b / 100
    g21r = (inp.B21_b / 100 * hB21 / 100 * 25) * L21 / 2 + gkr.v * (L21 / 2 if inp.b <= inp.a else 0) * L21 / 2
    Rgr = nt.given("R_gd,r", envr["Rg"][1] + 1.35 * g21r, "kN", "Roof beams B12 + B21 - permanent")
    Rsr = nt.given("R_qd,r", envr["Rmax"][1] - envr["Rg"][1] + 1.5 * inp.s_k * L21 / 2 * L21 / 2, "kN",
                   "Roof - snow")
    nt.h3("2.4 Self-weight of the column (one storey)")
    Gc = nt.calc("G_d,c", N(1.35) * (S("b", bc / 100, "m") * S("h", hc / 100, "m") * S("h_s", hs, "m") * N(25) +
                                     N(2) * N(0.02) * (S("b", bc / 100) + S("h", hc / 100)) * S("h_s", hs) * N(18)),
                 "kN")
    nt.h2("3. Static analysis - normal forces")
    Ng = nt.calc("N_g1", Rg21 + Rg12 + Gc, "kN", "Permanent - one floor")
    Nq = nt.calc("N_q1", Rq21 + Rq12, "kN", "Variable - one floor")
    Ngr = nt.calc("N_gr", Rgr + Gc, "kN", "Permanent - roof")
    Nsr = nt.calc("N_sr", Rsr, "kN", "Variable - roof")
    nt.p("The variable action of n floors is reduced by α_n = (2 + (n − 2)·ψ_0)/n, ψ_0 = 0.7 "
         "(EN 1991-1-1, 6.3.1.2(11)).")
    rows = []
    sections = []
    nf = inp.n_floors
    for k in range(nf, -1, -1):
        floors = nf - k
        an = alpha_n(floors)
        NG = Ngr.v + floors * Ng.v
        NQ = Nsr.v + an * floors * Nq.v
        sections.append((k, floors, an, NG, NQ, NG + NQ))
        rows.append((f"{k}-{k}", str(floors), fmt(an), fmt(NG), fmt(NQ), fmt(NG + NQ)))
    nt.table(["Section", "Floors above", "α_n", "N_g [kN]", "N_q [kN]", "N_Ed [kN]"], rows,
             caption="Normal forces in column C10")
    nt.h2("4. Design of the column")
    mat = materials(nt, inp.fck, inp.fyk)
    fcd_ax = 0.85 * inp.fck / 1.5
    res = {}
    for k in (0, 1):
        sec = [s for s in sections if s[0] == k][0]
        NEd = sec[5]
        l_col = (inp.hb + 50) / 100 if k == 0 else inp.hs / 100
        nt.h3(f"4.{k + 1} Section {k}-{k}  (N_Ed = {fmt(NEd)} kN)")
        nt.p("Preliminary design for the axial force (ρ = 1 %):", italic=True)
        Ac_req = nt.calc("A_c,req", S("N_Ed", NEd, "kN") * N(1000) / (S("f_cd", fcd_ax) + N(0.01) * mat["f_yd"]),
                         "mm²")
        Asmin = nt.calc("A_s,min", emax(N(0.1) * S("N_Ed", NEd) * N(1000) / mat["f_yd"],
                                        N(0.002) * S("A_c", bc * hc * 100, "mm²")), "mm²", "EC2 9.5.2(2)")
        l0 = 0.7 * l_col
        rw = column_design(nt, P_, "Weak axis", NEd, 0.0, 0.0, hc * 10, bc * 10, l_col, l0, mat,
                           "about the weak axis", As_guess=Asmin.v)
        As = max(rw["As"], Asmin.v)
        txt, Asp, phi, nb = column_bars(As, bc * 10, hc * 10)
        nt.p(f"A_s,tot = max(A_s,tot; A_s,min) = {fmt(As)} mm² → adopted {txt} ({fmt(Asp)} mm²), "
             f"ρ = {fmt(100 * Asp / (bc * hc * 100))} % (0.2 % ≤ ρ ≤ 4 %)", bold=True)
        res[k] = (txt, Asp, phi, nb)
    if not dry(nt):
        txt, Asp, phi, nb = res[0]
        f = pl.column_section(bc * 10, hc * 10, nb, phi, f"C10 - {txt}", "IX_col")
        nt.fig(f, "Cross-section of column C10 (section 0-0)", 6)
    nt.p("Links: Φ8, spacing s ≤ min(20·Φ_long; b; 400 mm) = "
         f"{fmt(min(20 * res[0][2], bc * 10, 400))} mm, reduced by 0.6 within h above/below beams "
         "and at laps (EC2 9.5.3).", italic=True)
    P_.res["IX"] = dict(N0=sections[-1][5],
                        summary=[("Column C10", f"{fmt(bc)}/{fmt(hc)} cm, 0-0: {res[0][0]}; 1-1: {res[1][0]}")])
    return True


# ============================================================================
# X  frame on axis 2
# ============================================================================
def T_inertia(bw, h, beff, hf):
    A1, A2 = bw * h, (beff - bw) * hf
    y = (A1 * h / 2 + A2 * (h - hf / 2)) / (A1 + A2)
    I = bw * h**3 / 12 + A1 * (h / 2 - y)**2 + (beff - bw) * hf**3 / 12 + A2 * (h - hf / 2 - y)**2
    return I, A1 + A2


class FrameModel:
    def __init__(self, P_, hB15):
        G, inp = P_.G, P_.inp
        self.P_ = P_
        E = 22 * ((inp.fck + 8) / 10) ** 0.3 * 1e6   # kN/m2
        hf = P_.res.get("II", {}).get("hf", 12) / 100
        Ly = G.Y["E"] / 100
        yC = G.Y["C"] / 100
        bw = inp.B15_b / 100
        h = hB15 / 100
        beff = min(bw + 2 * (0.2 * (inp.a - 30) / 200 + 0.1 * 0.85 * yC), bw + 2 * 0.2 * 0.85 * yC,
                   bw + (inp.a - 30) / 100)
        self.Ib, self.Ab = T_inertia(bw, h, beff, hf)
        self.beff = beff
        b1, h1 = inp.C1_b / 100, inp.C1_h / 100
        b7, h7 = inp.C7_b / 100, inp.C7_h / 100
        self.Ic1, self.Ic7 = b1 * h1**3 / 12, b7 * h7**3 / 12
        fr = Frame2D()
        self.fr = fr
        levels = [l / 100 for l in G.levels]
        self.levels = levels
        ys_sec = [k * G.s_h / 100 for k in range(1, 2 * G.n_half)]
        self.ys_sec = ys_sec
        ys = sorted(set([0.0, yC, Ly] + ys_sec))
        self.ys = ys
        self.beam_elems = {}     # storey -> list
        self.col_elems = {}      # (column, storey) -> list
        self.nodes = {}
        for j, z in enumerate(levels):
            for y in ys:
                if j == 0 and y not in (0.0, yC, Ly):
                    continue
                self.nodes[(y, j)] = fr.node(y, z)
        for y in (0.0, yC, Ly):
            fr.support(self.nodes[(y, 0)])
        nseg = 4
        for j in range(1, len(levels)):
            for y, (Ic, Ac, tag) in ((0.0, (self.Ic1, b1 * h1, "C1")), (yC, (self.Ic7, b7 * h7, "C7")),
                                     (Ly, (self.Ic1, b1 * h1, "C12"))):
                ids = []
                z0, z1 = levels[j - 1], levels[j]
                prev = self.nodes[(y, j - 1)]
                for k in range(1, nseg + 1):
                    nd = fr.node(y, z0 + (z1 - z0) * k / nseg) if k < nseg else self.nodes[(y, j)]
                    ids.append(fr.elem(prev, nd, E, Ac, Ic, tag=f"{tag}|s" if k == 1 else (f"{tag}|e" if k == nseg else "")))
                    prev = nd
                self.col_elems[(tag, j)] = ids
            ids = []
            for i in range(len(ys) - 1):
                ids.append(fr.elem(self.nodes[(ys[i], j)], self.nodes[(ys[i + 1], j)], E, self.Ab, self.Ib,
                                   tag="B15"))
            self.beam_elems[j] = ids
        self.yC, self.Ly = yC, Ly

    def case(self, nodal, udl):
        return self.fr.solve(nodal, udl)


def section_X(nt, P_):
    G, inp, pl = P_.G, P_.inp, P_.plot
    hB15 = inp.B15_h or ceil_to((G.Y["C"]) / 12, 5)
    viii = P_.res.get("VIII", {})
    hB5 = viii.get("h", 45)
    hf = P_.res.get("II", {}).get("hf", 12)
    gks = P_.res.get("II", {}).get("gk", hf / 100 * 25 + 1.46)
    nt.h1("X. Design of reinforced concrete frame")
    nt.p(f"Frame on axis 2: beams B15 between axes A - C - E (two spans of {fmt(G.Y['C'])} cm), columns "
         f"C1 (A), C7 (C) and C12 (E). {G.n_storeys} storeys: h_b = {fmt(inp.hb)} cm and "
         f"{inp.n_floors} × h_s = {fmt(inp.hs)} cm; fixed at the top of the footings.")
    nt.h2("1. Static scheme and stiffness")
    M = FrameModel(P_, hB15)
    nt.p(f"Beam B15: b_w/h = {fmt(inp.B15_b)}/{fmt(hB15)} cm, flange h_f = {fmt(hf)} cm, "
         f"b_eff = {fmt(M.beff * 100)} cm. Columns C1, C12: {fmt(inp.C1_b)}/{fmt(inp.C1_h)} cm; "
         f"C7: {fmt(inp.C7_b)}/{fmt(inp.C7_h)} cm (h in the plane of the frame).")
    nt.given("I_b", M.Ib * 1e8, "cm⁴", "Moment of inertia of the T-section of the beam")
    nt.given("I_c,1", M.Ic1 * 1e8, "cm⁴", "Columns C1, C12")
    nt.given("I_c,7", M.Ic7 * 1e8, "cm⁴", "Column C7")
    nt.h2("2. Actions (characteristic values)")
    s = G.s_h / 100
    a = inp.a / 100
    hsm = inp.hs / 100
    nt.h3("2.1 Point loads from the secondary beams B5-B9 (section VIII)")
    G1 = nt.given("G_k,1", viii.get("RBg", 150), "kN", "Reaction R_B of B5 - permanent")
    Q1 = nt.given("Q_k,1", viii.get("RBq", 100), "kN", "Reaction R_B of B5 - variable")
    nt.h3("2.2 Facade beams on axes A and E (B1, B10) - reaction on axis 2")
    bwf, hff = 0.30, 0.60
    gf = nt.calc("g_k,f", S("b", bwf, "m") * S("h", hff, "m") * N(25) +
                 S("b", bwf) * (S("h_s", hsm, "m") - S("h", hff)) * N(18) +
                 N(2) * N(0.02) * (S("h_s", hsm) - S("h_f", hf / 100, "m")) * N(18) +
                 S("g_k,slab", gks, "kN/m²") * S("s", s / 2, "m"), "kN/m",
                 "Beam 30/60 + facade wall + plaster + slab (s/2)")
    qf = nt.calc("q_k,f", S("q_k1", inp.qk1, "kN/m²") * S("s", s / 2, "m"), "kN/m")
    G2 = nt.calc("G_k,2", N(1.25) * gf * S("a", a, "m"), "kN", "Middle reaction of a two-span beam (10/8·w·l)")
    Q2 = nt.calc("Q_k,2", N(1.25) * qf * S("a", a, "m"), "kN")
    nt.h3("2.3 Roof")
    gkr, sk = roof_actions(nt, hf, inp.s_k, "roof above the hall")
    gr5 = nt.calc("g_k,r5", S("b_w", inp.B5_b / 100, "m") * (S("h", hB5 / 100, "m") - S("h_f", hf / 100, "m")) * N(25)
                  + gkr * S("s", s, "m"), "kN/m", "Roof beams B5-B9")
    G1r = nt.calc("G_kr,1", N(1.25) * gr5 * S("a", a, "m"), "kN")
    Q1r = nt.calc("Q_kr,1", N(1.25) * sk * S("s", s, "m") * S("a", a, "m"), "kN")
    G2r = nt.calc("G_kr,2", N(1.25) * (S("b", bwf) * S("h", hff) * N(25) + gkr * S("s", s / 2) + N(1.0)) * S("a", a), "kN",
                  "Roof facade beam + parapet 1.0 kN/m")
    Q2r = nt.calc("Q_kr,2", N(1.25) * sk * S("s", s / 2) * S("a", a), "kN")
    nt.h3("2.4 Frame beam B15 and columns")
    gb = nt.calc("g_k,B15", S("b_w", inp.B15_b / 100, "m") * (S("h", hB15 / 100, "m") - S("h_f", hf / 100, "m")) * N(25)
                 + N(0.02) * N(18) * (N(2) * (S("h", hB15 / 100) - S("h_f", hf / 100)) + S("b_w", inp.B15_b / 100)),
                 "kN/m", "Web of B15 + plaster")
    gc1 = inp.C1_b / 100 * inp.C1_h / 100 * 25
    gc7 = inp.C7_b / 100 * inp.C7_h / 100 * 25
    nt.p(f"Self-weight of the columns: C1/C12: {fmt(gc1)} kN/m, C7: {fmt(gc7)} kN/m (applied at the "
         f"top of every storey).")
    # ------------------------------------------------------------- analysis
    fr = M.fr
    nlev = len(M.levels)
    top = nlev - 1

    def g_case():
        nodal, udl = {}, {}
        for j in range(1, nlev):
            roof = j == top
            for y in M.ys_sec:
                n_ = M.nodes[(y, j)]
                nodal[n_] = (0, -(G1r.v if roof else G1.v), 0)
            for y in (0.0, M.Ly):
                n_ = M.nodes[(y, j)]
                fx, fy, mz = nodal.get(n_, (0, 0, 0))
                nodal[n_] = (0, fy - (G2r.v if roof else G2.v), 0)
            hgt = M.levels[j] - M.levels[j - 1]
            for y, gc in ((0.0, gc1), (M.yC, gc7), (M.Ly, gc1)):
                n_ = M.nodes[(y, j)]
                fx, fy, mz = nodal.get(n_, (0, 0, 0))
                nodal[n_] = (0, fy - gc * hgt, 0)
            for e in M.beam_elems[j]:
                udl[e] = (-gb.v, -gb.v)
        return nodal, udl

    def q_case(j, bay):
        nodal = {}
        roof = j == top
        Qs, Qf = (Q1r.v, Q2r.v) if roof else (Q1.v, Q2.v)
        for y in M.ys_sec:
            inbay = (y < M.yC - 1e-6) if bay == 0 else (y > M.yC + 1e-6)
            if inbay:
                nodal[M.nodes[(y, j)]] = (0, -Qs, 0)
            elif abs(y - M.yC) < 1e-6:
                nodal[M.nodes[(y, j)]] = (0, -Qs / 2, 0)
        yf = 0.0 if bay == 0 else M.Ly
        n_ = M.nodes[(yf, j)]
        fx, fy, mz = nodal.get(n_, (0, 0, 0))
        nodal[n_] = (0, fy - Qf, 0)
        return nodal, {}

    rG = M.case(*g_case())
    rQ = {(j, bay): M.case(*q_case(j, bay)) for j in range(1, nlev) for bay in (0, 1)}

    def combo(fG, fQ, pattern):
        """design (1.35/1.5) or characteristic (1/1) combination of the basic cases;
        returns per element (xs, N, V, M)"""
        out = {}
        for ei_ in range(len(fr.elems)):
            xs, Ng_, Vg_, Mg_ = rG.internal(ei_, 11)
            Nn, Vv, Mm = fG * Ng_, fG * Vg_, fG * Mg_
            for key in pattern:
                _, nq, vq, mq = rQ[key].internal(ei_, 11)
                Nn, Vv, Mm = Nn + fQ * nq, Vv + fQ * vq, Mm + fQ * mq
            out[ei_] = (xs, Nn, Vv, Mm)
        return out

    def react(fG, fQ, pattern, node):
        Rg = np.array(rG.reaction(node)) * fG
        for key in pattern:
            Rg = Rg + fQ * np.array(rQ[key].reaction(node))
        return Rg

    allQ = set(rQ.keys())
    pat2 = {(j, (j - 1) % 2) for j in range(1, nlev)}
    pat3 = {(j, j % 2) for j in range(1, nlev)}
    LCs = {"LC1": allQ, "LC2": pat2, "LC3": pat3}
    R = {k: combo(1.35, 1.5, v) for k, v in LCs.items()}
    nt.p("Load cases (design values 1.35·G + 1.5·Q):")
    nt.bullet("LC1 - variable load on all spans of all floors (maximum normal forces and support moments)")
    nt.bullet("LC2 - chequerboard: variable load in bay A-C on storeys 1, 3, 5 and in bay C-E on storeys 2, 4")
    nt.bullet("LC3 - the opposite chequerboard (maximum span moments / column moments)")
    nt.p("The frame is analysed by the stiffness method (Euler-Bernoulli elements, E_cm, gross "
         "sections, T-section for the beams).")
    if not dry(nt):
        pls = []
        for j in range(1, nlev):
            roof = j == top
            for y in M.ys_sec:
                pls.append((y, M.levels[j], f"{fmt(G1r.v if roof else G1.v)}+{fmt(Q1r.v if roof else Q1.v)}", "#c0392b"))
            for y in (0.0, M.Ly):
                pls.append((y, M.levels[j], f"{fmt(G2r.v if roof else G2.v)}+{fmt(Q2r.v if roof else Q2.v)}", "#1f5fa8"))
        f = pl.frame_loads(fr, M.levels, M.ys, pls, "", "Frame on axis 2 - characteristic point loads G_k+Q_k [kN]",
                           "X_loads")
        nt.fig(f, "Static scheme of the frame and characteristic loads from the secondary beams", 13)
        for lc in ("LC1", "LC2", "LC3"):
            f = pl.frame(fr, {e: (v[0], v[3]) for e, v in R[lc].items()}, "M",
                         f"Bending moments M_Ed [kNm] - {lc}", f"X_M_{lc}")
            nt.fig(f, f"Bending moment diagram - {lc}", 13)
        f = pl.frame(fr, {e: (v[0], v[2]) for e, v in R["LC1"].items()}, "V", "Shear forces V_Ed [kN] - LC1",
                     "X_V")
        nt.fig(f, "Shear force diagram - LC1", 13)
        f = pl.frame(fr, {e: (v[0], v[1]) for e, v in R["LC1"].items()}, "N", "Normal forces N_Ed [kN] - LC1",
                     "X_N")
        nt.fig(f, "Normal force diagram - LC1", 13)
    # ------------------------------------------------------- extract values
    def beam_vals(lc, j):
        xs_all, M_all, V_all = [], [], []
        y0 = 0
        for e in M.beam_elems[j]:
            xs, Nn, Vv, Mm = R[lc][e]
            n1 = fr.elems[e].n1
            ys0 = fr.nodes[n1][0]
            xs_all += list(ys0 + xs)
            M_all += list(Mm)
            V_all += list(Vv)
        return np.array(xs_all), np.array(M_all), np.array(V_all)

    rows = []
    best = dict(span=(0, None), sup=(0, None), end=(0, None), V=(0, None))
    for lc in LCs:
        for j in range(1, nlev):
            X, Mm, Vv = beam_vals(lc, j)
            kC = np.argmin(abs(X - M.yC))
            Msp = Mm.max()
            MC = Mm[abs(X - M.yC) < 1e-6].min()
            MA = Mm[0]
            Vm = abs(Vv).max()
            rows.append((lc, f"{j}", fmt(Msp), fmt(MC), fmt(MA), fmt(Vm)))
            if Msp > best["span"][0]:
                best["span"] = (Msp, (lc, j))
            if -MC > best["sup"][0]:
                best["sup"] = (-MC, (lc, j))
            if -MA > best["end"][0]:
                best["end"] = (-MA, (lc, j))
            if Vm > best["V"][0]:
                best["V"] = (Vm, (lc, j))
    nt.table(["LC", "Floor", "max M_span", "M at C7", "M at C1", "max |V|"], rows,
             caption="Frame beam B15 - design values [kNm, kN]")
    # columns
    def col_vals(lc, tag, j):
        ids = M.col_elems[(tag, j)]
        xs0, N0, V0, M0 = R[lc][ids[0]]
        xs1, N1, V1, M1 = R[lc][ids[-1]]
        return -N0[0], M0[0], M1[-1]   # compression +, M bottom, M top

    crow = []
    for lc in LCs:
        for tag in ("C1", "C7"):
            for j in (1, 2):
                Nc, Mb, Mt = col_vals(lc, tag, j)
                crow.append((lc, tag, f"{j}", fmt(Nc), fmt(Mb), fmt(Mt)))
    nt.table(["LC", "Column", "Storey", "N_Ed [kN]", "M_bottom [kNm]", "M_top [kNm]"], crow,
             caption="Columns - design forces")
    # ------------------------------------------------------------ design beam
    nt.h2("3. Design of the frame beam B15")
    mat = materials(nt, inp.fck, inp.fyk)
    d = beam_eff_depth(nt, hB15)
    bw = S("b_w", inp.B15_b * 10, "mm")
    beff = S("b_eff", M.beff * 1000, "mm")
    hfm = S("h_f", hf * 10, "mm")
    Msp = S("maxM_Ed,span", best["span"][0], "kNm")
    nt.p(f"Maximum span moment: {best['span'][1][0]}, floor {best['span'][1][1]}.")
    flange_check(nt, Msp, beff, hfm, d, mat)
    r1 = bending(nt, Msp, beff, d, mat, "Span section (bottom)", bt=bw, kind="beam", tag="span")
    nt.p(f"Support at column C7 (top) - {best['sup'][1][0]}, floor {best['sup'][1][1]}; moment at the face:",
         bold=True)
    MC = S("M_C7", best["sup"][0], "kNm")
    Vmax = best["V"][0]
    dM = nt.calc("ΔM", S("V_Ed", Vmax, "kN") * S("h_c7", inp.C7_h / 200, "m"), "kNm", "ΔM = V_Ed·h_c/2")
    MCf = nt.calc("M_Ed,C7", MC - dM, "kNm")
    r2 = bending(nt, MCf, bw, d, mat, "", kind="beam", tag="C7")
    ME = S("M_C1", best["end"][0], "kNm")
    nt.p("End support at column C1 (top):", bold=True)
    r3 = bending(nt, ME, bw, d, mat, "", kind="beam", tag="C1")
    nt.h3("Shear")
    sh = shear_links(nt, S("V_Ed", Vmax, "kN"), bw, d, r2["rho_prov"], mat, phi_w=10)
    nt.p("Hanger reinforcement for the reactions of B5-B9 (R = 1.35·G_k,1 + 1.5·Q_k,1):", bold=True)
    Rb = nt.calc("R_B5", N(1.35) * G1 + N(1.5) * Q1, "kN")
    Ah = nt.calc("A_s,hang", Rb * N(1000) / mat["f_yd"], "mm²")
    nt.p(f"→ {math.ceil(Ah.v / (2 * BAR_AREA[10]))} additional two-leg links Φ10 at each secondary beam "
         "(or bent-up bars 2Φ16 at 45°).", bold=True)
    # ------------------------------------------------------------ design column C7
    nt.h2("4. Design of the columns")
    best_c = {}
    for tag in ("C7", "C1"):
        cands = []
        for lc in LCs:
            Nc, Mb, Mt = col_vals(lc, tag, 1)
            cands.append((lc, Nc, Mb, Mt))
        best_c[tag] = cands
    out = {}
    for tag, (bcm, hcm) in (("C7", (inp.C7_b, inp.C7_h)), ("C1", (inp.C1_b, inp.C1_h))):
        nt.h3(f"Column {tag} - first storey ({fmt(bcm)}/{fmt(hcm)} cm)")
        l = inp.hb / 100
        Ic = bcm * hcm**3 / 12
        Ib = M.Ib * 1e8
        nb = 2 if tag == "C7" else 1
        k1 = nt.calc("k_1", S("I_c", Ic, "cm⁴") / S("l", l * 100, "cm") /
                     (N(4 * nb) * S("I_b", Ib, "cm⁴") / S("l_b", G.Y["C"], "cm")), "",
                     "Flexibility of the restraint at the top (course formula)")
        k2 = nt.given("k_2", 0.1, "", "Footing (minimum recommended value)")
        l0 = nt.calc("l_0", N(0.5) * S("l", l, "m") * sqrt((1 + k1 / (N(0.45) + k1)) * (1 + k2 / (N(0.45) + k2))),
                     "m", "Effective length in the plane of the frame (braced, EC2 5.15)")
        l0o = nt.calc("l_0,out", N(0.7) * S("l", l, "m"), "m", "Out of the plane of the frame")
        res_all = []
        for lc, Nc, Mb, Mt in best_c[tag]:
            M02, M01 = (Mb, Mt) if abs(Mb) >= abs(Mt) else (Mt, Mb)
            res_all.append((lc, Nc, M01, M02))
        nt.table(["LC", "N_Ed [kN]", "M_01 [kNm]", "M_02 [kNm]"],
                 [(lc, fmt(Nc), fmt(M01), fmt(M02)) for lc, Nc, M01, M02 in res_all],
                 caption=f"Design forces of column {tag} (first storey)")
        As_need = 0
        for lc, Nc, M01, M02 in res_all:
            if lc == "LC1" or abs(M02) == max(abs(r[3]) for r in res_all):
                nt.p(f"{lc}:", bold=True)
                ri = column_design(nt, P_, tag, Nc, M01, M02,
                                   bcm * 10, hcm * 10, l, l0.v, mat, "in the plane of the frame")
                As_need = max(As_need, ri["As"] if ri["ok"] else 1e9)
        Nmax = max(r[1] for r in res_all)
        ro = column_design(nt, P_, tag, Nmax, 0.0, 0.0, hcm * 10, bcm * 10, l, l0o.v, mat,
                           "out of the plane of the frame (N_max)")
        As_need = max(As_need, ro["As"] if ro["ok"] else 1e9)
        Asmin = max(0.002 * bcm * hcm * 100, 0.1 * Nmax * 1000 / mat["fyd"])
        As_need = max(As_need, Asmin)
        txt, Asp, phi, nbar = column_bars(As_need, bcm * 10, hcm * 10)
        nt.p(f"Required A_s,tot = {fmt(As_need)} mm² (A_s,min = {fmt(Asmin)} mm²) → adopted {txt} "
             f"({fmt(Asp)} mm², ρ = {fmt(100 * Asp / (bcm * hcm * 100))} %)", bold=True)
        if not dry(nt):
            f = pl.column_section(bcm * 10, hcm * 10, nbar, phi, f"{tag} - {txt}", f"X_{tag}")
            nt.fig(f, f"Cross-section of column {tag}", 5.5)
            # interaction diagram
            import matplotlib.pyplot as plt
            c = interaction_curve(bcm * 10, hcm * 10, Asp, 45, 0.85 * inp.fck / 1.5, mat["fyd"])
            fig, ax = plt.subplots(figsize=(5.5, 4))
            ax.plot(c[:, 1] / 1e6, c[:, 0] / 1e3, color="#1f5fa8", label=f"{txt}")
            ax.plot(-c[:, 1] / 1e6, c[:, 0] / 1e3, color="#1f5fa8")
            for lc, Nc, M01, M02 in res_all:
                ax.plot(abs(M02), Nc, "o", color="#c0392b")
                ax.annotate(lc, (abs(M02), Nc), fontsize=7, xytext=(4, 2), textcoords="offset points")
            ax.set_xlabel("M [kNm]")
            ax.set_ylabel("N [kN] (compression +)")
            ax.grid(alpha=0.3)
            ax.legend(fontsize=8)
            ax.set_title(f"N-M interaction diagram - {tag} (first order forces)", fontsize=9)
            path = pl._save(fig, f"X_NM_{tag}")
            nt.fig(path, f"Interaction diagram of column {tag} with the design forces", 11)
        out[tag] = (txt, Asp)
    nt.p("Links in the columns: Φ8 (Φ10 for Φ25 bars), s ≤ min(20·Φ; b; 400 mm), 0.6·s in the "
         "critical regions at the beams and at laps.", italic=True)
    Nbase = {lc: react(1.35, 1.5, pat, M.nodes[(M.yC, 0)]) for lc, pat in LCs.items()}
    Nk = react(1.0, 1.0, allQ, M.nodes[(M.yC, 0)])
    P_.res["X"] = dict(N_Ed=Nbase["LC1"][1], M_Ed=Nbase["LC1"][2], N_k=Nk[1], M_k=Nk[2],
                       hc=inp.C7_h, bc=inp.C7_b, hB15=hB15,
                       summary=[("Frame beam B15", f"{fmt(inp.B15_b)}/{fmt(hB15)} cm: span {r1['bars']}, "
                                 f"over C7 {r2['bars']}, over C1 {r3['bars']}, links {sh['links']}"),
                                ("Column C7 (1st storey)", f"{fmt(inp.C7_b)}/{fmt(inp.C7_h)} cm, {out['C7'][0]}"),
                                ("Columns C1/C12 (1st storey)", f"{fmt(inp.C1_b)}/{fmt(inp.C1_h)} cm, {out['C1'][0]}")])
    return True


# ============================================================================
# XI  pad footing under C7
# ============================================================================
def section_XI(nt, P_, Hf=None):
    if Hf is None:
        Hf = 0
        for _ in range(40):
            ok, Hnext = _section_XI(NullNote(), P_, Hf)
            if ok:
                break
            Hf = Hnext + 50
        P_.log.append(f"footing height: {fmt(Hnext / 10)} cm")
    return _section_XI(nt, P_, Hf)[0]


def _section_XI(nt, P_, Hf_force=0):
    G, inp, pl = P_.G, P_.inp, P_.plot
    x = P_.res.get("X", {})
    nt.h1("XI. Design of reinforced concrete pad footing for single columns")
    hc, bc = inp.C7_h, inp.C7_b
    nt.p(f"Pad footing under column C7 ({fmt(bc)}/{fmt(hc)} cm), frame on axis 2.")
    nt.h2("1. Actions")
    NEd = nt.given("N_Ed", x.get("N_Ed", 3000), "kN", "Design normal force at the base (LC1, frame X)")
    MEd = nt.given("M_Ed", abs(x.get("M_Ed", 0)), "kNm", "Corresponding bending moment")
    Nk = nt.given("N_k", x.get("N_k", 2200), "kN", "Characteristic normal force (G_k + Q_k) - SLS")
    Mk = nt.given("M_k", abs(x.get("M_k", 0)), "kNm")
    Gf = nt.calc("G_f,k", N(0.15) * Nk, "kN", "Weight of the footing and the backfill (≈ 15 %)")
    Nfk = nt.calc("N_f,k", Nk + Gf, "kN")
    nt.h2("2. Plan size of the footing (SLS)")
    R0 = nt.given("R_0", inp.R0, "kN/m²", "Characteristic soil pressure (assignment)")
    Af = nt.calc("A_f,req", Nfk / R0, "m²")
    hcm, bcm = S("h_c", hc / 100, "m"), S("b_c", bc / 100, "m")
    lc1 = nt.calc("l_c,req", N(0.5) * (sqrt(Af) - (hcm + bcm) / 2), "m",
                  "Equal overhangs on all sides")
    lc = ceil_to(lc1.v * 100, 5) / 100
    lcS = nt.given("l_c", lc, "m", "Adopted overhang (rounded up to 5 cm)")
    L = nt.calc("L_f", N(2) * lcS + hcm, "m")
    B = nt.calc("B_f", N(2) * lcS + bcm, "m")
    A = nt.calc("A_f", L * B, "m²")
    sk = nt.calc("σ_k", Nfk / A, "kN/m²")
    nt.compare(sk, "≤", R0, ok_text="The soil pressure is acceptable")
    e = nt.calc("e", Mk / Nfk, "m", "Eccentricity of the load (in the plane of the frame)")
    smax = nt.calc("σ_k,max", Nfk / A * (1 + N(6) * e / L), "kN/m²")
    nt.compare(smax, "≤", S("1.2·R_0", 1.2 * inp.R0, "kN/m²"), ok_text="Edge pressure acceptable")
    nt.calc("L_f/B_f", L / B, "", "Shape (≤ 1.5 recommended)")
    nt.h2("3. Thickness and reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    sgr = nt.calc("σ_gr", NEd / A, "kN/m²", "Design soil pressure (self-weight not included)")
    u0 = nt.calc("u_0", N(2) * (S("h_c", hc * 10, "mm") + S("b_c", bc * 10, "mm")), "mm",
                 "Perimeter of the column")
    Vred = nt.calc("V_Ed,red", NEd - sgr * hcm * bcm, "kN")
    nu = nt.calc("ν", N(0.6) * (1 - mat["f_ck"] / N(250)), "")
    dreq = nt.calc("d_req", Vred * N(1000) / (u0 * N(0.4) * nu * mat["f_cd"]), "mm",
                   "From v_Ed ≤ v_Rd,max = 0.4·ν·f_cd at the column face (EC2 6.4.5(3))")
    dmin = max(dreq.v, lc * 1000 / 2.5)
    Hf = max(ceil_to(dmin + 50 + 15, 50), Hf_force)
    HfS = nt.given("H_f", Hf, "mm", "Adopted height (≥ d_req + c_nom + Φ, ≥ l_c/2.5 for a rigid footing;"
                   " increased if needed for punching)")
    d = nt.calc("d", HfS - S("c_nom", 50, "mm") - S("φ", 15, "mm"), "mm")
    nt.h3("3.1 Bending reinforcement")
    Mf = nt.calc("M_Ed,f", sgr * lcS**2 / 2, "kNm/m", "Moment at the face of the column (cantilever l_c)")
    r = bending(nt, Mf, S("b", 1000, "mm"), d, mat, "Both directions (per metre)", kind="slab",
                h=S("h", Hf, "mm"))
    nt.h3("3.2 Punching shear (EC2 6.4.4(2))")
    nt.p("The control perimeter is searched between a = 0.2·d and a = 2·d; the soil pressure inside "
         "the perimeter reduces the punching force.")
    k = min(1 + math.sqrt(200 / d.v), 2.0)
    rho = min(r["rho_prov"], 0.02)
    crit = None
    for a_ in np.linspace(0.2 * d.v, 2 * d.v, 37):
        u = 2 * (hc * 10 + bc * 10) + 2 * math.pi * a_
        Ain = (hc * 10 * bc * 10 + 2 * a_ * (hc * 10 + bc * 10) + math.pi * a_**2) / 1e6
        V = NEd.v - sgr.v * Ain
        vEd = V * 1000 / (u * d.v)
        vRd = max(0.18 / 1.5 * k * (100 * rho * inp.fck) ** (1 / 3), 0.035 * k**1.5 * math.sqrt(inp.fck)) * 2 * d.v / a_
        if crit is None or vEd / vRd > crit[0]:
            crit = (vEd / vRd, a_, u, Ain, V, vEd, vRd)
    _, a_, u, Ain, V, vEd, vRd = crit
    aS = nt.given("a_crit", a_, "mm", "Critical control perimeter (largest v_Ed/v_Rd)")
    uS = nt.calc("u", N(2) * (S("h_c", hc * 10) + S("b_c", bc * 10)) + N(2) * S("π", math.pi) * aS, "mm")
    AinS = nt.calc("A_in", (S("h_c", hc * 10) * S("b_c", bc * 10) + N(2) * aS * (S("h_c", hc * 10) + S("b_c", bc * 10))
                            + S("π", math.pi) * aS**2) / N(1e6, "10⁶"), "m²")
    VS = nt.calc("V_Ed,red", NEd - sgr * AinS, "kN")
    vE = nt.calc("v_Ed", VS * N(1000) / (uS * d), "N/mm²")
    kS = nt.calc("k", emin(1 + sqrt(N(200) / d), N(2)), "")
    vR = nt.calc("v_Rd", emax(S("C_Rd,c", 0.12) * kS * (N(100) * S("ρ_l", rho, digits=5) * mat["f_ck"]) ** N(1 / 3),
                              N(0.035) * kS**N(1.5) * sqrt(mat["f_ck"])) * N(2) * d / aS, "N/mm²",
                 "v_Rd = C_Rd,c·k·(100·ρ·f_ck)^(1/3)·2d/a ≥ v_min·2d/a")
    okp = nt.compare(vE, "≤", vR, ok_text="No punching shear reinforcement is required",
                     ng_text="Increase the height of the footing")
    if not dry(nt):
        f = pl.footing(L.v * 100, B.v * 100, hc, bc, Hf / 10, "Pad footing under C7", "XI_footing")
        nt.fig(f, "Pad footing - plan and section", 13)
    P_.res["XI"] = dict(L=L.v * 100, B=B.v * 100, H=Hf / 10,
                        summary=[("Footing under C7", f"{fmt(L.v * 100)} × {fmt(B.v * 100)} × {fmt(Hf / 10)} cm, "
                                  f"{r['bars']} both ways")])
    return okp, Hf
