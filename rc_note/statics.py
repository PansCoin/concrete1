# -*- coding: utf-8 -*-
"""
statics.py - structural analysis used by the explanatory note

* Frame2D           : direct stiffness method for plane frames / continuous
                      beams (Euler-Bernoulli elements, linear element loads)
* ContinuousBeam    : continuous beam with permanent + pattern variable load,
                      exact envelopes by superposition of single-span cases
* plate_levy        : rectangular plate, two opposite edges simply supported,
                      other two edges simply supported or clamped (Levy series)
                      -> moment coefficients like the Marcus/Czerny tables
Units are whatever the caller uses consistently (here kN, m).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


# ============================================================================
# Plane frame
# ============================================================================
@dataclass
class Elem:
    n1: int
    n2: int
    E: float
    A: float
    I: float
    tag: str = ""


class Frame2D:
    def __init__(self):
        self.nodes: list[tuple[float, float]] = []
        self.elems: list[Elem] = []
        self.fix: dict[int, tuple[bool, bool, bool]] = {}

    # geometry -----------------------------------------------------------
    def node(self, x, y):
        for i, (a, b) in enumerate(self.nodes):
            if abs(a - x) < 1e-9 and abs(b - y) < 1e-9:
                return i
        self.nodes.append((float(x), float(y)))
        return len(self.nodes) - 1

    def elem(self, n1, n2, E, A, I, tag=""):
        self.elems.append(Elem(n1, n2, E, A, I, tag))
        return len(self.elems) - 1

    def support(self, n, ux=True, uy=True, rz=True):
        self.fix[n] = (ux, uy, rz)

    def geom(self, e: Elem):
        (x1, y1), (x2, y2) = self.nodes[e.n1], self.nodes[e.n2]
        L = math.hypot(x2 - x1, y2 - y1)
        return L, (x2 - x1) / L, (y2 - y1) / L

    @staticmethod
    def k_local(E, A, I, L):
        k = np.zeros((6, 6))
        ea, ei = E * A / L, E * I
        k[0, 0] = k[3, 3] = ea
        k[0, 3] = k[3, 0] = -ea
        k[1, 1] = k[4, 4] = 12 * ei / L**3
        k[1, 4] = k[4, 1] = -12 * ei / L**3
        k[1, 2] = k[2, 1] = k[1, 5] = k[5, 1] = 6 * ei / L**2
        k[4, 2] = k[2, 4] = k[4, 5] = k[5, 4] = -6 * ei / L**2
        k[2, 2] = k[5, 5] = 4 * ei / L
        k[2, 5] = k[5, 2] = 2 * ei / L
        return k

    @staticmethod
    def T(c, s):
        t = np.zeros((6, 6))
        for o in (0, 3):
            t[o, o], t[o, o + 1] = c, s
            t[o + 1, o], t[o + 1, o + 1] = -s, c
            t[o + 2, o + 2] = 1
        return t

    # analysis -----------------------------------------------------------
    def solve(self, nodal=None, eloads=None):
        """nodal : {node: (Fx, Fy, Mz)}  (global)
        eloads: {elem: (wy1, wy2)} global vertical load per unit length of the
                element axis, linear from n1 to n2 (negative = downwards)
        returns Result"""
        nodal = nodal or {}
        eloads = eloads or {}
        nn = len(self.nodes)
        K = np.zeros((3 * nn, 3 * nn))
        F = np.zeros(3 * nn)
        fe_loc = {}
        for ei_, e in enumerate(self.elems):
            L, c, s = self.geom(e)
            kl = self.k_local(e.E, e.A, e.I, L)
            t = self.T(c, s)
            kg = t.T @ kl @ t
            dofs = [3 * e.n1, 3 * e.n1 + 1, 3 * e.n1 + 2, 3 * e.n2, 3 * e.n2 + 1, 3 * e.n2 + 2]
            K[np.ix_(dofs, dofs)] += kg
            if ei_ in eloads:
                w1, w2 = eloads[ei_]
                # global vertical load -> local components
                q1x, q1y = w1 * s, w1 * c      # local x along member, y normal
                q2x, q2y = w2 * s, w2 * c
                d = q2y - q1y
                feq = np.array([
                    L * (2 * q1x + q2x) / 6,
                    q1y * L / 2 + 3 * d * L / 20,
                    q1y * L**2 / 12 + d * L**2 / 30,
                    L * (q1x + 2 * q2x) / 6,
                    q1y * L / 2 + 7 * d * L / 20,
                    -(q1y * L**2 / 12 + d * L**2 / 20),
                ])
                fe_loc[ei_] = (feq, (q1x, q1y, q2x, q2y))
                F[dofs] += t.T @ feq
        for n, (fx, fy, mz) in nodal.items():
            F[3 * n] += fx
            F[3 * n + 1] += fy
            F[3 * n + 2] += mz
        fixed = []
        for n, f in self.fix.items():
            for k in range(3):
                if f[k]:
                    fixed.append(3 * n + k)
        free = [i for i in range(3 * nn) if i not in fixed]
        u = np.zeros(3 * nn)
        u[free] = np.linalg.solve(K[np.ix_(free, free)], F[free])
        R = K @ u - F
        return Result(self, u, R, fe_loc)


class Result:
    def __init__(self, fr: Frame2D, u, R, fe_loc):
        self.fr, self.u, self.R, self.fe = fr, u, R, fe_loc
        self.end = []
        for ei_, e in enumerate(fr.elems):
            L, c, s = fr.geom(e)
            t = fr.T(c, s)
            dofs = [3 * e.n1, 3 * e.n1 + 1, 3 * e.n1 + 2, 3 * e.n2, 3 * e.n2 + 1, 3 * e.n2 + 2]
            f = fr.k_local(e.E, e.A, e.I, L) @ (t @ u[dofs])
            if ei_ in fe_loc:
                f = f - fe_loc[ei_][0]
            self.end.append(f)

    def reaction(self, n):
        return self.R[3 * n], self.R[3 * n + 1], self.R[3 * n + 2]

    def internal(self, ei_, npts=21):
        """x (local), N (tension +), V, M (sagging + for beams drawn left->right)"""
        e = self.fr.elems[ei_]
        L, c, s = self.fr.geom(e)
        f = self.end[ei_]
        q1x = q1y = q2x = q2y = 0.0
        if ei_ in self.fe:
            q1x, q1y, q2x, q2y = self.fe[ei_][1]
        xs = np.linspace(0, L, npts)
        N, V, M = [], [], []
        for x in xs:
            qy_int = q1y * x + (q2y - q1y) * x**2 / (2 * L)
            qx_int = q1x * x + (q2x - q1x) * x**2 / (2 * L)
            # moment of distributed load about section x
            m_q = q1y * x**2 / 2 + (q2y - q1y) * x**3 / (6 * L)
            N.append(-f[0] - qx_int)
            V.append(f[1] + qy_int)
            M.append(-f[2] + f[1] * x + m_q)
        return xs, np.array(N), np.array(V), np.array(M)


# ============================================================================
# Continuous beam with exact envelopes
# ============================================================================
class ContinuousBeam:
    """spans [m]; supports: list of 'pin' or 'fix' for every support
    (len = n+1); EI per span (relative). Loads per span: callables returning
    (w1, w2) linear segments, or a constant (UDL), positive downwards."""

    def __init__(self, spans, supports=None, EI=None, nseg=40):
        self.spans = list(spans)
        n = len(spans)
        self.supports = supports or ["pin"] * (n + 1)
        self.EI = EI or [1.0] * n
        self.nseg = nseg
        self.fr = Frame2D()
        self.span_elems = []
        self.xs_nodes = []
        x0 = 0.0
        prev = self.fr.node(0, 0)
        self.sup_nodes = [prev]
        for i, L in enumerate(spans):
            ids = []
            for k in range(1, nseg + 1):
                nd = self.fr.node(x0 + L * k / nseg, 0)
                ids.append(self.fr.elem(prev, nd, 1.0, 1e6, self.EI[i]))
                prev = nd
            self.sup_nodes.append(prev)
            self.span_elems.append(ids)
            x0 += L
        for j, n_ in enumerate(self.sup_nodes):
            t = self.supports[j]
            if t == "fix":
                self.fr.support(n_, True, True, True)
            elif t == "free":
                pass
            else:
                self.fr.support(n_, j == 0 or t == "pinx", True, False)
        if all(not v[0] for v in self.fr.fix.values()):
            self.fr.fix[self.sup_nodes[0]] = (True,) + tuple(self.fr.fix[self.sup_nodes[0]][1:])
        self.x_start = np.cumsum([0] + self.spans)

    def _eloads(self, span_loads):
        """span_loads: {span_index: profile} profile = float (udl) or
        function(xi in [0,1]) -> intensity  (positive downward)"""
        el = {}
        for i, prof in span_loads.items():
            L = self.spans[i]
            ids = self.span_elems[i]
            for k, eid in enumerate(ids):
                if callable(prof):
                    w1, w2 = prof(k / self.nseg), prof((k + 1) / self.nseg)
                else:
                    w1 = w2 = prof
                el[eid] = (-w1, -w2)
        return el

    def solve_case(self, span_loads, point_loads=None):
        nodal = {}
        for (x, P) in (point_loads or []):
            n_ = self.fr.node(x, 0)  # must coincide with an existing node
            nodal[n_] = (0, -P, 0)
        return self.fr.solve(nodal, self._eloads(span_loads))

    def diagrams(self, res, npts=5):
        X, M, V = [], [], []
        for i, ids in enumerate(self.span_elems):
            for eid in ids:
                xs, N_, V_, M_ = res.internal(eid, npts)
                n1 = self.fr.elems[eid].n1
                x0 = self.fr.nodes[n1][0]
                X += list(x0 + xs)
                M += list(M_)
                V += list(V_)
        return np.array(X), np.array(M), np.array(V)

    def reactions(self, res):
        return [res.reaction(n_)[1] for n_ in self.sup_nodes]

    def envelope(self, g_loads, q_loads):
        """g_loads / q_loads: {span: profile}. Variable load acts span by span
        (pattern loading). Returns dict with X, Mg, Mmax, Mmin, Vmax, Vmin,
        reactions max/min, and the single cases."""
        rg = self.solve_case(g_loads)
        X, Mg, Vg = self.diagrams(rg)
        Rg = np.array(self.reactions(rg))
        Mq, Vq, Rq = [], [], []
        for i in q_loads:
            r = self.solve_case({i: q_loads[i]})
            _, m, v = self.diagrams(r)
            Mq.append(m)
            Vq.append(v)
            Rq.append(np.array(self.reactions(r)))
        Mq, Vq, Rq = np.array(Mq), np.array(Vq), np.array(Rq)
        out = dict(
            X=X, Mg=Mg, Vg=Vg,
            Mmax=Mg + np.clip(Mq, 0, None).sum(0), Mmin=Mg + np.clip(Mq, None, 0).sum(0),
            Vmax=Vg + np.clip(Vq, 0, None).sum(0), Vmin=Vg + np.clip(Vq, None, 0).sum(0),
            Rg=Rg, Rmax=Rg + np.clip(Rq, 0, None).sum(0), Rmin=Rg + np.clip(Rq, None, 0).sum(0),
            Mq=Mq, Vq=Vq, Rq=Rq, Mall=Mg + Mq.sum(0), Vall=Vg + Vq.sum(0),
            Rall=Rg + Rq.sum(0), Rq_all=Rq.sum(0),
        )
        return out

    def span_of(self, x):
        for i in range(len(self.spans)):
            if self.x_start[i] - 1e-9 <= x <= self.x_start[i + 1] + 1e-9:
                return i
        return len(self.spans) - 1


# ============================================================================
# Rectangular plates (Levy series)
# ============================================================================
def plate_levy(lx, ly, bc_x0="S", bc_x1="S", nu=0.0, q=1.0, mterms=41, nx=61, ny=31):
    """Plate 0<x<lx, 0<y<ly. Edges y=0, y=ly simply supported; edges x=0 and
    x=lx 'S' (simply supported) or 'C' (clamped). Uniform load q, D = 1.
    Returns dict with max field moments Mx, My (per unit width) and the
    clamped-edge moments (negative) and the share of load carried in x."""
    xs = np.linspace(0, lx, nx)
    ys = np.linspace(0, ly, ny)
    WXX = np.zeros((ny, nx))
    WYY = np.zeros((ny, nx))
    W = np.zeros((ny, nx))
    for m in range(1, mterms + 1, 2):
        al = m * math.pi / ly
        wp = 4 * q / (m * math.pi * al**4)
        # f(x) = (A + B al x) e^{-al x} + (C + D al (lx-x)) e^{-al (lx-x)} + wp
        def rows(x):
            g1, g2 = math.exp(-al * x), math.exp(-al * (lx - x))
            f = [g1, al * x * g1, g2, al * (lx - x) * g2]
            f1 = [-al * g1, al * (1 - al * x) * g1, al * g2, al * (-1 + al * (lx - x)) * g2]
            f2 = [al**2 * g1, al**2 * (al * x - 2) * g1, al**2 * g2,
                  al**2 * (al * (lx - x) - 2) * g2]
            return f, f1, f2
        Amat, rhs = [], []
        for x, bc in ((0.0, bc_x0), (lx, bc_x1)):
            f, f1, f2 = rows(x)
            Amat.append(f)
            rhs.append(-wp)
            if bc == "S":
                Amat.append(f2)
                rhs.append(0.0)
            else:
                Amat.append(f1)
                rhs.append(0.0)
        A, B, C, D = np.linalg.solve(np.array(Amat), np.array(rhs))
        sy = np.sin(al * ys)
        for j, x in enumerate(xs):
            f, f1, f2 = rows(x)
            fv = A * f[0] + B * f[1] + C * f[2] + D * f[3] + wp
            f2v = A * f2[0] + B * f2[1] + C * f2[2] + D * f2[3]
            W[:, j] += fv * sy
            WXX[:, j] += f2v * sy
            WYY[:, j] += -al**2 * fv * sy
    Mx = -(WXX + nu * WYY)
    My = -(WYY + nu * WXX)
    jm = ny // 2
    res = dict(Mx_field=float(Mx.max()), My_field=float(My.max()),
               Mx_edge0=float(Mx[jm, 0]), Mx_edge1=float(Mx[jm, -1]),
               w_max=float(W.max()))
    # share of the load carried in x-direction (from the edge reactions)
    return res


def plate_coeffs(lx, ly, bc_x0, bc_x1, nu=0.0):
    """Moment coefficients: M = p*l^2/m (m_x with lx, m_y with ly)."""
    r = plate_levy(lx, ly, bc_x0, bc_x1, nu)
    out = dict(m_x=lx**2 / r["Mx_field"], m_y=ly**2 / r["My_field"])
    if bc_x0 == "C":
        out["m_x0"] = lx**2 / -r["Mx_edge0"]
    if bc_x1 == "C":
        out["m_x1"] = lx**2 / -r["Mx_edge1"]
    return out
