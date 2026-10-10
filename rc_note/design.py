# -*- coding: utf-8 -*-
"""
design.py - Eurocode 2 design steps that write their own equations.

All functions take the Note (real or NullNote) as first argument and
S-symbols as inputs, and return a dict with the results.
"""
from __future__ import annotations

import math

import numpy as np

from .engine import (S, N, P, sqrt, cbrt, emin, emax, eabs, ecot, etan, esin, ecos,
                     fmt)

MU_LIM = 0.295     # limit relative moment (course value, x/d = 0.45, C<=50)


# ============================================================================
# Null note (dry runs for automatic iterations)
# ============================================================================
class NullNote:
    def __getattr__(self, k):
        def f(*a, **kw):
            if k in ("calc",):
                expr = a[1]
                val = kw.get("value")
                v = expr.value() if hasattr(expr, "value") else float(expr)
                return S(a[0], v if val is None else val, a[2] if len(a) > 2 else kw.get("unit", ""))
            if k == "given":
                return S(a[0], a[1], a[2] if len(a) > 2 else kw.get("unit", ""))
            if k == "compare":
                av, bv = float(a[0].value()), float(a[2].value())
                op = a[1]
                g = kw.get("good")
                if g is None:
                    g = {"<": av < bv, "≤": av <= bv + 1e-9, ">": av > bv, "≥": av >= bv - 1e-9}[op]
                return g
            return None
        return f


# ============================================================================
# Materials
# ============================================================================
def materials(nt, fck=25.0, fyk=500.0, alpha_cc=1.0, title=True):
    if title:
        nt.p("Design characteristics of the materials (EN 1992-1-1):", bold=True)
        nt.p(f"Concrete C{int(fck)}/{int(fck + 5)}, reinforcing steel B{int(fyk)}.")
    f_ck = nt.given("f_ck", fck, "N/mm²", "Characteristic cylinder strength of concrete")
    g_c = S("γ_c", 1.5)
    a_cc = S("α_cc", alpha_cc)
    f_cd = nt.calc("f_cd", a_cc * f_ck / g_c, "N/mm²", "Design compressive strength")
    f_ctm = nt.given("f_ctm", 0.30 * fck ** (2 / 3) if fck <= 50 else 2.12 * math.log(1 + (fck + 8) / 10),
                     "N/mm²", "Mean tensile strength", digits=2)
    f_yk = nt.given("f_yk", fyk, "N/mm²", "Characteristic yield strength of steel")
    g_s = S("γ_s", 1.15)
    f_yd = nt.calc("f_yd", f_yk / g_s, "N/mm²", "Design yield strength of steel")
    E_cm = 22 * ((fck + 8) / 10) ** 0.3
    return dict(f_ck=f_ck, f_cd=f_cd, f_ctm=f_ctm, f_yk=f_yk, f_yd=f_yd, E_cm=E_cm,
                fck=fck, fcd=f_cd.v, fyd=f_yd.v, fctm=f_ctm.v, fyk=fyk)


# ============================================================================
# Bar selection
# ============================================================================
BAR_AREA = {d: math.pi * d * d / 4 for d in (6, 8, 10, 12, 14, 16, 18, 20, 22, 25, 28, 32)}


def slab_bars(As_req, h_mm, s_max=None, dias=(8, 10, 12, 14, 16)):
    """Bars per metre: returns (text, As_prov, phi, s)."""
    s_max = s_max or min(2 * h_mm, 250)
    best = None
    for phi in dias:
        for s in (100, 110, 125, 140, 150, 160, 175, 200, 250):
            if s > s_max:
                continue
            As = BAR_AREA[phi] * 1000 / s
            if As + 1e-6 >= As_req:
                key = (As, -s)
                if best is None or key < best[0]:
                    best = (key, phi, s, As)
    if best is None:
        phi, s = dias[-1], 100
        As = BAR_AREA[phi] * 10
    else:
        _, phi, s, As = best
    n = 1000 / s
    if abs(n - round(n)) < 0.01:
        return f"{int(round(n))}Φ{phi}/{fmt(s / 10)} cm", As, phi, s
    return f"Φ{phi}/{fmt(s / 10)} cm", As, phi, s


def beam_bars(As_req, bw, cover=25, phi_w=8, dias=(12, 14, 16, 18, 20, 22, 25), nmin=2):
    best = None
    for phi in dias:
        for n in range(nmin, 9):
            clear = (bw - 2 * (cover + phi_w) - n * phi) / max(n - 1, 1)
            if n > 1 and clear < max(phi, 25):
                continue
            As = n * BAR_AREA[phi]
            if As + 1e-6 >= As_req:
                key = (As, n)
                if best is None or key < best[0]:
                    best = (key, n, phi, As)
                break
    if best is None:   # two layers
        for phi in dias[::-1]:
            n = math.ceil(As_req / BAR_AREA[phi])
            return f"{n}Φ{phi} (2 layers)", n * BAR_AREA[phi], phi, n
    _, n, phi, As = best
    return f"{n}Φ{phi}", As, phi, n


# ============================================================================
# Bending
# ============================================================================
def bending(nt, M, b, d, mat, label="", bt=None, kind="slab", h=None, tag=""):
    """M: S [kNm or kNm/m]; b,d: S [mm]; bt: width in tension for As,min.
    Returns dict(As_req, As_prov, rho, rho_prov, bars, zeta, mu)."""
    sfx = f",{tag}" if tag else ""
    if label:
        nt.p(label, bold=True)
    mu = nt.calc(f"μ_Ed{sfx}", eabs(M) * N(1e6, "10⁶") / (b * d**2 * mat["f_cd"]), "",
                 "Relative design moment")
    ok = nt.compare(mu, "≤", S("μ_lim", MU_LIM), ok_text="Single reinforcement is sufficient",
                    ng_text="μ_Ed > μ_lim - increase the depth of the section")
    mu_v = min(mu.v, 0.499)
    zeta = nt.calc(f"ζ_{tag}" if tag else "ζ", N(0.5) * (1 + sqrt(1 - 2 * S(mu.name, mu_v))), "",
                   "Lever arm ratio z/d")
    As_req = nt.calc(f"A_s,req{sfx}", eabs(M) * N(1e6, "10⁶") / (zeta * d * mat["f_yd"]),
                     "mm²" + ("/m" if kind == "slab" else ""), "Required reinforcement")
    bt = bt or b
    Asmin1 = 0.26 * mat["fctm"] / mat["fyk"] * bt.v * d.v
    Asmin = nt.calc(f"A_s,min{sfx}", emax(N(0.26) * mat["f_ctm"] / mat["f_yk"] * bt * d,
                                          N(0.0013) * bt * d),
                    "mm²" + ("/m" if kind == "slab" else ""), "Minimum reinforcement (EC2 9.2.1.1)")
    As = max(As_req.v, Asmin.v)
    if kind == "slab":
        txt, As_prov, phi, s = slab_bars(As, h.v if h else 2 * d.v)
        extra = dict(phi=phi, s=s)
    else:
        txt, As_prov, phi, n = beam_bars(As, bt.v)
        extra = dict(phi=phi, n=n)
    nt.p(f"Provided reinforcement: {txt}  →  A_s,prov = {fmt(As_prov)} mm²"
         + ("/m" if kind == "slab" else ""), bold=True)
    rho = nt.calc(f"ρ_{tag}" if tag else "ρ", S("A_s", As, "mm²") / (bt * d), "", "Required reinforcement ratio")
    rho_p = nt.calc(f"ρ_prov{sfx}", S("A_s,prov", As_prov, "mm²") / (bt * d), "",
                    "Provided reinforcement ratio")
    xi = (1 - zeta.v) / 0.4
    return dict(As_req=As_req.v, As=As, As_min=Asmin.v, As_prov=As_prov, rho=rho.v,
                rho_prov=rho_p.v, bars=txt, zeta=zeta.v, mu=mu.v, ok=ok, xi=xi, **extra)


def flange_check(nt, M, beff, hf, d, mat):
    """T-section: is the neutral axis in the flange?  (0.8x = hf)"""
    Fcd = nt.calc("F_cd", beff * hf * mat["f_cd"] / N(1000, "10³"), "kN",
                  "Compression force of the whole flange (0.8x = h_f)")
    Mf = nt.calc("M_f", Fcd * (d - hf / 2) / N(1000, "10³"), "kNm",
                 "Moment resisted by the flange")
    inflange = nt.compare(S(M.name, abs(M.v), M.unit), "≤", Mf,
                          ok_text="The neutral axis is in the flange - rectangular section b = b_eff",
                          ng_text="Neutral axis in the web - T-section design")
    return inflange


# ============================================================================
# Shear
# ============================================================================
def shear_no_links(nt, V, b, d, rho_l, mat, per_m=True, beam=False):
    k = nt.calc("k", emin(1 + sqrt(N(200) / d), N(2)), "", "Size factor")
    C = S("C_Rd,c", 0.18 / 1.5, digits=3)
    rho = S("ρ_l", min(rho_l, 0.02), digits=5)
    vmin = nt.calc("v_min", N(0.035) * k**N(1.5) * sqrt(mat["f_ck"]), "N/mm²")
    u = "kN/m" if per_m else "kN"
    VRc = nt.calc("V_Rd,c", C * k * cbrt(N(100) * rho * mat["f_ck"]) * b * d / N(1000, "10³"), u,
                  "Shear resistance without shear reinforcement (EC2 6.2.2)")
    VRmin = nt.calc("V_Rd,c,min", vmin * b * d / N(1000, "10³"), u)
    VR = S("V_Rd,c", max(VRc.v, VRmin.v), u)
    nt.p(f"V_Rd,c = max(V_Rd,c ; V_Rd,c,min) = {fmt(VR.v)} {u}")
    ok = nt.compare(S(V.name, abs(V.v), V.unit), "≤", VR,
                    ok_text="No shear reinforcement is required" + (" (minimum links are provided)" if beam else ""),
                    ng_text=("Shear reinforcement is required - designed below" if beam else
                             "Shear reinforcement (or a thicker section) is required"), neutral=beam)
    return dict(ok=ok, VRdc=VR.v)


def shear_links(nt, V, bw, d, rho_l, mat, cot=2.5, phi_w=8, legs=2):
    nt.p("Strut inclination θ: cot θ = " + fmt(cot) + f"  (θ = {fmt(math.degrees(math.atan(1 / cot)))}°)")
    z = nt.calc("z", N(0.9) * d, "mm", "Internal lever arm")
    nu1 = nt.calc("ν_1", N(0.6) * (1 - mat["f_ck"] / N(250)), "")
    ct = S("cot θ", cot)
    VRmax = nt.calc("V_Rd,max", bw * z * nu1 * mat["f_cd"] / (ct + 1 / ct) / N(1000, "10³"), "kN",
                    "Resistance of the compression struts (EC2 6.9)")
    okmax = nt.compare(S(V.name, abs(V.v), "kN"), "≤", VRmax,
                       ok_text="The concrete struts are not crushed",
                       ng_text="V_Ed > V_Rd,max - increase the section")
    sh = shear_no_links(nt, V, bw, d, rho_l, mat, per_m=False, beam=True)
    fywd = mat["f_yd"]
    aw = nt.calc("A_sw/s", S(V.name, abs(V.v)) * N(1000, "10³") / (z * fywd * ct), "mm²/mm",
                 "Required shear reinforcement (EC2 6.8)")
    rwmin = nt.calc("ρ_w,min", N(0.08) * sqrt(mat["f_ck"]) / mat["f_yk"], "", digits=5)
    awmin = nt.calc("(A_sw/s)_min", rwmin * bw, "mm²/mm")
    need = max(aw.v, awmin.v)
    Asw = legs * BAR_AREA[phi_w]
    s_max = min(0.75 * d.v, 300)
    s = math.floor(min(Asw / need, s_max) / 10) * 10
    s = max(s, 50)
    nt.calc("s", S("A_sw", Asw, "mm²") / S("(A_sw/s)", need, "mm²/mm"), "mm",
            f"Spacing of {legs}-leg links Φ{phi_w} (A_sw = {legs}·{fmt(BAR_AREA[phi_w])} mm²)")
    nt.calc("s_l,max", N(0.75) * d, "mm", "Maximum longitudinal spacing of links (EC2 9.2.2)")
    nt.p(f"Adopted links: Φ{phi_w}/{fmt(s / 10)} cm ({legs}-leg) in the support zones", bold=True)
    dF = nt.calc("ΔF_td", N(0.5) * S(V.name, abs(V.v), "kN") * ct, "kN",
                 "Additional tensile force in the longitudinal reinforcement (EC2 6.2.3(7))")
    return dict(ok=okmax, s=s, phi_w=phi_w, links=f"Φ{phi_w}/{fmt(s / 10)} cm", need_links=not sh["ok"])


def flange_shear(nt, dM, dx, d, hf, beff, bw, mat, compression=True):
    """Longitudinal shear between web and flange (EC2 6.2.4)."""
    dF = nt.calc("ΔF_d", dM * N(1e6, "10⁶") / (d - hf / 2) * (N(0.5) * (beff - bw) / beff) / N(1000, "10³"),
                 "kN", "Change of the longitudinal force in one flange outstand over Δx")
    vEd = nt.calc("v_Ed", dF * N(1000, "10³") / (hf * dx), "N/mm²", "Longitudinal shear stress")
    lim = S("0.4·f_ctd", 0.4 * 0.7 * mat["fctm"] / 1.5)
    small = nt.compare(vEd, "≤", lim, ok_text="No additional transverse reinforcement is needed",
                       ng_text="Transverse reinforcement for the flange shear is needed - designed below",
                       neutral=True)
    if not small:
        cot = 2.0 if compression else 1.25
        th = math.degrees(math.atan(1 / cot))
        nu = 0.6 * (1 - mat["fck"] / 250)
        vmax = S("ν·f_cd·sinθ·cosθ", nu * mat["fcd"] * math.sin(math.radians(th)) * math.cos(math.radians(th)))
        nt.compare(vEd, "≤", vmax, ok_text="The compression struts in the flange are adequate",
                   ng_text="Increase the flange thickness")
        Asf = nt.calc("A_sf/s_f", vEd * hf / (mat["f_yd"] * S("cot θ_f", cot)) * N(1000), "mm²/m",
                      "Required transverse reinforcement in the flange")
        return dict(Asf=Asf.v)
    return dict(Asf=0)


# ============================================================================
# Deflection - span/depth ratio (EC2 7.4.2)
# ============================================================================
def deflection_ld(nt, l_eff_mm, d, rho, rho_prov, As_req, As_prov, mat, K, gk, qk, gd, qd,
                  psi2=0.3):
    fck = mat["fck"]
    rho0 = nt.calc("ρ_0", sqrt(mat["f_ck"]) * N(1e-3, "10⁻³"), "", digits=5)
    rho_s = S("ρ", max(rho, 1e-6), digits=5)
    Kc = S("K", K)
    if rho <= rho0.v:
        ld = nt.calc("(l/d)_basic", Kc * (N(11) + N(1.5) * sqrt(mat["f_ck"]) * rho0 / rho_s
                                          + N(3.2) * sqrt(mat["f_ck"]) * (rho0 / rho_s - 1) ** N(1.5)),
                     "", "Basic span/depth ratio, ρ ≤ ρ_0 (EC2 7.16a)")
    else:
        ld = nt.calc("(l/d)_basic", Kc * (N(11) + N(1.5) * sqrt(mat["f_ck"]) * rho0 / rho_s), "",
                     "Basic span/depth ratio, ρ > ρ_0 (EC2 7.16b, ρ' = 0)")
    sig = nt.calc("σ_s", mat["f_yd"] * (S("g_k", gk) + N(psi2) * S("q_k", qk)) /
                  (S("g_d", gd) + S("q_d", qd)) * S("A_s,req", As_req) / S("A_s,prov", As_prov),
                  "N/mm²", "Steel stress under the quasi-permanent load")
    k2 = nt.calc("k_σ", emin(N(310) / sig, N(1.5)), "", "Correction factor 310/σ_s (≤ 1.5)")
    lim = nt.calc("(l/d)_lim", ld * k2, "")
    act = nt.calc("l/d", S("l_eff", l_eff_mm, "mm") / d, "")
    ok = nt.compare(act, "≤", lim, ok_text="Deflection need not be calculated (l/d check satisfied)",
                    ng_text="l/d too large - increase the depth")
    return ok


# ============================================================================
# Columns: N-M interaction (symmetric reinforcement)
# ============================================================================
def _NM_capacity(b, h, As_face, d1, fcd, fyd, x):
    """Rectangular stress block; returns N (compression +), M about centroid."""
    Es, ecu = 200000.0, 0.0035
    lam, eta = 0.8, 1.0
    a = min(lam * x, h)
    Fc = eta * fcd * b * a
    d = h - d1
    eps1 = ecu * (x - d1) / x          # top steel (compression +)
    eps2 = ecu * (x - d) / x           # bottom steel
    s1 = max(min(Es * eps1, fyd), -fyd)
    s2 = max(min(Es * eps2, fyd), -fyd)
    Nn = Fc + As_face * s1 + As_face * s2
    Mn = Fc * (h / 2 - a / 2) + As_face * s1 * (h / 2 - d1) - As_face * s2 * (h / 2 - d1)
    return Nn, Mn


def interaction_curve(b, h, As_tot, d1, fcd, fyd, npts=200):
    As_face = As_tot / 2
    pts = []
    for x in np.concatenate([np.linspace(1, h, npts // 2), np.linspace(h, 6 * h, npts // 2)]):
        pts.append(_NM_capacity(b, h, As_face, d1, fcd, fyd, x))
    pts.append(((b * h) * fcd + As_tot * fyd, 0.0))
    pts.insert(0, (-As_tot * fyd, 0.0))
    return np.array(pts)


def required_As(N_Ed, M_Ed, b, h, d1, fcd, fyd):
    """Minimum symmetric As,tot [mm²] so that (N,M) [N, Nmm] is inside."""
    def inside(As):
        c = interaction_curve(b, h, As, d1, fcd, fyd, 300)
        # M capacity at given N by interpolation on the upper branch
        Ns, Ms = c[:, 0], c[:, 1]
        order = np.argsort(Ns)
        Ns, Ms = Ns[order], Ms[order]
        if N_Ed > Ns.max() or N_Ed < Ns.min():
            return False
        Mcap = np.interp(N_Ed, Ns, Ms)
        return Mcap >= abs(M_Ed)
    lo, hi = 0.0, 0.08 * b * h
    if not inside(hi):
        return None
    if inside(0.0):
        return 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if inside(mid):
            hi = mid
        else:
            lo = mid
    return hi


def column_bars(As_req, b, h, dias=(16, 18, 20, 22, 25, 28)):
    best = None
    for phi in dias:
        for n in (4, 6, 8, 10, 12, 14, 16):
            As = n * BAR_AREA[phi]
            if As >= As_req:
                key = (As, n)
                if best is None or key < best[0]:
                    best = (key, n, phi, As)
                break
    _, n, phi, As = best
    return f"{n}Φ{phi}", As, phi, n
