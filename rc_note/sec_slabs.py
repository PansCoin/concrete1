# -*- coding: utf-8 -*-
"""Sections I - IV : slabs."""
from __future__ import annotations

import math

import numpy as np

from .engine import S, N, P, sqrt, emin, emax, eabs, fmt
from .design import (NullNote, materials, bending, shear_no_links, deflection_ld,
                     slab_bars, BAR_AREA, MESHES, MESH_SHEET, mesh_area, mesh_for)
from .project import slab_actions, HF_TIP
from .statics import ContinuousBeam, plate_coeffs


def dry(nt):
    return isinstance(nt, NullNote)


def eff_depth(nt, hf_cm, c_nom=25, phi=10, name="d"):
    nt.p("Effective depth of the cross-section:", italic=True)
    h = S("h_f", hf_cm * 10, "mm")
    return nt.calc(name, h - S("c_nom", c_nom, "mm") - S("φ", phi, "mm") / 2, "mm",
                   f"c_nom = {c_nom} mm (XC1, 50 years), assumed bar Φ{phi}")


def detailing_one_way(nt, As_main, hf_cm, s_main):
    nt.p("Detailing of the reinforcement (EC2 9.3.1):", bold=True)
    As_d = max(0.2 * As_main, 3 * BAR_AREA[8])
    txt, Asd, phi, s = slab_bars(As_d, hf_cm * 10, s_max=min(3 * hf_cm * 10, 400), dias=(6, 8, 10))
    nt.bullet(f"Distribution (secondary) reinforcement: A_s,dist ≥ max(0.20·A_s; 3Φ8/m) = "
              f"{fmt(As_d)} mm²/m → {txt}")
    nt.bullet(f"Spacing of main bars ≤ min(2·h_f; 250 mm) = {fmt(min(2 * hf_cm * 10, 250))} mm "
              f"(adopted {s_main} mm); distribution bars ≤ min(3·h_f; 400 mm).")
    nt.bullet("Top reinforcement at end supports (monolithic connection): A_s3 ≥ max(0.25·A_s,span; "
              "A_s,min; 5Φ8/m), length 0.2·l_min from the face of the support + l_bd.")
    nt.bullet("Bottom bars are anchored at end supports with l_bd and lapped over interior supports; "
              "top bars over interior supports extend 0.3·l_min beyond the face of the support.")
    return dict(phi=phi, s=s, As=Asd)


# ============================================================================
# I  simply supported slab
# ============================================================================
def section_I(nt, P_, hf):
    G, inp, pl = P_.G, P_.inp, P_.plot
    nt.h1("I. Design of reinforced concrete single-span simply supported slab")
    nt.p(f"Slab {G.no_corr} - corridor between axes B and D (Б-Г) and axes 4-7. The slab is "
         f"supported on the beams on axes B and D and spans in the short direction.")
    nt.h2("1. Static scheme")
    lmax = nt.given("l_max,cl", G.X["7"] - G.X["4"] - 25, "cm", "Clear span in the long direction")
    lmin = nt.given("l_min,cl", inp.c - 25, "cm", "Clear span in the short direction")
    lam = nt.calc("λ", lmax / lmin, "", "Ratio of the spans")
    nt.compare(lam, ">", S("2", 2.0), ok_text="Slab spanning in one direction (simply supported strip)")
    hfS = nt.given("h_f", hf, "cm", "Thickness of the slab")
    t = S("t", 25, "cm")
    a1 = nt.calc("a_1", emin(hfS / 2, t / 2), "cm", "EC2 5.3.2.2(1): a_i = min(h/2; t/2)")
    leff = nt.calc("l_eff", lmin + 2 * a1, "cm", "Effective span l_eff = l_n + a_1 + a_2")
    l = S("l_eff", leff.v / 100, "m")
    nt.h2("2. Actions")
    L = slab_actions(nt, hf, inp.q_office, "Imposed load - corridor (category B/C)")
    if not dry(nt):
        f = pl.beam_scheme([l.v], ["pin", "pin"], "Static scheme - strip 1 m wide",
                           loads=[(0, l.v, L["p"].v, L["p"].v, f"p_d = {fmt(L['p'].v)} kN/m", "#1f5fa8")],
                           sup_labels=["B", "D"], name="I_scheme")
        nt.fig(f, "Static scheme of the simply supported slab", 13)
    nt.h2("3. Static analysis")
    M = nt.calc("M_Ed", L["p"] * l**2 / 8, "kNm/m", "Maximum bending moment (mid-span)")
    V = nt.calc("V_Ed", L["p"] * l / 2, "kN/m", "Maximum shear force (supports)")
    if not dry(nt):
        X = np.linspace(0, l.v, 81)
        f = pl.simple_diagrams(X, L["p"].v * X * (l.v - X) / 2, L["p"].v * (l.v / 2 - X),
                               "Bending moment and shear force diagrams", "I_diag", "kNm/m", "kN/m")
        nt.fig(f, "Internal forces in the simply supported slab", 13)
    nt.h2("4. Design of the bending reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    d = eff_depth(nt, hf)
    b = S("b", 1000, "mm")
    r = bending(nt, M, b, d, mat, "Mid-span section (b = 1000 mm, per metre)", kind="slab",
                h=S("h", hf * 10, "mm"))
    nt.h2("5. Design for shear")
    sh = shear_no_links(nt, V, b, d, r["rho_prov"], mat)
    nt.h2("6. Control of deflection (EC2 7.4.2)")
    nt.p("Simply supported slab: K = 1.0")
    okd = deflection_ld(nt, leff.v * 10, d, r["rho"], r["rho_prov"], r["As"], r["As_prov"], mat, 1.0,
                        L["gk"].v, L["qk"].v, L["gd"].v, L["qd"].v)
    nt.h2("7. Detailing")
    dist = detailing_one_way(nt, r["As_prov"], hf, r["s"])
    P_.res["I"] = dict(hf=hf, bars=r["bars"], M=M.v, V=V.v, gk=L["gk"].v, slab=G.no_corr,
                       design=dict(span=r, dist=dist),
                       summary=[(f"Slab {G.no_corr} (corridor, simply supported)", f"h_f = {fmt(hf)} cm, {r['bars']}")])
    return r["ok"] and sh["ok"] and okd


# ============================================================================
# II  continuous one-way slab, elastic analysis
# ============================================================================
def section_II(nt, P_, hf):
    G, inp, pl = P_.G, P_.inp, P_.plot
    nh = G.n_half
    n = 2 * nh
    nt.h1("II. Design of reinforced concrete continuous slab spanning in one direction - "
          "elastic analysis")
    nt.p(f"Slabs {G.no_hall} - exhibition hall, axes 1-3 / A-E. The slab is continuous over the "
         f"secondary beams B5... ({n - 1} interior supports at a spacing of {fmt(G.s_h)} cm) and spans "
         f"from axis A to axis E (Д) in {n} spans.")
    nt.h2("1. Static scheme")
    lmax = nt.given("l_max,cl", inp.a - 27.5, "cm",
                    "Clear span in the long direction (wall 25 cm on axis 1, beam 30 cm on axis 2)")
    lmin = nt.given("l_min,cl", G.s_h - 25, "cm", "Clear span between the secondary beams (b_w = 25 cm)")
    lam = nt.calc("λ", lmax / lmin, "")
    nt.compare(lam, ">", S("2", 2.0), ok_text="Slab spanning in one direction - continuous strip 1 m wide")
    hfS = nt.given("h_f", hf, "cm", "Thickness of the slab")
    t = S("t", 25, "cm")
    l1 = nt.calc("l_eff,1", lmin + emin(hfS / 2, t / 2) + t / 2, "cm",
                 "End span: l_eff,1 = l_n + min(h_f/2; t/2) + t/2")
    l2 = nt.calc("l_eff,2", lmin + t, "cm", "Interior spans: l_eff,2 = l_n + t")
    spans = [l1.v / 100] + [l2.v / 100] * (n - 2) + [l1.v / 100]
    nt.h2("2. Actions")
    L = slab_actions(nt, hf, inp.qk1, "Imposed load - exhibition hall q_k1 (assignment)")
    nt.h2("3. Static analysis - bending moments and shear forces")
    nt.p(f"The strip is analysed as a continuous beam with {n} spans (stiffness method). The "
         "permanent load acts on all spans; the variable load is placed span by span in the most "
         "unfavourable arrangement for every section (pattern loading). The envelope is obtained by "
         "superposition, the results are written in the familiar coefficient form "
         "M = (α_g·g_d + α_q·q_d)·l².")
    cb = ContinuousBeam(spans)
    env = cb.envelope({i: L["gd"].v for i in range(n)}, {i: L["qd"].v for i in range(n)})
    X = env["X"]
    xs = cb.x_start
    gd, qd = L["gd"], L["qd"]
    sup_names = [chr(ord("A") + i) for i in range(n + 1)]
    if not dry(nt):
        f = pl.beam_scheme(spans, ["pin"] * (n + 1), "Static scheme - continuous strip 1 m wide",
                           loads=[(0, sum(spans), gd.v, gd.v, f"g_d = {fmt(gd.v)} kN/m", "#555555"),
                                  (0, sum(spans), qd.v, qd.v, f"q_d = {fmt(qd.v)} kN/m (pattern)", "#c0392b")],
                           sup_labels=sup_names, name="II_scheme")
        nt.fig(f, "Static scheme of the continuous slab", 16)
    rows = []
    moments = []
    for i in range(nh):
        m = (X > xs[i] + 1e-6) & (X < xs[i + 1] - 1e-6)
        k = int(np.argmax(np.where(m, env["Mmax"], -1e18)))
        li = spans[i]
        ag = env["Mg"][k] / (gd.v * li**2)
        aq = (env["Mmax"][k] - env["Mg"][k]) / (qd.v * li**2)
        lS = S(f"l_eff,{1 if i == 0 else 2}", li, "m")
        Mi = nt.calc(f"maxM_Ed,{i + 1}", (S("α_g", ag, digits=4) * gd + S("α_q", aq, digits=4) * qd) * lS**2,
                     "kNm/m", f"Span {i + 1} (x = {fmt(X[k])} m)")
        rows.append((f"Span {i + 1}", fmt(ag), fmt(aq), fmt(Mi.v)))
        moments.append(("span", i + 1, Mi))
    Vsup = []
    for j in range(1, nh + 1):
        k = int(np.argmin(abs(X - xs[j])))
        lj = max(spans[j - 1], spans[j])
        ag = env["Mg"][k] / (gd.v * lj**2)
        aq = (env["Mmin"][k] - env["Mg"][k]) / (qd.v * lj**2)
        lS = S("l_eff", lj, "m")
        Mj = nt.calc(f"minM_{sup_names[j]}", -((S("α_g", -ag, digits=4) * gd + S("α_q", -aq, digits=4) * qd) * lS**2),
                     "kNm/m", f"Support {sup_names[j]}")
        rows.append((f"Support {sup_names[j]}", fmt(ag), fmt(aq), fmt(Mj.v)))
        near = abs(X - xs[j]) < 1e-3
        Vj = max(abs(env["Vmax"][near]).max(), abs(env["Vmin"][near]).max())
        Vsup.append(Vj)
        moments.append(("sup", sup_names[j], Mj))
    # shear: maximum at first interior support
    near = abs(X - xs[1]) < 1e-3
    kv = int(np.argmin(np.where(near, env["Vmin"], 1e18)))
    bg = abs(env["Vg"][kv]) / (gd.v * spans[0])
    bq = (abs(env["Vmin"][kv]) - abs(env["Vg"][kv])) / (qd.v * spans[0])
    Vmax = nt.calc("maxV_Ed", (S("β_g", bg, digits=4) * gd + S("β_q", bq, digits=4) * qd) * S("l_eff,1", spans[0], "m"),
                   "kN/m", "Maximum shear force (left of support B)")
    rows.append(("Shear at B (left)", fmt(bg), fmt(bq), fmt(Vmax.v)))
    nt.table(["Section", "α_g (β_g)", "α_q (β_q)", "Design value [kNm/m, kN/m]"], rows,
             caption="Coefficients and design values from the elastic analysis")
    if not dry(nt):
        f = pl.envelope(X, env["Mmax"], env["Mmin"], env["Vmax"], env["Vmin"], xs,
                        "Envelope of bending moments and shear forces (1 m strip)", "II_env",
                        "kNm/m", "kN/m", extra_M=env["Mall"])
        nt.fig(f, "Envelopes of M and V for the continuous slab (pattern loading)", 16.5)
    nt.h2("4. Design of the bending reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    d = eff_depth(nt, hf)
    b = S("b", 1000, "mm")
    ok = True
    res = {}
    for kind, idx, M in moments:
        if kind == "span":
            r = bending(nt, M, b, d, mat, f"Span {idx} (bottom reinforcement)", kind="slab",
                        h=S("h", hf * 10, "mm"), tag=str(idx))
        else:
            nt.p(f"Support {idx} (top reinforcement) - moment at the face of the support:", bold=True)
            j = sup_names.index(idx)
            Vs = S(f"V_Ed,{idx}", Vsup[j - 1], "kN/m")
            dM = nt.calc("ΔM_Ed", Vs * S("t", 0.25, "m") / 2, "kNm/m", "ΔM = V_Ed·t/2")
            lj = max(spans[j - 1], spans[j])
            Mmin65 = 0.65 * L["p"].v * lj**2 / 12
            Mf = nt.calc(f"M_Ed,{idx}", emax(eabs(M) - dM, S("0.65·p·l²/12", Mmin65)), "kNm/m",
                         "Not less than 65 % of the fixed-end moment (EC2 5.3.2.2(4))")
            r = bending(nt, Mf, b, d, mat, "", kind="slab", h=S("h", hf * 10, "mm"), tag=idx)
        res[(kind, idx)] = r
        ok &= r["ok"]
    nt.h2("5. Design for shear")
    rhoB = res[("sup", "B")]["rho_prov"]
    sh = shear_no_links(nt, Vmax, b, d, rhoB, mat)
    nt.h2("6. Control of deflection (EC2 7.4.2)")
    nt.p("End span of a continuous slab: K = 1.3")
    r1 = res[("span", 1)]
    okd = deflection_ld(nt, spans[0] * 1000, d, r1["rho"], r1["rho_prov"], r1["As"], r1["As_prov"], mat,
                        1.3, L["gk"].v, L["qk"].v, L["gd"].v, L["qd"].v)
    nt.h2("7. Detailing")
    dist = detailing_one_way(nt, r1["As_prov"], hf, r1["s"])
    nt.table(["Section", "M_Ed [kNm/m]", "A_s,req [mm²/m]", "Adopted reinforcement", "A_s,prov [mm²/m]"],
             [(f"{'Span' if k == 'span' else 'Support'} {i}", fmt(abs(M.v)), fmt(res[(k, i)]["As"]),
               res[(k, i)]["bars"], fmt(res[(k, i)]["As_prov"])) for k, i, M in moments],
             caption="Reinforcement of the continuous slab")
    meshes, okm = hall_meshes(nt, res, moments, r1, spans, d, mat, L, hf)
    P_.res["II"] = dict(hf=hf, gk=L["gk"].v, spans=spans, env=env,
                        design=dict(span={i: res[("span", i)] for i in range(1, nh + 1)},
                                    sup={sup_names[j]: res[("sup", sup_names[j])] for j in range(1, nh + 1)},
                                    dist=dist, n=n, mesh=meshes),
                        summary=[(f"Slabs {G.no_hall} (hall, continuous)",
                                  f"h_f = {fmt(hf)} cm, welded meshes: span 1 {meshes[('span', 1)]}, "
                                  f"support B {meshes[('sup', 'B')]}")])
    return ok and sh["ok"] and okd and okm


def hall_meshes(nt, res, moments, r1, spans, d, mat, L, hf):
    """The slabs of the hall are reinforced with welded wire meshes (R-type):
    the lightest mesh with A_s ≥ A_s,req in every section; the span mesh is
    increased until the deflection check is satisfied."""
    dr = dry(nt)
    nt.h2("8. Reinforcement with welded wire meshes")
    if not dr:
        nt.p("The slabs are reinforced with welded wire meshes of type R (main bars in the long direction "
             f"of the sheet, standard sheet {fmt(MESH_SHEET[0] / 100)} × {fmt(MESH_SHEET[1] / 100)} m), main "
             "bars parallel to the span. Bottom meshes are placed in every panel and run into the beams up to "
             "the far face minus the cover; top meshes are strips over the beams (0.3·l beyond the face of "
             "the beam) and at the edges. Laps of the transverse bars ≥ 150 mm.")
        nt.table(["Mesh", "Main bars", "Transverse bars", "A_s [mm²/m]", "A_s,tr [mm²/m]"],
                 [(n, f"Φ{fmt(v[0])}/{fmt(v[1] / 10)} cm", f"Φ{fmt(v[2])}/{fmt(v[3] / 10)} cm",
                   fmt(mesh_area(n)[0]), fmt(mesh_area(n)[1])) for n, v in MESHES.items()],
                 caption="Welded wire meshes (R-type)")
    out, rows, ok = {}, [], True
    for kind, idx, M in moments:
        r = res[(kind, idx)]
        m = mesh_for(r["As"])
        if kind == "span" and idx == 1:          # deflection with the area of the mesh
            while not deflection_ld(NullNote(), spans[0] * 1000, d, r1["rho"], mesh_area(m)[0] / (1000 * d.v),
                                    r1["As"], mesh_area(m)[0], mat, 1.3, L["gk"].v, L["qk"].v, L["gd"].v,
                                    L["qd"].v):
                nxt = mesh_for(mesh_area(m)[0] + 1, start=m)
                if nxt == m:
                    ok = False
                    break
                m = nxt
        out[(kind, idx)] = m
        rows.append((f"{'Span' if kind == 'span' else 'Support'} {idx} ({'bottom' if kind == 'span' else 'top'})",
                     fmt(r["As"]), m, fmt(mesh_area(m)[0])))
    As3 = max(0.25 * mesh_area(out[("span", 1)])[0], r1["As_min"], 5 * BAR_AREA[8])
    out["edge"] = mesh_for(As3)
    rows.append(("End supports A, E (top): max(0.25·A_s; A_s,min; 5Φ8/m)", fmt(As3), out["edge"],
                 fmt(mesh_area(out["edge"])[0])))
    out["constr"] = mesh_for(5 * BAR_AREA[8])
    rows.append(("Edges on axes 1, 2, 3 (top, constructive 5Φ8/m)", fmt(5 * BAR_AREA[8]), out["constr"],
                 fmt(mesh_area(out["constr"])[0])))
    nt.table(["Section", "A_s,req [mm²/m]", "Adopted mesh", "A_s,prov [mm²/m]"], rows,
             caption="Welded wire meshes of the continuous slab")
    m1 = out[("span", 1)]
    nt.p(f"Control of deflection with the mesh of the end span ({m1}):", italic=True)
    okd = deflection_ld(nt, spans[0] * 1000, d, r1["rho"], mesh_area(m1)[0] / (1000 * d.v), r1["As"],
                        mesh_area(m1)[0], mat, 1.3, L["gk"].v, L["qk"].v, L["gd"].v, L["qd"].v)
    s_max = min(2 * hf * 10, 250)
    nt.p(f"Spacing of the main bars of the meshes 150 mm ≤ min(2·h_f; 250 mm) = {fmt(s_max)} mm.")
    return out, ok and okd and s_max >= 150


# ============================================================================
# III  continuous one-way slab, plastic analysis
# ============================================================================
def section_III(nt, P_, hf):
    G, inp, pl = P_.G, P_.inp, P_.plot
    n = G.n_room
    nt.h1("III. Design of reinforced concrete continuous slab spanning in one direction - "
          "plastic analysis")
    nos = ", ".join(str(x) for x in G.no_room)
    nt.p(f"Slabs {nos} - meeting room, axes 5'-7 / D-E. The slab is continuous over {n - 1} secondary "
         f"beams (spacing {fmt(G.s_r)} cm) between the walls on axes 5' and 7.")
    nt.h2("1. Static scheme")
    lmax = nt.given("l_max,cl", inp.b - 25, "cm", "Clear span in the long direction (axes D-E)")
    lmin = nt.given("l_min,cl", G.s_r - 25, "cm", "Clear span between the secondary beams")
    lam = nt.calc("λ", lmax / lmin, "")
    nt.compare(lam, ">", S("2", 2.0), ok_text="Slab spanning in one direction")
    hfS = nt.given("h_f", hf, "cm", "Thickness of the slab")
    t = S("t", 25, "cm")
    l1 = nt.calc("l_eff,1", lmin + emin(hfS / 2, t / 2) + t / 2, "cm", "End spans")
    l2 = nt.calc("l_eff,2", lmin + t, "cm", "Interior spans")
    nt.h2("2. Actions")
    L = slab_actions(nt, hf, inp.qk2, "Imposed load - meeting room q_k2 (assignment)")
    nt.h2("3. Static analysis - plastic analysis (moment redistribution)")
    nt.p("For slabs with approximately equal spans (difference ≤ 20 %) and q_k ≤ 1.25 g_k... the "
         "design effects may be taken with the coefficients of the plastic analysis (course table):")
    nt.table(["Section", "Moment", "Shear"],
             [("End span", "p·l²/11", "0.40·p·l (outer support)"),
              ("First interior support", "−p·l²/11", "0.60·p·l"),
              ("Interior spans and supports", "± p·l²/16", "0.50·p·l")],
             caption="Coefficients of the plastic analysis")
    p = L["p"]
    l1m, l2m = S("l_eff,1", l1.v / 100, "m"), S("l_eff,2", l2.v / 100, "m")
    M1 = nt.calc("M_Ed,1", p * l1m**2 / 11, "kNm/m", "End span")
    MB = nt.calc("M_Ed,B", p * emax(l1m, l2m)**2 / 11, "kNm/m", "First interior support (absolute value)")
    M2 = nt.calc("M_Ed,2", p * l2m**2 / 16, "kNm/m", "Interior spans and interior supports")
    V1 = nt.calc("V_Ed,1", N(0.40) * p * l1m, "kN/m", "Outer support")
    V2 = nt.calc("V_Ed,2", N(0.60) * p * l1m, "kN/m", "First interior support")
    V3 = nt.calc("V_Ed,3", N(0.50) * p * l2m, "kN/m", "Interior supports")
    if not dry(nt):
        spans = [l1.v / 100] + [l2.v / 100] * (n - 2) + [l1.v / 100]
        names = [str(x) for x in range(n + 1)]
        f = pl.beam_scheme(spans, ["pin"] * (n + 1), "Static scheme - continuous strip 1 m wide",
                           loads=[(0, sum(spans), p.v, p.v, f"p_d = {fmt(p.v)} kN/m", "#1f5fa8")],
                           name="III_scheme",
                           sup_labels=["5'"] + [f"B{i}" for i in range(1, n)] + ["7"])
        nt.fig(f, "Static scheme of the slabs in the meeting room", 16)
        # plastic moment diagram
        X, Mp = [], []
        x0 = 0
        sup = [0.0] + [-MB.v] + [-M2.v] * (n - 3) + ([-MB.v] if n > 2 else []) + [0.0]
        for i, Ls in enumerate(spans):
            xx = np.linspace(0, Ls, 41)
            Ml, Mr = sup[i], sup[i + 1]
            Mi = Ml + (Mr - Ml) * xx / Ls + p.v * xx * (Ls - xx) / 2
            X += list(x0 + xx)
            Mp += list(Mi)
            x0 += Ls
        Vd = []
        for i, Ls in enumerate(spans):
            xx = np.linspace(0, Ls, 41)
            Vd += list((sup[i + 1] - sup[i]) / Ls + p.v * (Ls / 2 - xx))
        Vd = np.array(Vd)
        f = pl.simple_diagrams(np.array(X), np.array(Mp), Vd, "Bending moments after redistribution",
                               "III_diag", "kNm/m", "kN/m")
        nt.fig(f, "Bending moments and shear forces - plastic analysis", 15)
    nt.h2("4. Design of the bending reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    d = eff_depth(nt, hf)
    b = S("b", 1000, "mm")
    h = S("h", hf * 10, "mm")
    r1 = bending(nt, M1, b, d, mat, "End span (bottom)", kind="slab", h=h, tag="1")
    rB = bending(nt, MB, b, d, mat, "First interior support (top)", kind="slab", h=h, tag="B")
    r2 = bending(nt, M2, b, d, mat, "Interior spans (bottom) and interior supports (top)", kind="slab",
                 h=h, tag="2")
    nt.p("Ductility requirement for plastic analysis (EC2 5.6.2(2)): x_u/d ≤ 0.25 (C ≤ 50/60)",
         bold=True)
    okx = True
    for nm, r in (("1", r1), ("B", rB), ("2", r2)):
        xi = nt.calc(f"x_u/d,{nm}", (1 - S("ζ", r["zeta"])) / N(0.4), "")
        okx &= nt.compare(xi, "≤", S("0.25", 0.25), ok_text="Rotation capacity is sufficient",
                          ng_text="Increase the thickness")
    nt.h2("5. Design for shear")
    Vm = S("V_Ed,max", max(V1.v, V2.v, V3.v), "kN/m")
    nt.p(f"V_Ed,max = max(V_Ed,1; V_Ed,2; V_Ed,3) = {fmt(Vm.v)} kN/m")
    sh = shear_no_links(nt, Vm, b, d, rB["rho_prov"], mat)
    nt.h2("6. Control of deflection (EC2 7.4.2)")
    nt.p("End span of a continuous slab: K = 1.3")
    okd = deflection_ld(nt, l1.v * 10, d, r1["rho"], r1["rho_prov"], r1["As"], r1["As_prov"], mat, 1.3,
                        L["gk"].v, L["qk"].v, L["gd"].v, L["qd"].v)
    nt.h2("7. Detailing")
    dist = detailing_one_way(nt, r1["As_prov"], hf, r1["s"])
    nt.table(["Section", "M_Ed [kNm/m]", "A_s,req [mm²/m]", "Adopted", "A_s,prov [mm²/m]"],
             [(nm, fmt(M.v), fmt(r["As"]), r["bars"], fmt(r["As_prov"])) for nm, M, r in
              (("End span", M1, r1), ("First interior support", MB, rB), ("Interior span/support", M2, r2))],
             caption="Reinforcement of the slabs in the meeting room")
    P_.res["III"] = dict(hf=hf, gk=L["gk"].v, design=dict(r1=r1, rB=rB, r2=r2, dist=dist),
                         summary=[(f"Slabs {nos} (meeting room, plastic)",
                                   f"h_f = {fmt(hf)} cm, end span {r1['bars']}, support B {rB['bars']}")])
    return r1["ok"] and rB["ok"] and r2["ok"] and sh["ok"] and okd and okx


# ============================================================================
# IV  two-way slabs (offices) + balconies
# ============================================================================
def _chi(lx, ly, kx, ky):
    return ky * ly**4 / (kx * lx**4 + ky * ly**4)


def section_IV(nt, P_, hf):
    G, inp, pl = P_.G, P_.inp, P_.plot
    s1, s2, s3 = G.no_office
    b1, b2 = G.no_balcony
    nt.h1("IV. Design of reinforced concrete slabs spanning in two directions")
    nt.p(f"Slabs {s1}, {s2}, {s3} - offices, axes 4-7 / A-B. In direction x (along axis A) the slabs are "
         f"continuous over the beams on axes 5 and 6; in direction y they are supported on the beams on "
         f"axes A and B. Slabs {b1} and {b2} are the balconies (cantilevers, l = d) in front of slabs "
         f"{s1} and {s3}.")
    nt.h2("1. Static scheme")
    lxc = nt.given("l_x,cl", inp.a - 25, "cm", "Clear span in direction x (axes 4-5, 5-6, 6-7)")
    lyc = nt.given("l_y,cl", inp.b - 25, "cm", "Clear span in direction y (axes A-B)")
    hfS = nt.given("h_f", hf, "cm", "Thickness of the slabs")
    t = S("t", 25, "cm")
    a_s = nt.calc("a_s", emin(hfS / 2, t / 2), "cm", "Support at a wall / edge beam: min(h/2; t/2)")
    lx1 = nt.calc("l_eff,x1", lxc + a_s + t / 2, "cm", f"Slabs {s1} and {s3} (one continuous edge)")
    lx2 = nt.calc("l_eff,x2", lxc + t, "cm", f"Slab {s2} (both edges continuous)")
    ly = nt.calc("l_eff,y", lyc + 2 * a_s, "cm", "Direction y")
    lam1 = nt.calc("λ_1", ly / lx1, "")
    nt.compare(lam1, "≥", S("0.5", 0.5), ok_text="l_max/l_min ≤ 2 - slabs spanning in two directions")
    lcc = nt.given("l_c,cl", inp.d, "cm", "Clear length of the balconies (= d)")
    lc = nt.calc("l_c", lcc + t / 2, "cm", "Effective length of the cantilever")
    if not dry(nt):
        A, B = inp.a, inp.b
        rects = [(0, 0, A, B, f"Slab {s1}\ncase 2\n(S | C)", "#dfe9f5"),
                 (A, 0, A, B, f"Slab {s2}\ncase 3\n(C | C)", "#cfe0f2"),
                 (2 * A, 0, A, B, f"Slab {s3}\ncase 2\n(C | S)", "#dfe9f5"),
                 (0, -inp.d, A, inp.d, f"Balcony {b1}", "#f5ecd9"),
                 (2 * A, -inp.d, A, inp.d, f"Balcony {b2}", "#f5ecd9")]
        f = pl.slab_plan(rects, "Slabs spanning in two directions (S = simply supported, "
                         "C = continuous/clamped edge in x)", "IV_plan",
                         arrows=[(0, B * 1.08, A, B * 1.08, f"l_x = {fmt(A)}"),
                                 (-A * 0.08, 0, -A * 0.08, B, f"l_y = {fmt(B)}")])
        nt.fig(f, "Slabs in two directions and boundary conditions", 15)
    nt.h2("2. Actions")
    L = slab_actions(nt, hf, inp.q_office, "Imposed load - offices")
    nt.p("Balconies - characteristic permanent actions:", italic=True)
    gb1 = nt.calc("g_k,c1", (hfS + S("h_tip", HF_TIP, "cm")) / N(200) * N(25), "kN/m²",
                  f"Self-weight, variable thickness h_f → {fmt(HF_TIP)} cm (mean)")
    gb2 = nt.calc("g_k,c2", N(0.10) * N(6) + N(0.04) * N(22) + N(0.02) * N(22) + N(0.02) * N(18), "kN/m²",
                  "Perlite concrete 10 cm, screed 4 cm, mosaic 2 cm, plaster 2 cm")
    gkc = nt.calc("Σg_k,c", gb1 + gb2, "kN/m²")
    qkc = nt.given("q_k,c", inp.q_balcony, "kN/m²", "Imposed load on the balcony")
    gdc = nt.calc("g_d,c", N(1.35) * gkc, "kN/m²")
    qdc = nt.calc("q_d,c", N(1.5) * qkc, "kN/m²")
    nt.p("Parapet (RC base 15/30 cm and metal railing):", italic=True)
    Gpar = nt.calc("G_k,par", N(0.15) * N(0.30) * N(25) + (N(0.3) + N(0.4) + N(0.15)) * N(0.02) * N(18) + N(0.8),
                   "kN/m")
    Hk = nt.given("H_k", 0.5, "kN/m", "Horizontal load on the railing (h = 1.1 m)")
    Gdp = nt.calc("G_d,par", N(1.35) * Gpar, "kN/m")
    Hd = nt.calc("H_d", N(1.5) * Hk, "kN/m")
    nt.h2("3. Static analysis")
    nt.h3("3.1 Cantilever slabs (balconies)")
    lcm = S("l_c", lc.v / 100, "m")
    bpar = S("b_par", 0.075, "m")
    Mc = nt.calc("M_Ed,c", gdc * lcm**2 / 2 + qdc * (lcm - bpar)**2 / 2 + Gdp * (lcm - bpar) + Hd * N(1.1),
                 "kNm/m", "Bending moment at the root of the cantilever")
    Vc = nt.calc("V_Ed,c", gdc * lcm + qdc * (lcm - bpar) + Gdp, "kN/m")
    Mkc = nt.calc("M_k,cg", gkc * lcm**2 / 2 + Gpar * (lcm - bpar), "kNm/m",
                  "Characteristic moment from permanent actions (restraint of the slab edge)")
    nt.h3("3.2 Verification of the boundary condition between slabs and balconies")
    lxm, lym = lx1.v / 100, ly.v / 100
    nt.p("First approximation: the edge on axis A is restrained by the cantilever. Load carried in "
         "direction y (Marcus distribution, edge y fixed - other edge simply supported):")
    ky, kx = 2, 2
    chiy = nt.calc("χ_y", S("k_x", kx) * S("l_x", lxm, "m")**4 /
                   (S("k_x", kx) * S("l_x", lxm, "m")**4 + S("k_y", ky) * S("l_y", lym, "m")**4), "",
                   "k = 2 for fixed-simple, k = 5 for simple-simple, k = 1 for fixed-fixed strips")
    M_restr = nt.calc("M_A,restr", chiy * L["p"] * S("l_y", lym, "m")**2 / 8, "kNm/m",
                      "Restraining moment required for a fixed edge (p·l²/8 of the propped strip)")
    fixed = M_restr.v <= Mkc.v
    if fixed:
        nt.ok("M_A,restr ≤ M_k,cg - the edge on axis A may be considered as fixed.")
    else:
        nt.ok("M_A,restr > M_k,cg - the assumption of a fixed edge is NOT confirmed; the edge on axis A "
              "is treated as simply supported (case 2 / case 3 tables).", True)
    nt.h3("3.3 Bending moments in the spans - elastic analysis (plate theory)")
    nt.p("The coefficients m are obtained from the theory of elastic plates (Lévy series, ν = 0) - the "
         "same basis as the tables of Marcus/Czerny used in the course. M = p·l²/m. For the maximum span "
         "moments the load is split into p' = g_d + q_d/2 acting on the slab with its real boundary "
         "conditions and p'' = q_d/2 acting on all slabs as simply supported (chequerboard loading).")
    c1 = plate_coeffs(lxm, lym, "S", "S")
    c2 = plate_coeffs(lxm, lym, "S", "C")
    lx2m = lx2.v / 100
    c3 = plate_coeffs(lx2m, lym, "C", "C")
    c1b = plate_coeffs(lx2m, lym, "S", "S")
    nt.table(["Case", "Edges x", "l_x [m]", "l_y [m]", "m_x", "m_y", "m_x,sup"],
             [("1", "S - S", fmt(lxm), fmt(lym), fmt(c1["m_x"]), fmt(c1["m_y"]), "-"),
              ("2", "S - C", fmt(lxm), fmt(lym), fmt(c2["m_x"]), fmt(c2["m_y"]), fmt(c2["m_x1"])),
              ("1 (l_x2)", "S - S", fmt(lx2m), fmt(lym), fmt(c1b["m_x"]), fmt(c1b["m_y"]), "-"),
              ("3", "C - C", fmt(lx2m), fmt(lym), fmt(c3["m_x"]), fmt(c3["m_y"]), fmt(c3["m_x0"]))],
             caption="Moment coefficients (plate theory, ν = 0)")
    pi = nt.calc("p'", L["gd"] + L["qd"] / 2, "kN/m²")
    pii = nt.calc("p''", L["qd"] / 2, "kN/m²")
    Lx1, Ly = S("l_eff,x1", lxm, "m"), S("l_eff,y", lym, "m")
    Lx2 = S("l_eff,x2", lx2m, "m")
    nt.p(f"Slabs {s1} and {s3} (case 2):", bold=True)
    Mx1 = nt.calc("M_Ed,x", (pi / S("m_x2", c2["m_x"]) + pii / S("m_x1", c1["m_x"])) * Lx1**2, "kNm/m")
    My1 = nt.calc("M_Ed,y", (pi / S("m_y2", c2["m_y"]) + pii / S("m_y1", c1["m_y"])) * Ly**2, "kNm/m")
    nt.p(f"Slab {s2} (case 3):", bold=True)
    Mx2 = nt.calc("M_Ed,x,2", (pi / S("m_x3", c3["m_x"]) + pii / S("m_x1", c1b["m_x"])) * Lx2**2, "kNm/m")
    My2 = nt.calc("M_Ed,y,2", (pi / S("m_y3", c3["m_y"]) + pii / S("m_y1", c1b["m_y"])) * Ly**2, "kNm/m")
    nt.h3("3.4 Bending moments over the supports (axes 5 and 6)")
    p = L["p"]
    Ma = nt.calc(f"M_{s1}", p * Lx1**2 / S("m_x2,sup", c2["m_x1"]), "kNm/m", f"Clamped edge of slab {s1}")
    Mb = nt.calc(f"M_{s2}", p * Lx2**2 / S("m_x3,sup", c3["m_x0"]), "kNm/m", f"Clamped edge of slab {s2}")
    ratio = min(Ma.v, Mb.v) / max(Ma.v, Mb.v)
    if ratio >= 0.8:
        Ms = nt.calc(f"M_{s1}-{s2}", (Ma + Mb) / 2, "kNm/m", "Ratio ≥ 0.8 → mean value of the two moments")
    else:
        Ms = nt.calc(f"M_{s1}-{s2}", emax(Ma, Mb), "kNm/m", "Ratio < 0.8 → larger value")
    chix = _chi(lxm, lym, 2, 5)
    chiS = nt.calc("χ_x", S("k_y", 5) * Ly**4 / (S("k_x", 2) * Lx1**4 + S("k_y", 5) * Ly**4), "",
                   "Share of the load carried in direction x (Marcus)")
    dM = nt.calc("ΔM", chiS * p * Lx1 / 2 * S("t", 0.25, "m") / 2, "kNm/m", "Reduction to the face of the beam")
    Msf = nt.calc("M_Ed,56", Ms - dM, "kNm/m", "Design moment over the supports (absolute value)")
    nt.h3("3.5 Shear forces")
    Vx = nt.calc("V_Ed,x", N(0.625) * chiS * p * Lx1, "kN/m", "At the continuous edge (5/8 of the strip load)")
    Vy = nt.calc("V_Ed,y", N(0.5) * (1 - chiS) * p * Ly, "kN/m")
    nt.h2("4. Design of the bending reinforcement")
    mat = materials(nt, inp.fck, inp.fyk)
    d = eff_depth(nt, hf, name="d_x")
    d2 = nt.calc("d_y", d - S("φ", 10, "mm"), "mm", "Bars in direction y are placed above the bars in x")
    b = S("b", 1000, "mm")
    h = S("h", hf * 10, "mm")
    R = {}
    R["x1"] = bending(nt, Mx1, b, d, mat, f"Slabs {s1}, {s3} - direction x (bottom)", kind="slab", h=h, tag="x")
    R["y1"] = bending(nt, My1, b, d2, mat, f"Slabs {s1}, {s3} - direction y (bottom)", kind="slab", h=h, tag="y")
    R["x2"] = bending(nt, Mx2, b, d, mat, f"Slab {s2} - direction x (bottom)", kind="slab", h=h, tag="x2")
    R["y2"] = bending(nt, My2, b, d2, mat, f"Slab {s2} - direction y (bottom)", kind="slab", h=h, tag="y2")
    R["sup"] = bending(nt, Msf, b, d, mat, "Over the supports on axes 5 and 6 (top)", kind="slab", h=h, tag="56")
    nt.p("Balconies - top reinforcement at the root of the cantilever:", bold=True)
    R["c"] = bending(nt, Mc, b, d, mat, "", kind="slab", h=h, tag="c")
    nt.h2("5. Design for shear")
    Vm = S("V_Ed,max", max(Vx.v, Vy.v, Vc.v), "kN/m")
    nt.p(f"V_Ed,max = max(V_Ed,x; V_Ed,y; V_Ed,c) = {fmt(Vm.v)} kN/m")
    sh = shear_no_links(nt, Vm, b, d, min(R["sup"]["rho_prov"], R["c"]["rho_prov"]), mat)
    nt.h2("6. Control of deflection (EC2 7.4.2)")
    nt.p("Two-way slab - the shorter span is checked; one edge continuous: K = 1.3")
    lshort = min(lxm, lym)
    rr = R["y1"] if lym <= lxm else R["x1"]
    dd = d2 if lym <= lxm else d
    okd = deflection_ld(nt, lshort * 1000, dd, rr["rho"], rr["rho_prov"], rr["As"], rr["As_prov"], mat, 1.3,
                        L["gk"].v, L["qk"].v, L["gd"].v, L["qd"].v)
    nt.p("Balcony (cantilever): K = 0.4", italic=True)
    rc = R["c"]
    okc = deflection_ld(NullNote(), lc.v * 10, d, rc["rho"], rc["rho_prov"], rc["As"], rc["As_prov"], mat,
                        0.4, gkc.v, qkc.v, gdc.v, qdc.v)
    if not okc:
        # more top reinforcement lowers the steel stress (k_σ = 310/σ_s ≤ 1.5) - try before a thicker slab
        As_t = rc["As_prov"]
        while As_t < 1.5 * rc["As"] + 1:
            As_t *= 1.05
            txt, Asp, phi, sp = slab_bars(As_t, h.v)
            if deflection_ld(NullNote(), lc.v * 10, d, rc["rho"], Asp / (b.v * d.v), rc["As"], Asp, mat,
                             0.4, gkc.v, qkc.v, gdc.v, qdc.v):
                nt.p(f"With {rc['bars']} the simplified l/d check of the cantilever is not satisfied - the top "
                     f"reinforcement of the balconies is increased to {txt} (A_s,prov = {fmt(Asp)} mm²/m), which "
                     "lowers the steel stress σ_s:", italic=True)
                R["c"] = rc = dict(rc, bars=txt, As_prov=Asp, phi=phi, s=sp, rho_prov=Asp / (b.v * d.v))
                break
    okc = deflection_ld(nt, lc.v * 10, d, rc["rho"], rc["rho_prov"], rc["As"], rc["As_prov"], mat,
                        0.4, gkc.v, qkc.v, gdc.v, qdc.v)
    nt.h2("7. Reinforcement summary")
    nt.table(["Location", "M_Ed [kNm/m]", "A_s,req [mm²/m]", "Adopted", "A_s,prov [mm²/m]"],
             [(lbl, fmt(M.v), fmt(R[k]["As"]), R[k]["bars"], fmt(R[k]["As_prov"])) for lbl, M, k in
              ((f"{s1}/{s3} x", Mx1, "x1"), (f"{s1}/{s3} y", My1, "y1"), (f"{s2} x", Mx2, "x2"),
               (f"{s2} y", My2, "y2"), ("supports 5, 6", Msf, "sup"), ("balcony root", Mc, "c"))],
             caption="Reinforcement of the slabs in two directions")
    P_.res["IV"] = dict(hf=hf, gk=L["gk"].v, qk=L["qk"].v, gkc=gkc.v, design=R,
                        summary=[(f"Slabs {s1}, {s2}, {s3} (offices, two-way)",
                                  f"h_f = {fmt(hf)} cm, x: {R['x1']['bars']}, y: {R['y1']['bars']}, "
                                  f"supports: {R['sup']['bars']}"),
                                 (f"Balconies {b1}, {b2}", f"top {R['c']['bars']}")])
    if not okc:
        nt.p("Note: the simplified l/d check of the cantilever is not satisfied. The balconies are made "
             f"with a root thickness h_f and a tip thickness of {fmt(HF_TIP)} cm; increase the root thickness or "
             "verify the deflection by calculation (EC2 7.4.3).", italic=True)
    ok = all(r["ok"] for r in R.values()) and sh["ok"] and okd and okc
    return ok
