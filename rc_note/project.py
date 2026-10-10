# -*- coding: utf-8 -*-
"""project.py - input data, geometry of the building and common blocks."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

from .engine import S, N, fmt


@dataclass
class Inputs:
    # --- student -------------------------------------------------------
    student: str = ""
    faculty_no: str = ""
    date: str = ""
    # --- assignment sheet ("Input data") -------------------------------
    a: float = 630.0      # cm
    b: float = 580.0      # cm
    c: float = 350.0      # cm
    d: float = 170.0      # cm
    hs: float = 310.0     # cm  floor height
    hb: float = 290.0     # cm  height of the first (lowest) storey
    qk1: float = 5.60     # kN/m2 exhibition hall
    qk2: float = 3.30     # kN/m2 meeting room
    R0: float = 230.0     # kN/m2 design soil pressure (characteristic)
    # --- loads not on the sheet (course values) ------------------------
    q_office: float = 3.5     # kN/m2 offices / corridors
    q_stair: float = 3.0      # kN/m2 stairs
    q_balcony: float = 3.0    # kN/m2 balconies
    s_k: float = 1.0          # kN/m2 snow / roof variable action
    n_floors: int = 4         # storeys of height hs above the first storey
    # --- materials -----------------------------------------------------
    fck: float = 25.0
    fyk: float = 500.0
    # --- element sizes (0 = automatic) ---------------------------------
    hf_corridor: float = 0    # cm
    hf_hall: float = 0
    hf_room: float = 0
    hf_office: float = 0
    hf_stair: float = 0
    hf_canopy: float = 15
    B5_b: float = 25; B5_h: float = 0
    B21_b: float = 25; B21_h: float = 0
    B12_b: float = 25; B12_h: float = 0
    B15_b: float = 30; B15_h: float = 0
    BT_b: float = 25; BT_h: float = 50          # torsion beam (canopy slab 7)
    C1_b: float = 40; C1_h: float = 60          # columns on axes A and E (frame 2)
    C7_b: float = 40; C7_h: float = 80          # column at 2/C
    C10_b: float = 25; C10_h: float = 60        # office column 5/B
    wall_t: float = 0.25                        # m, brick partition walls
    wall_gamma: float = 17.0                    # kN/m3

    @classmethod
    def from_dict(cls, d):
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def to_dict(self):
        return asdict(self)


def ceil_to(v, step):
    return math.ceil(v / step - 1e-9) * step


class Geometry:
    """Grid and derived quantities (all in cm unless stated)."""

    def __init__(self, inp: Inputs):
        a, b, c, d = inp.a, inp.b, inp.c, inp.d
        X = {"1": 0.0}
        X["2"] = a
        X["3"] = 2 * a
        X["4"] = X["3"] + 2 * d + 45
        X["5'"] = X["4"] + 425
        X["5"] = X["4"] + a
        X["6"] = X["5"] + a
        X["7"] = X["6"] + a
        Y = {"A": 0.0, "B": b, "C": b + c / 2, "D": b + c, "E": 2 * b + c}
        self.X, self.Y = X, Y
        self.half = b + c / 2                       # A-C (= C-E)
        self.n_half = math.ceil(2 * self.half / a - 1e-9)
        self.s_h = self.half / self.n_half          # secondary beam spacing (hall)
        self.L_room = X["7"] - X["5'"]
        self.n_room = math.ceil(2 * self.L_room / b - 1e-9)
        self.s_r = self.L_room / self.n_room
        # slab numbers (as in the formwork plan)
        nh = 2 * self.n_half
        self.no_hall = f"1-{nh}"
        self.no_stairs = [nh + 1, nh + 2, nh + 3]
        self.no_10 = nh + 4
        r0 = nh + 5
        self.no_room = list(range(r0, r0 + self.n_room))
        k = r0 + self.n_room
        self.no_corr = k
        self.no_lobby = k + 1
        self.no_office = [k + 2, k + 3, k + 4]
        self.no_balcony = [k + 5, k + 6]
        # heights
        self.levels = [0.0, inp.hb] + [inp.hb + i * inp.hs for i in range(1, inp.n_floors + 1)]
        self.n_storeys = inp.n_floors + 1


def slab_actions(nt, hf_cm, qk_val, q_desc="Imposed load", finishes=True):
    """Floor slab: self-weight + floor finishes + ceiling plaster."""
    nt.p("Characteristic values - permanent actions:", italic=True)
    hf = S("h_f", hf_cm / 100, "m")
    g1 = nt.calc("g_k,1", hf * N(25), "kN/m²", "Self-weight of the slab (γ = 25 kN/m³)")
    g2 = nt.calc("g_k,2", N(0.05) * N(22), "kN/m²", "Floor finishes, 5 cm (γ = 22 kN/m³)")
    g3 = nt.calc("g_k,3", N(0.02) * N(18), "kN/m²", "Ceiling plaster, 2 cm (γ = 18 kN/m³)")
    gk = nt.calc("Σg_k", g1 + g2 + g3, "kN/m²", "Total permanent action")
    nt.p("Characteristic value - variable action:", italic=True)
    qk = nt.given("q_k", qk_val, "kN/m²", q_desc)
    nt.p("Design values (EN 1990, 6.10):", italic=True)
    gd = nt.calc("g_d", N(1.35) * gk, "kN/m²", "Permanent action, γ_G = 1.35")
    qd = nt.calc("q_d", N(1.5) * qk, "kN/m²", "Variable action, γ_Q = 1.5")
    p = nt.calc("p_d", gd + qd, "kN/m²", "Total design load")
    return dict(gk=gk, qk=qk, gd=gd, qd=qd, p=p)


def roof_actions(nt, hf_cm, sk, label="roof slab"):
    nt.p(f"Characteristic permanent actions on the {label}:", italic=True)
    items = [("waterproofing", 0.04), ("protective layer", 0.66), ("thermal insulation", 0.20),
             ("vapour barrier", 0.03), ("levelling cement screed", 0.44),
             ("lightweight concrete for slope", 1.76)]
    rows = [(n, v) for n, v in items]
    rows.append((f"RC slab h_f = {fmt(hf_cm)} cm", hf_cm / 100 * 25))
    rows.append(("ceiling plaster", 0.36))
    nt.table(["Layer", "g_k [kN/m²]"], [(n, fmt(v)) for n, v in rows], caption=f"Permanent actions - {label}")
    gk = nt.given("Σg_k,roof", sum(v for _, v in rows), "kN/m²", "Total permanent action of the roof")
    skS = nt.given("s_k", sk, "kN/m²", "Variable action on the roof (snow / maintenance)")
    return gk, skS
