# -*- coding: utf-8 -*-
"""Sections V - VIII : stairs and beams."""
from __future__ import annotations

import math

import numpy as np

from .engine import S, N, P, sqrt, emin, emax, eabs, eatan, ecos, esin, fmt
from .design import (NullNote, materials, bending, shear_no_links, shear_links, deflection_ld,
                     flange_check, flange_shear, beam_bars, BAR_AREA)
from .project import ceil_to
from .statics import ContinuousBeam


def dry(nt):
    return isinstance(nt, NullNote)


def beam_eff_depth(nt, h_cm, c_nom=25, phi_w=8, phi=20, name="d"):
    return nt.calc(name, S("h", h_cm * 10, "mm") - S("c_nom", c_nom, "mm") - S("φ_w", phi_w, "mm")
                   - S("φ", phi, "mm") / 2, "mm",
                   f"Effective depth (c_nom = {c_nom} mm, links Φ{phi_w}, main bars Φ{phi})")


def beff_T(nt, bw_mm, l0_m, bi_list_m):
    """EC2 5.3.2.1 effective flange width."""
    l0 = S("l_0", l0_m, "m")
    parts = []
    for k, bi in enumerate(bi_list_m, 1):
        biS = S(f"b_{k}", bi, "m")
        be = nt.calc(f"b_eff,{k}", emin(N(0.2) * biS + N(0.1) * l0, N(0.2) * l0, biS), "m",
                     "b_eff,i = 0.2·b_i + 0.1·l_0 ≤ 0.2·l_0 ; ≤ b_i")
        parts.append(be)
    tot = S("b_w", bw_mm / 1000, "m")
    for p_ in parts:
        tot = tot + p_
    beff = nt.calc("b_eff", tot, "m", "Effective width of the flange")
    return beff


# ============================================================================
# V  stairs
# ============================================================================
def section_V(nt, P_, hcm):
    G, inp, pl = P_.G, P_.inp, P_.plot
    nt.h1("V. Design of reinforced concrete stairs")
    nt.p(f"Two-flight staircase between axes 3 and 4. Storey height H = h_b = {fmt(inp.hb)} cm, "
         f"intermediate landing at H/2. Width of a flight d = {fmt(inp.d)} cm.")
    nt.h2("1. Geometry and static scheme")
    H = nt.given("H", inp.hb, "cm", "Height of the storey served by the stair")
    Hf = nt.calc("H_fl", H / 2, "cm", "Height of one flight")
    n = math.ceil(Hf.v / 17.5 - 1e-9)
    nS = nt.given("n", n, "", "Number of risers in a flight (riser ≤ 17.5 cm)")
    hst = nt.calc("h_st", Hf / nS, "cm", "Height of a riser")
    bst_v = max(26.0, math.floor(63 - 2 * hst.v))
    bst = nt.given("b_st", bst_v, "cm", "Width of a tread (2·h_st + b_st ≈ 62-64 cm)")
    nt.calc("2h_st+b_st", 2 * hst + bst, "cm")
    lfl = nt.calc("l_fl", (nS - 1) * bst, "cm", "Horizontal projection of the flight")
    lla = nt.given("l_la", inp.d, "cm", "Depth of the landing (= d)")
    alpha = nt.calc("α", eatan(hst / bst), "°", "Inclination of the flight")
    hS = nt.given("h", hcm, "cm", "Thickness of the waist slab")
    L = nt.calc("l_eff", lfl + lla, "cm", "Span of the simply supported model (flight + landing)")
    if not dry(nt):
        f = pl.stair(n - 1, bst.v / 100, hst.v / 100, lla.v / 100, "Static scheme of the flight", "V_stair")
        nt.fig(f, "Flight and landing - simply supported inclined slab", 14)
    nt.h2("2. Actions (per 1 m width)")
    nt.p("Flight (per m² of plan):", italic=True)
    cosA = math.cos(math.radians(alpha.v))
    ca = S("cos α", cosA, digits=4)
    hm = S("h", hcm / 100, "m")
    g1 = nt.calc("g_k,1", hm / ca * N(25) + S("h_st", hst.v / 100, "m") / 2 * N(25), "kN/m²",
                 "Waist slab (h/cos α) and steps (h_st/2)")
    g2 = nt.calc("g_k,2", N(0.02) / ca * N(18), "kN/m²", "Plaster")
    g3 = nt.given("g_k,3", 1.0, "kN/m²", "Finishing of the steps")
    gfl = nt.calc("g_k,fl", g1 + g2 + g3, "kN/m²")
    nt.p("Landing:", italic=True)
    gla = nt.calc("g_k,la", hm * N(25) + N(0.02) * N(18) + N(1.0), "kN/m²")
    qk = nt.given("q_k", inp.q_stair, "kN/m²", "Imposed load on stairs")
    pfl = nt.calc("p_fl", N(1.35) * gfl + N(1.5) * qk, "kN/m", "Design load on the flight")
    pla = nt.calc("p_la", N(1.35) * gla + N(1.5) * qk, "kN/m", "Design load on the landing")
    nt.h2("3. Static analysis")
    a_ = S("l_fl", lfl.v / 100, "m")
    b_ = S("l_la", lla.v / 100, "m")
    Lm = S("l_eff", L.v / 100, "m")
    RA = nt.calc("R_A", (pfl * a_ * (Lm - a_ / 2) + pla * b_**2 / 2) / Lm, "kN/m",
                 "Reaction at the lower support")
    RB = nt.calc("R_B", pfl * a_ + pla * b_ - RA, "kN/m")
    if RA.v / pfl.v <= a_.v:
        x0 = nt.calc("x_0", RA / pfl, "m", "Section with V = 0 (on the flight)")
        M = nt.calc("maxM_Ed", RA**2 / (2 * pfl), "kNm/m")
    else:
        x0 = nt.calc("x_0", Lm - RB / pla, "m", "Section with V = 0 (on the landing)")
        M = nt.calc("maxM_Ed", RB**2 / (2 * pla), "kNm/m")
    V = nt.calc("maxV_Ed", emax(RA, RB), "kN/m")
    if not dry(nt):
        X = np.linspace(0, Lm.v, 201)
        w = np.where(X <= a_.v, pfl.v, pla.v)
        Vx = RA.v - np.concatenate([[0], np.cumsum((w[1:] + w[:-1]) / 2 * np.diff(X))])
        Mx = np.concatenate([[0], np.cumsum((Vx[1:] + Vx[:-1]) / 2 * np.diff(X))])
        f = pl.simple_diagrams(X, Mx, Vx, "Internal forces in the stair slab", "V_diag", "kNm/m", "kN/m")
        nt.fig(f, "Bending moment and shear force in the stair", 13)
    nt.h2("4. Design of the section")
    mat = materials(nt, inp.fck, inp.fyk)
    d = nt.calc("d", S("h", hcm * 10, "mm") - S("c_nom", 25, "mm") - S("φ", 12, "mm") / 2, "mm")
    b = S("b", 1000, "mm")
    r = bending(nt, M, b, d, mat, "Bottom reinforcement of the flight", kind="slab",
                h=S("h", hcm * 10, "mm"))
    nt.h2("5. Shear")
    sh = shear_no_links(nt, V, b, d, r["rho_prov"], mat)
    nt.h2("6. Control of deflection")
    okd = deflection_ld(nt, L.v * 10, d, r["rho"], r["rho_prov"], r["As"], r["As_prov"], mat, 1.0,
                        gfl.v, qk.v, 1.35 * gfl.v, 1.5 * qk.v)
    nt.h2("7. Detailing")
    nt.bullet("Distribution bars Φ8/20 cm in every step and along the waist; top bars Φ8/20 cm at both "
              "ends (0.2·l), bottom bars bent at the kink between flight and landing are replaced by "
              "two crossing bars anchored with l_bd.")
    P_.res["V"] = dict(h=hcm, n=n, hst=hst.v, bst=bst.v, bars=r["bars"],
                       summary=[("Stairs", f"h = {fmt(hcm)} cm, {n} risers {fmt(hst.v)}/{fmt(bst.v)} cm, {r['bars']}")])
    return r["ok"] and sh["ok"] and okd


# ============================================================================
# VI  simply supported beam B21
# ============================================================================
def slab_to_beam(L_beam, l_other):
    """Load shape from a two-way slab onto a beam of length L_beam (45° lines).
    returns ('tri' or 'trap', ramp a, peak factor (× p))."""
    if L_beam <= l_other:
        return "tri", L_beam / 2, L_beam / 2
    return "trap", l_other / 2, l_other / 2


def section_VI(nt, P_, h_given=None):
    inp = P_.inp
    if h_given is None and not inp.B21_h:
        h = ceil_to(inp.b / 10, 5)
        for _ in range(8):
            if _section_VI(NullNote(), P_, h):
                break
            h += 5
        P_.log.append(f"B21: {fmt(inp.B21_b)}/{fmt(h)} cm")
    else:
        h = h_given or inp.B21_h
    return _section_VI(nt, P_, h)


def _section_VI(nt, P_, hcm):
    G, inp, pl = P_.G, P_.inp, P_.plot
    hf = P_.res.get("IV", {}).get("hf", 14)
    gk_slab = P_.res.get("IV", {}).get("gk", hf / 100 * 25 + 1.46)
    s1, s2, _ = G.no_office
    nt.h1("VI. Design of reinforced concrete simply supported beam")
    nt.p(f"Beam B21 on axis 5 between axes A and B (offices). It carries the slabs {s1} and {s2} "
         f"(two-way, h_f = {fmt(hf)} cm), its self-weight and a brick partition wall.")
    nt.h2("1. Static scheme and geometry")
    bw = nt.given("b_w", inp.B21_b, "cm")
    h = nt.given("h", hcm, "cm")
    hfS = nt.given("h_f", hf, "cm")
    lcl = nt.given("l_cl", inp.b - 25, "cm", "Clear span (columns 25 cm on axes A and B)")
    t = S("t", 25, "cm")
    leff = nt.calc("l_eff", lcl + 2 * emin(h / 2, t / 2), "cm", "a_i = min(h/2; t/2)")
    L = S("l_eff", leff.v / 100, "m")
    lo = inp.a - 25
    kind, ramp, peak = slab_to_beam(leff.v, lo + 25)
    nt.p(("The beam is on the short side of the slabs → triangular load (lines at 45°)."
          if kind == "tri" else "The beam is on the long side of the slabs → trapezoidal load."))
    nt.h2("2. Actions")
    nt.p("Characteristic permanent actions directly on the beam:", italic=True)
    hs = S("h_s", inp.hs / 100, "m")
    g1 = nt.calc("g_k,1", S("b_w", bw.v / 100, "m") * S("h", h.v / 100, "m") * N(25), "kN/m",
                 "Self-weight of the beam")
    g2 = nt.calc("g_k,2", S("t_w", inp.wall_t, "m") * (hs - S("h", h.v / 100, "m")) * S("γ_w", inp.wall_gamma),
                 "kN/m", "Brick wall on the beam")
    g3 = nt.calc("g_k,3", N(2) * N(0.02) * (hs - S("h_f", hf / 100, "m")) * N(18), "kN/m", "Plaster of the wall")
    Gk = nt.calc("ΣG_k", g1 + g2 + g3, "kN/m")
    nt.p(f"From the slabs {s1} and {s2} (peak value of the {'triangle' if kind == 'tri' else 'trapezoid'}):",
         italic=True)
    ls = S("l_load", 2 * peak / 100, "m")
    gfk = nt.calc("g_fk", S("g_k,slab", gk_slab, "kN/m²") * ls / 2, "kN/m")
    qfk = nt.calc("q_fk", S("q_k,slab", inp.q_office, "kN/m²") * ls / 2, "kN/m")
    nt.p("Design values:", italic=True)
    gd = nt.calc("g_d", N(1.35) * Gk, "kN/m")
    gfd = nt.calc("g_fd", N(1.35) * gfk, "kN/m")
    qfd = nt.calc("q_fd", N(1.5) * qfk, "kN/m")
    nt.h2("3. Static analysis")
    w0 = gfd + qfd
    if kind == "tri":
        M = nt.calc("maxM_Ed", gd * L**2 / 8 + N(2) * P(w0) * L**2 / 12, "kNm",
                    "UDL: g·l²/8 ; triangle (both sides): 2·w_0·l²/12")
        V = nt.calc("maxV_Ed", gd * L / 2 + N(2) * P(w0) * L / 4, "kN")
        Mqp = nt.calc("M_qp", Gk * L**2 / 8 + N(2) * P(gfk + N(0.3) * qfk) * L**2 / 12, "kNm",
                      "Quasi-permanent combination (ψ_2 = 0.3)")
        prof = lambda xi: 1 - abs(2 * xi - 1)
    else:
        a = S("a", ramp / 100, "m")
        M = nt.calc("maxM_Ed", gd * L**2 / 8 + N(2) * P(w0) * (N(3) * L**2 - N(4) * a**2) / 24, "kNm")
        V = nt.calc("maxV_Ed", gd * L / 2 + N(2) * P(w0) * (L - a) / 2, "kN")
        Mqp = nt.calc("M_qp", Gk * L**2 / 8 + N(2) * P(gfk + N(0.3) * qfk) * (N(3) * L**2 - N(4) * a**2) / 24,
                      "kNm")
        r_ = ramp / 100 / L.v
        prof = lambda xi: min(1.0, xi / r_, (1 - xi) / r_)
    cb = ContinuousBeam([L.v])
    res = cb.solve_case({0: lambda xi: gd.v + 2 * w0.v * prof(xi)})
    X, Mx, Vx = cb.diagrams(res)
    k4 = int(np.argmin(abs(X - L.v / 4)))
    Mq = nt.calc("M_Δx", S("M(l/4)", Mx[k4], "kNm"), "kNm", "Bending moment at x = l/4 (from the analysis)")
    Rg = nt.calc("R_g", gd * L / 2 + N(2) * gfd * L / 4 if kind == "tri" else gd * L / 2 + gfd * (L - S("a", ramp / 100)),
                 "kN", "Reaction from permanent actions (design) - for the columns")
    Rq = nt.calc("R_q", N(2) * qfd * L / 4 if kind == "tri" else qfd * (L - S("a", ramp / 100)), "kN",
                 "Reaction from variable actions (design)")
    if not dry(nt):
        f = pl.beam_scheme([L.v], ["pin", "pin"], "Beam B21 - static scheme",
                           loads=[(0, L.v, gd.v, gd.v, f"g_d = {fmt(gd.v)} kN/m", "#555555")],
                           sup_labels=["A", "B"], name="VI_scheme")
        nt.fig(f, "Static scheme of beam B21 (plus the triangular/trapezoidal load from the slabs)", 13)
        f = pl.simple_diagrams(X, Mx, Vx, "Beam B21 - M and V", "VI_diag")
        nt.fig(f, "Bending moment and shear force diagrams of beam B21", 13)
    nt.h2("4. Design of the bending reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    d = beam_eff_depth(nt, hcm)
    nt.p("Effective width of the flange (T-section, EC2 5.3.2.1):", italic=True)
    beff = beff_T(nt, bw.v * 10, L.v, [lo / 200, lo / 200])
    beffmm = S("b_eff", beff.v * 1000, "mm")
    hfmm = S("h_f", hf * 10, "mm")
    flange_check(nt, M, beffmm, hfmm, d, mat)
    r = bending(nt, M, beffmm, d, mat, "Mid-span section", bt=S("b_w", bw.v * 10, "mm"), kind="beam")
    nt.h2("5. Design for shear")
    sh = shear_links(nt, V, S("b_w", bw.v * 10, "mm"), d, r["rho_prov"] * beffmm.v / (bw.v * 10), mat)
    nt.p("Shear between the web and the flange (EC2 6.2.4):", bold=True)
    flange_shear(nt, Mq, S("Δx", L.v * 250, "mm"), d, hfmm, beffmm, S("b_w", bw.v * 10, "mm"), mat)
    nt.h2("6. Deflection of the beam (EC2 7.4.3)")
    okf = beam_deflection(nt, mat, bw.v * 10, hcm * 10, beff.v * 1000, hf * 10, d.v, r["As_prov"],
                          Mqp, L.v * 1000)
    P_.res["VI"] = dict(h=hcm, Rg=Rg.v, Rq=Rq.v, bars=r["bars"], links=sh["links"],
                        summary=[("Beam B21", f"{fmt(inp.B21_b)}/{fmt(hcm)} cm, {r['bars']}, links {sh['links']}")])
    return r["ok"] and sh["ok"] and okf


def beam_deflection(nt, mat, bw, h, beff, hf, d, As, Mqp, L, phi_cr=2.0):
    Ecm = mat["E_cm"]
    Ecm_ = nt.given("E_cm", Ecm, "GPa")
    Ece = nt.calc("E_c,eff", Ecm_ / (1 + S("φ(∞,t0)", phi_cr)), "GPa", "Effective modulus (creep)")
    ae = nt.calc("α_e", S("E_s", 200, "GPa") / Ece, "")
    a = ae.v
    # uncracked
    A1 = bw * h + (beff - bw) * hf + a * As
    xI = (bw * h * h / 2 + (beff - bw) * hf * hf / 2 + a * As * d) / A1
    II = (bw * h**3 / 12 + bw * h * (h / 2 - xI)**2 + (beff - bw) * hf**3 / 12 +
          (beff - bw) * hf * (xI - hf / 2)**2 + a * As * (d - xI)**2)
    nt.p("Uncracked section (state I):", italic=True)
    nt.given("A_I", A1, "mm²")
    nt.given("x_I", xI, "mm")
    nt.given("I_I", II, "mm⁴")
    SI = As * (d - xI)
    Mcr = nt.calc("M_cr", mat["f_ctm"] * S("I_I", II, "mm⁴") / (S("h", h, "mm") - S("x_I", xI, "mm")) / N(1e6, "10⁶"),
                  "kNm", "Cracking moment")
    # cracked: solve beff x^2/2 = a As (d-x) (flange) else T
    xII = (-a * As + math.sqrt((a * As)**2 + 2 * beff * a * As * d)) / beff
    if xII > hf:
        A_ = bw / 2
        B_ = (beff - bw) * hf + a * As
        C_ = -((beff - bw) * hf * hf / 2 + a * As * d)
        xII = (-B_ + math.sqrt(B_ * B_ - 4 * A_ * C_)) / (2 * A_)
        III = (bw * xII**3 / 3 + (beff - bw) * hf**3 / 12 + (beff - bw) * hf * (xII - hf / 2)**2
               + a * As * (d - xII)**2)
    else:
        III = beff * xII**3 / 3 + a * As * (d - xII)**2
    nt.p("Cracked section (state II):", italic=True)
    nt.given("x_II", xII, "mm")
    nt.given("I_II", III, "mm⁴")
    SII = As * (d - xII)
    if Mqp.v > Mcr.v:
        zeta = nt.calc("ζ", 1 - S("β", 0.5) * (Mcr / Mqp)**2, "", "Distribution coefficient (EC2 7.19)")
    else:
        zeta = nt.given("ζ", 0.0, "", "M_qp < M_cr - the section is uncracked")
    r1 = nt.calc("1/r_m", Mqp * N(1e6, "10⁶") / (Ece * N(1000)) * (zeta / S("I_II", III) + (1 - zeta) / S("I_I", II)),
                 "1/mm", "Curvature from the quasi-permanent moment")
    h0 = 2 * (bw * h + (beff - bw) * hf) / (2 * beff + 2 * (h - hf))
    kh = np.interp(h0, [100, 200, 300, 500], [1.0, 0.85, 0.75, 0.70])
    ecd = nt.calc("ε_cd", S("k_h", kh, digits=3) * S("ε_cd,0", 0.00045, digits=5), "", digits=6)
    eca = nt.calc("ε_ca", N(2.5) * (mat["f_ck"] - 10) * N(1e-6, "10⁻⁶"), "", digits=6)
    ecs = nt.calc("ε_cs", ecd + eca, "", "Total shrinkage strain", digits=6)
    rcs = nt.calc("1/r_cs", ecs * ae * (zeta * S("S_II", SII) / S("I_II", III) + (1 - zeta) * S("S_I", SI) / S("I_I", II)),
                  "1/mm", "Curvature from shrinkage (EC2 7.21)")
    f = nt.calc("f", N(5 / 48, "5/48") * (r1 + rcs) * S("l_eff", L, "mm")**2, "mm", "Deflection (k = 5/48)")
    lim = nt.calc("f_lim", S("l_eff", L, "mm") / 250, "mm")
    return nt.compare(f, "≤", lim, ok_text="The deflection is acceptable",
                      ng_text="The deflection is too large - increase the depth of the beam")


# ============================================================================
# VII  beam subjected to torsion (supports the canopy slab 7)
# ============================================================================
def section_VII(nt, P_, h_given=None):
    inp = P_.inp
    h = h_given or inp.BT_h
    for _ in range(8):
        if _section_VII(NullNote(), P_, h):
            break
        h += 5
    if h != inp.BT_h:
        P_.log.append(f"torsion beam: {fmt(inp.BT_b)}/{fmt(h)} cm")
    return _section_VII(nt, P_, h)


def _section_VII(nt, P_, hcm):
    G, inp, pl = P_.G, P_.inp, P_.plot
    s7 = G.no_stairs[0]
    nt.h1("VII. Design of reinforced concrete beam for torsion")
    nt.p(f"Beam on axis E (Д) between axes 3 and 4 carrying the cantilever canopy slab {s7} "
         f"(length 1.25·d = {fmt(1.25 * inp.d)} cm). Bending: simply supported beam. Torsion: both ends "
         f"fixed against rotation (walls on axes 3 and 4).")
    nt.h2("1. Static scheme")
    bw = nt.given("b", inp.BT_b, "cm")
    h = nt.given("h", hcm, "cm")
    lcl = nt.given("l_cl", 2 * inp.d + 20, "cm", "Clear span between the walls (2d + 45 − 25)")
    t = S("t", 25, "cm")
    lb = nt.calc("l_eff", lcl + 2 * emin(h / 2, t / 2), "cm", "Effective span for bending")
    nt.p(f"Effective span for torsion: l_T = l_cl = {fmt(lcl.v)} cm")
    hfc = S("h_f7", inp.hf_canopy / 100, "m")
    lc = nt.calc("l_c", S("1.25·d", 1.25 * inp.d / 100, "m") + S("b", bw.v / 200, "m"), "m",
                 "Length of the cantilever measured to the axis of the beam")
    nt.h2("2. Actions")
    nt.p(f"Canopy slab {s7} - characteristic permanent actions:", italic=True)
    g7 = nt.calc("Σg_k7", hfc * N(25) + N(0.02) * N(18) + N(0.04) * N(20) + N(0.20), "kN/m²",
                 "slab + plaster + screed 4 cm + insulation")
    sk = nt.given("s_k", inp.s_k, "kN/m²", "Snow")
    Mcg = nt.calc("M_cg", g7 * lc**2 / 2, "kNm/m", "Torsional moment per metre (permanent)")
    Rcg = nt.calc("R_cg", g7 * lc, "kN/m")
    Msk = nt.calc("M_sk", sk * lc**2 / 2, "kNm/m")
    Rsk = nt.calc("R_sk", sk * lc, "kN/m")
    gb = nt.calc("g_k,b", S("b", bw.v / 100, "m") * S("h", h.v / 100, "m") * N(25) +
                 N(0.02) * N(18) * (N(2) * S("h", h.v / 100, "m") + S("b", bw.v / 100, "m")), "kN/m",
                 "Self-weight and plaster of the beam")
    gd = nt.calc("g_d", N(1.35) * (Rcg + gb), "kN/m")
    qd = nt.calc("q_d", N(1.5) * Rsk, "kN/m")
    pd = nt.calc("p_d", gd + qd, "kN/m")
    td = nt.calc("t_d", N(1.35) * Mcg + N(1.5) * Msk, "kNm/m", "Distributed torsional moment")
    nt.h2("3. Static analysis")
    L = S("l_eff", lb.v / 100, "m")
    LT = S("l_T", lcl.v / 100, "m")
    M = nt.calc("M_Ed", pd * L**2 / 8, "kNm")
    V = nt.calc("V_Ed", pd * L / 2, "kN")
    T = nt.calc("T_Ed", td * LT / 2, "kNm", "Torsion - beam fixed at both ends")
    if not dry(nt):
        X = np.linspace(0, LT.v, 81)
        f = pl.simple_diagrams(X, pd.v * X * (LT.v - X) / 2, td.v * (LT.v / 2 - X),
                               "Bending moment (top) and torsional moment T(x) (bottom)", "VII_diag",
                               "kNm", "kNm")
        nt.fig(f, "Internal forces of the beam subjected to torsion", 13)
    nt.h2("4. Design of the cross-section for torsion (EC2 6.3)")
    mat = materials(nt, inp.fck, inp.fyk)
    bmm, hmm = bw.v * 10, h.v * 10
    A = nt.calc("A", S("b", bmm, "mm") * S("h", hmm, "mm"), "mm²")
    u = nt.calc("u", N(2) * (S("b", bmm, "mm") + S("h", hmm, "mm")), "mm")
    tef = nt.calc("t_ef", A / u, "mm", "Effective wall thickness")
    Ak = nt.calc("A_k", (S("b", bmm) - tef) * (S("h", hmm) - tef), "mm²")
    uk = nt.calc("u_k", N(2) * ((S("b", bmm) - tef) + (S("h", hmm) - tef)), "mm")
    d = beam_eff_depth(nt, hcm, phi=16)
    nu = nt.calc("ν", N(0.6) * (1 - mat["f_ck"] / N(250)), "")
    th = 45.0
    nt.p("Angle of the compression struts θ = 45° (cot θ = 1).")
    TRmax = nt.calc("T_Rd,max", N(2) * nu * mat["f_cd"] * Ak * tef * N(0.5) / N(1e6, "10⁶"), "kNm",
                    "T_Rd,max = 2·ν·α_cw·f_cd·A_k·t_ef·sinθ·cosθ")
    VRmax = nt.calc("V_Rd,max", S("b", bmm) * N(0.9) * d * nu * mat["f_cd"] / N(2) / N(1000, "10³"), "kN",
                    "V_Rd,max = α_cw·b·z·ν·f_cd/(cotθ + tanθ)")
    inter = nt.calc("η", T / TRmax + V / VRmax, "", "Interaction torsion + shear (EC2 6.29)")
    ok1 = nt.compare(inter, "≤", S("1", 1.0), ok_text="The concrete section is adequate",
                     ng_text="Increase the section")
    nt.h2("5. Reinforcement")
    z = 0.9 * d.v
    aV = nt.calc("A_sw/s,V", V * N(1000) / (S("z", z, "mm") * mat["f_yd"] * N(1)), "mm²/mm",
                 "Links for shear (both legs)")
    aT = nt.calc("A_sw/s,T", T * N(1e6, "10⁶") / (N(2) * Ak * mat["f_yd"] * N(1)), "mm²/mm",
                 "Links for torsion (one leg)")
    a1 = nt.calc("A_sw1/s", aV / 2 + aT, "mm²/mm", "Total, one leg")
    rmin = 0.08 * math.sqrt(inp.fck) / inp.fyk * bmm / 2
    need = max(a1.v, rmin)
    phi_w = 8 if need * 100 <= BAR_AREA[8] else 10
    s = min(math.floor(BAR_AREA[phi_w] / need / 10) * 10, math.floor(min(uk.v / 8, 0.75 * d.v, bmm) / 10) * 10)
    nt.calc("s_max", emin(uk / 8, N(0.75) * d, S("b", bmm)), "mm", "Maximum spacing of torsion links")
    nt.p(f"Adopted closed links: Φ{phi_w}/{fmt(s / 10)} cm", bold=True)
    AsT = nt.calc("ΣA_sl", T * N(1e6, "10⁶") * uk / (N(2) * Ak * mat["f_yd"]), "mm²",
                  "Longitudinal reinforcement for torsion (cot θ = 1)")
    bk = bmm - tef.v
    hk = hmm - tef.v
    nt.p("Bending reinforcement (rectangular section):", bold=True)
    r = bending(nt, M, S("b", bmm, "mm"), d, mat, "", kind="beam")
    bot = nt.calc("A_s,bot", S("A_s", r["As"]) + AsT * S("b_k", bk) / uk, "mm²", "Bottom face: bending + torsion share")
    top = nt.calc("A_s,top", AsT * S("b_k", bk) / uk, "mm²", "Top face")
    side = nt.calc("A_s,side", AsT * S("h_k", hk) / uk, "mm²", "Each side face")
    tb, Ab, _, _ = beam_bars(bot.v, bmm)
    tt, At, _, _ = beam_bars(max(top.v, 2 * BAR_AREA[12]), bmm)
    nt.p(f"Adopted: bottom {tb} ({fmt(Ab)} mm²), top {tt} ({fmt(At)} mm²), "
         f"side bars {max(2, math.ceil(side.v / BAR_AREA[12]))}Φ12 on each face.", bold=True)
    nt.h2(f"6. Canopy slab {s7} - top reinforcement at the root of the cantilever")
    Mc = nt.calc(f"M_Ed,{s7}", N(1.35) * Mcg + N(1.5) * Msk, "kNm/m", "Design moment at the root (per metre)")
    hc = S("h", inp.hf_canopy * 10, "mm")
    dc = nt.calc(f"d_{s7}", hc - S("c_nom", 25, "mm") - S("φ", 10, "mm") / 2, "mm")
    rc = bending(nt, Mc, S("b", 1000, "mm"), dc, mat, "", kind="slab", h=hc, tag=str(s7))
    P_.res["VII"] = dict(h=hcm, canopy=dict(design=rc, lc=lc.v, hf=inp.hf_canopy),
                         summary=[("Torsion beam (axis E, 3-4)",
                                   f"{fmt(inp.BT_b)}/{fmt(hcm)} cm, bottom {tb}, top {tt}, links Φ{phi_w}/{fmt(s / 10)}")])
    return ok1 and r["ok"]


# ============================================================================
# VIII  continuous beam B5
# ============================================================================
def section_VIII(nt, P_, h_given=None):
    inp = P_.inp
    h = h_given or inp.B5_h or ceil_to(inp.a / 14, 5)
    if not (h_given or inp.B5_h):
        for _ in range(8):
            if _section_VIII(NullNote(), P_, h):
                break
            h += 5
        P_.log.append(f"B5: {fmt(inp.B5_b)}/{fmt(h)} cm")
    return _section_VIII(nt, P_, h)


def _section_VIII(nt, P_, hcm):
    G, inp, pl = P_.G, P_.inp, P_.plot
    hf = P_.res.get("II", {}).get("hf", 12)
    gks = P_.res.get("II", {}).get("gk", hf / 100 * 25 + 1.46)
    nt.h1("VIII. Design of reinforced concrete continuous beams")
    nt.p(f"Secondary beam B5 (and B6-B9) of the exhibition hall: continuous beam over two spans "
         f"(axes 1-2-3), supported on the walls on axes 1 and 3 and on the frame beam B15 (axis 2). "
         f"Load width = spacing of the beams = {fmt(G.s_h)} cm.")
    nt.h2("1. Static scheme")
    bw = nt.given("b_w", inp.B5_b, "cm")
    h = nt.given("h", hcm, "cm")
    t1 = S("t_1", 25, "cm")
    t2 = S("t_2", inp.B15_b, "cm")
    lcl = nt.given("l_cl", inp.a - 12.5 - inp.B15_b / 2, "cm", "Clear span")
    leff = nt.calc("l_eff", lcl + emin(h / 2, t1 / 2) + t2 / 2, "cm")
    L = leff.v / 100
    nt.h2("2. Actions")
    s = S("s", G.s_h / 100, "m")
    hm, hfm, bm = S("h", hcm / 100, "m"), S("h_f", hf / 100, "m"), S("b_w", inp.B5_b / 100, "m")
    g1 = nt.calc("g_k,1", bm * (hm - hfm) * N(25), "kN/m", "Web of the beam")
    g2 = nt.calc("g_k,2", N(0.02) * N(18) * (N(2) * (hm - hfm) + bm), "kN/m", "Plaster")
    g3 = nt.calc("g_k,3", S("g_k,slab", gks, "kN/m²") * s, "kN/m", "From the slab (load width s)")
    gk = nt.calc("Σg_k", g1 + g2 + g3, "kN/m")
    qk = nt.calc("q_k", S("q_k1", inp.qk1, "kN/m²") * s, "kN/m", "Variable action from the slab")
    gd = nt.calc("g_d", N(1.35) * gk, "kN/m")
    qd = nt.calc("q_d", N(1.5) * qk, "kN/m")
    nt.h2("3. Static analysis")
    nt.p("Continuous beam with two equal spans; permanent load on both spans, variable load in the "
         "most unfavourable arrangement (stiffness method, envelopes).")
    cb = ContinuousBeam([L, L])
    env = cb.envelope({0: gd.v, 1: gd.v}, {0: qd.v, 1: qd.v})
    X = env["X"]
    m1 = (X > 0) & (X < L)
    k1 = int(np.argmax(np.where(m1, env["Mmax"], -1e18)))
    kB = int(np.argmin(abs(X - L)))
    Ls = S("l_eff", L, "m")
    ag, aq = env["Mg"][k1] / (gd.v * L * L), (env["Mmax"][k1] - env["Mg"][k1]) / (qd.v * L * L)
    M1 = nt.calc("maxM_Ed,1", (S("α_g", ag, digits=4) * gd + S("α_q", aq, digits=4) * qd) * Ls**2, "kNm",
                 "Span moment (q on one span)")
    bg, bq = env["Mg"][kB] / (gd.v * L * L), (env["Mmin"][kB] - env["Mg"][kB]) / (qd.v * L * L)
    MB = nt.calc("minM_B", -((S("α_g", -bg, digits=4) * gd + S("α_q", -bq, digits=4) * qd) * Ls**2), "kNm",
                 "Moment at the middle support (q on both spans)")
    near = abs(X - L) < 1e-3
    VB = max(abs(env["Vmax"][near]).max(), abs(env["Vmin"][near]).max())
    V = nt.calc("maxV_Ed", N(0.625) * (gd + qd) * Ls, "kN", "Shear at the middle support (5/8·p·l)")
    VA = nt.calc("V_Ed,A", S("R_A,max", env["Rmax"][0], "kN"), "kN", "Maximum reaction at the end support")
    RB = nt.calc("maxR_B", N(1.25) * (gd + qd) * Ls, "kN", "Reaction on the frame beam B15 (10/8·p·l)")
    RBg = nt.calc("R_B,gk", N(1.25) * gk * Ls, "kN", "Characteristic reaction - permanent")
    RBq = nt.calc("R_B,qk", N(1.25) * qk * Ls, "kN", "Characteristic reaction - variable")
    k4 = int(np.argmin(abs(X - L / 4)))
    if not dry(nt):
        f = pl.beam_scheme([L, L], ["pin", "pin", "pin"], "Beam B5 - static scheme",
                           loads=[(0, 2 * L, gd.v, gd.v, f"g_d = {fmt(gd.v)} kN/m", "#555555"),
                                  (0, 2 * L, qd.v, qd.v, f"q_d = {fmt(qd.v)} kN/m", "#c0392b")],
                           sup_labels=["1", "2", "3"], name="VIII_scheme")
        nt.fig(f, "Static scheme of the continuous beam B5", 14)
        f = pl.envelope(X, env["Mmax"], env["Mmin"], env["Vmax"], env["Vmin"], cb.x_start,
                        "Beam B5 - envelopes", "VIII_env", extra_M=env["Mall"])
        nt.fig(f, "Envelopes of M and V of beam B5", 15)
    nt.h2("4. Design of the bending reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    d = beam_eff_depth(nt, hcm)
    nt.p("Spans - T-section, effective width (l_0 = 0.85·l_eff):", italic=True)
    bi = (G.s_h - 25) / 200
    beff = beff_T(nt, inp.B5_b * 10, 0.85 * L, [bi, bi])
    beffmm = S("b_eff", beff.v * 1000, "mm")
    hfmm = S("h_f", hf * 10, "mm")
    bwmm = S("b_w", inp.B5_b * 10, "mm")
    flange_check(nt, M1, beffmm, hfmm, d, mat)
    r1 = bending(nt, M1, beffmm, d, mat, "Span 1-2 and 2-3 (bottom)", bt=bwmm, kind="beam", tag="1")
    nt.p("Middle support - rectangular section b_w (flange in tension), moment at the face:", bold=True)
    dM = nt.calc("ΔM", S("V_Ed", VB, "kN") * t2 / 200, "kNm", "ΔM = V_Ed·t_2/2")
    MBf = nt.calc("M_Ed,B", eabs(MB) - dM, "kNm")
    rB = bending(nt, MBf, bwmm, d, mat, "", kind="beam", tag="B")
    nt.p(f"End supports: A_s3 ≥ 0.25·A_s,span = {fmt(0.25 * r1['As_prov'])} mm² → 2Φ14; "
         f"assembly bars in the span 2Φ10.", italic=True)
    nt.h2("5. Design for shear")
    sh = shear_links(nt, V, bwmm, d, rB["rho_prov"], mat)
    nt.p("Supporting (hanger) reinforcement in the intersection with the frame beam B15:", bold=True)
    Asw = nt.calc("A_sw,hang", RB * N(1000) / mat["f_yd"], "mm²", "The whole reaction is hung up by links")
    nlinks = math.ceil(Asw.v / (2 * BAR_AREA[8]))
    nt.p(f"Required {nlinks} additional two-leg links Φ8 in the intersection zone (each side of B5).",
         bold=True)
    nt.p("Shear between the web and the flange:", bold=True)
    flange_shear(nt, S("M_Δx", env["Mmax"][k4], "kNm"), S("Δx", L * 250, "mm"), d, hfmm, beffmm, bwmm, mat)
    nt.h2("6. Control of deflection")
    nt.p("End span of a continuous beam: K = 1.3 (flanged section b_eff/b_w > 3 → × 0.8)")
    Kf = 1.3 * (0.8 if beff.v * 1000 / (inp.B5_b * 10) > 3 else 1.0)
    okd = deflection_ld(nt, L * 1000, d, r1["As"] / (inp.B5_b * 10 * d.v), r1["As_prov"] / (inp.B5_b * 10 * d.v),
                        r1["As"], r1["As_prov"], mat, Kf, gk.v, qk.v, gd.v, qd.v)
    P_.res["VIII"] = dict(h=hcm, RBg=RBg.v, RBq=RBq.v, RB=RB.v, gk=gk.v, qk=qk.v, L=L,
                          summary=[("Beam B5-B9", f"{fmt(inp.B5_b)}/{fmt(hcm)} cm, span {r1['bars']}, "
                                    f"support {rB['bars']}, links {sh['links']}")])
    return r1["ok"] and rB["ok"] and sh["ok"] and okd
