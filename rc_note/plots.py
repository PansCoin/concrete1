# -*- coding: utf-8 -*-
"""plots.py - static schemes and internal force diagrams (matplotlib)."""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import math
import numpy as np  # noqa: E402
from matplotlib.patches import Polygon, Rectangle, Circle, FancyArrowPatch  # noqa: E402

from .engine import fmt  # noqa: E402

BLUE = "#1f5fa8"
RED = "#c0392b"
GREEN = "#1e8449"
GREY = "#555555"


class Plotter:
    def __init__(self, outdir):
        self.outdir = outdir
        os.makedirs(outdir, exist_ok=True)
        self.n = 0

    def _save(self, fig, name):
        self.n += 1
        path = os.path.join(self.outdir, f"{self.n:03d}_{name}.png")
        fig.savefig(path, dpi=170, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return path

    # ------------------------------------------------------------ supports
    @staticmethod
    def _support(ax, x, y, kind, s):
        if kind == "fix":
            ax.plot([x, x], [y - s, y + s], color="k", lw=2)
            for k in np.linspace(-s, s, 5):
                ax.plot([x, x - s * 0.4], [y + k, y + k - s * 0.3], color="k", lw=0.8)
            return
        tri = Polygon([[x, y], [x - s * 0.6, y - s], [x + s * 0.6, y - s]], closed=True,
                      fc="white", ec="k", lw=1.2)
        ax.add_patch(tri)
        if kind == "roller":
            ax.plot([x - s * 0.7, x + s * 0.7], [y - s * 1.25] * 2, color="k", lw=1)
        else:
            for k in np.linspace(-s * 0.6, s * 0.6, 4):
                ax.plot([k + x, k + x - s * 0.25], [y - s, y - s * 1.3], color="k", lw=0.8)

    # --------------------------------------------------------- beam scheme
    def beam_scheme(self, spans, supports, title, loads=None, labels=None,
                    sup_labels=None, name="scheme", point_loads=None, unit="m"):
        """loads: list of (x0, x1, w0, w1, label, color) in m (drawn above)."""
        L = sum(spans)
        fig, ax = plt.subplots(figsize=(10, 2.8))
        s = L * 0.018
        ax.plot([0, L], [0, 0], color="k", lw=2.5)
        xs = np.concatenate([[0], np.cumsum(spans)])
        for i, x in enumerate(xs):
            kind = supports[i] if i < len(supports) else "pin"
            if kind == "free":
                continue
            self._support(ax, x, 0, "fix" if kind == "fix" else ("pin" if i == 0 else "roller"), s)
            if sup_labels:
                ax.text(x, -s * 2.6, sup_labels[i], ha="center", va="top", fontsize=9,
                        fontweight="bold")
        for i, Ls in enumerate(spans):
            ax.annotate("", xy=(xs[i], -s * 4.2), xytext=(xs[i + 1], -s * 4.2),
                        arrowprops=dict(arrowstyle="<->", lw=0.8))
            lab = labels[i] if labels else f"{fmt(Ls)} {unit}"
            ax.text((xs[i] + xs[i + 1]) / 2, -s * 4.0, lab, ha="center", va="bottom", fontsize=8.5)
        top = 0
        if loads:
            h0 = s * 1.2
            for j, (x0, x1, w0, w1, lab, col) in enumerate(loads):
                base = h0 + j * s * 3.4
                hmax = s * 2.4
                wm = max(abs(w0), abs(w1), 1e-9)
                y0, y1 = base + hmax * abs(w0) / wm, base + hmax * abs(w1) / wm
                ax.add_patch(Polygon([[x0, base], [x1, base], [x1, y1], [x0, y0]], closed=True,
                                     fc=col, alpha=0.18, ec=col))
                for xa in np.linspace(x0, x1, max(3, int((x1 - x0) / L * 30))):
                    ya = y0 + (y1 - y0) * (xa - x0) / max(x1 - x0, 1e-9)
                    if ya - base > s * 0.3:
                        ax.annotate("", xy=(xa, base), xytext=(xa, ya),
                                    arrowprops=dict(arrowstyle="->", color=col, lw=0.7))
                ax.text(x1 + L * 0.005, (y0 + y1) / 2, lab, fontsize=8.5, color=col, va="center")
                top = max(top, base + hmax)
        if point_loads:
            for (x, lab) in point_loads:
                ax.annotate("", xy=(x, 0), xytext=(x, s * 4),
                            arrowprops=dict(arrowstyle="->", color=RED, lw=1.6))
                ax.text(x, s * 4.3, lab, ha="center", fontsize=8, color=RED)
                top = max(top, s * 5)
        ax.set_xlim(-L * 0.04, L * 1.12)
        ax.set_ylim(-s * 6, max(top, s * 3) + s * 1.5)
        ax.set_aspect("auto")
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        return self._save(fig, name)

    # ------------------------------------------------------- envelope plot
    def envelope(self, X, Mmax, Mmin, Vmax, Vmin, sup_x, title, name="env",
                 unitM="kNm", unitV="kN", Mlines=None, extra_M=None):
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 6.2), sharex=True)
        for ax in (a1, a2):
            ax.axhline(0, color="k", lw=1)
            for x in sup_x:
                ax.axvline(x, color="#999", lw=0.6, ls=":")
        a1.fill_between(X, 0, Mmax, color=BLUE, alpha=0.15)
        a1.fill_between(X, 0, Mmin, color=RED, alpha=0.12)
        a1.plot(X, Mmax, color=BLUE, lw=1.5, label="max M")
        a1.plot(X, Mmin, color=RED, lw=1.5, label="min M")
        if extra_M is not None:
            a1.plot(X, extra_M, color=GREY, lw=1, ls="--", label="all spans loaded")
        a1.invert_yaxis()   # positive (sagging) moments drawn below the axis
        a1.set_ylabel(f"M [{unitM}]")
        a1.legend(fontsize=8, loc="upper right")
        # annotate extremes in each span and at supports
        for i in range(len(sup_x) - 1):
            m = (X > sup_x[i] + 1e-6) & (X < sup_x[i + 1] - 1e-6)
            if m.any():
                k = np.argmax(np.where(m, Mmax, -1e18))
                a1.annotate(fmt(Mmax[k]), (X[k], Mmax[k]), textcoords="offset points",
                            xytext=(0, 9), ha="center", fontsize=8, color=BLUE)
        for x in sup_x:
            k = np.argmin(abs(X - x))
            if abs(Mmin[k]) > 1e-6 * max(1, abs(Mmax).max()):
                a1.annotate(fmt(Mmin[k]), (X[k], Mmin[k]), textcoords="offset points",
                            xytext=(0, -12), ha="center", fontsize=8, color=RED)
        a2.fill_between(X, 0, Vmax, color=BLUE, alpha=0.15)
        a2.fill_between(X, 0, Vmin, color=RED, alpha=0.12)
        a2.plot(X, Vmax, color=BLUE, lw=1.5, label="max V")
        a2.plot(X, Vmin, color=RED, lw=1.5, label="min V")
        a2.set_ylabel(f"V [{unitV}]")
        a2.set_xlabel("x [m]")
        a2.legend(fontsize=8, loc="upper right")
        for x in sup_x:
            for side in (-1, 1):
                xx = x + side * 1e-4
                k = np.argmin(abs(X - xx))
                for arr, col in ((Vmax, BLUE), (Vmin, RED)):
                    if abs(arr[k]) > 0.02 * max(abs(Vmax).max(), abs(Vmin).max()):
                        pass
        # max |V| labels at supports
        for x in sup_x:
            near = abs(X - x) < (X.max() - X.min()) * 0.01
            if near.any():
                kmax = np.argmax(np.where(near, Vmax, -1e18))
                kmin = np.argmin(np.where(near, Vmin, 1e18))
                if Vmax[kmax] > 1e-6:
                    a2.annotate(fmt(Vmax[kmax]), (X[kmax], Vmax[kmax]), textcoords="offset points",
                                xytext=(4, 2), fontsize=7.5, color=BLUE)
                if Vmin[kmin] < -1e-6:
                    a2.annotate(fmt(Vmin[kmin]), (X[kmin], Vmin[kmin]), textcoords="offset points",
                                xytext=(4, -9), fontsize=7.5, color=RED)
        a1.set_title(title, fontsize=10)
        fig.tight_layout()
        return self._save(fig, name)

    def simple_diagrams(self, X, M, V, title, name="sb", unitM="kNm", unitV="kN"):
        fig, (a1, a2) = plt.subplots(2, 1, figsize=(9, 4.8), sharex=True)
        for ax in (a1, a2):
            ax.axhline(0, color="k", lw=1)
        a1.fill_between(X, 0, M, color=BLUE, alpha=0.18)
        a1.plot(X, M, color=BLUE)
        a1.invert_yaxis()
        k = np.argmax(abs(M))
        a1.annotate(f"max M = {fmt(M[k])}", (X[k], M[k]), textcoords="offset points",
                    xytext=(0, 10), ha="center", fontsize=8.5, color=BLUE)
        a1.set_ylabel(f"M [{unitM}]")
        a2.fill_between(X, 0, V, color=GREEN, alpha=0.18)
        a2.plot(X, V, color=GREEN)
        a2.annotate(fmt(V[0]), (X[0], V[0]), textcoords="offset points", xytext=(4, 0),
                    fontsize=8.5, color=GREEN)
        a2.annotate(fmt(V[-1]), (X[-1], V[-1]), textcoords="offset points", xytext=(-30, 0),
                    fontsize=8.5, color=GREEN)
        a2.set_ylabel(f"V [{unitV}]")
        a2.set_xlabel("x [m]")
        a1.set_title(title, fontsize=10)
        fig.tight_layout()
        return self._save(fig, name)

    # ---------------------------------------------------------- frame plot
    # ------------------------------------------------------------ frames
    @staticmethod
    def _frame_skeleton(ax, fr):
        for e in fr.elems:
            (x1, y1), (x2, y2) = fr.nodes[e.n1], fr.nodes[e.n2]
            ax.plot([x1, x2], [y1, y2], color="k", lw=1.6)
        for n, f in fr.fix.items():
            x, y = fr.nodes[n]
            ax.add_patch(Rectangle((x - 0.25, y - 0.18), 0.5, 0.18, fc="#999", ec="k"))

    @staticmethod
    def _frame_data(fr, res_or_env, kind):
        data = {}
        for ei_, e in enumerate(fr.elems):
            if isinstance(res_or_env, dict):
                data[ei_] = res_or_env[ei_]
            else:
                xs, N, V, M = res_or_env.internal(ei_, 11)
                data[ei_] = (xs, {"M": M, "V": V, "N": N}[kind])
        return data

    def _frame_diagram(self, ax, fr, data, kind, scale=None, label_min=0.0, fs=6.5, color=None):
        """draw a diagram on ax; data {elem: (xs, values)} or {elem: (xs, vmax, vmin)} (envelope)"""
        vmax = 1e-9
        for v in data.values():
            for arr in v[1:]:
                vmax = max(vmax, np.abs(arr).max())
        W = max(x for x, _ in fr.nodes) - min(x for x, _ in fr.nodes)
        Hh = max(y for _, y in fr.nodes) - min(y for _, y in fr.nodes)
        sc = scale or 0.11 * max(W, Hh) / vmax
        sgn = 1 if kind in ("M", "Menv") else -1
        cols = color or {"M": BLUE, "Menv": BLUE, "V": GREEN, "N": "#8e44ad"}[kind]
        for ei_, e in enumerate(fr.elems):
            L, c, s = fr.geom(e)
            x1, y1 = fr.nodes[e.n1]
            nx, ny = s, -c
            xs = data[ei_][0]
            bx, by = x1 + c * xs, y1 + s * xs
            for k, vals in enumerate(data[ei_][1:]):
                col = cols if kind != "Menv" else (RED if k == 0 else BLUE)
                px = bx + sgn * nx * vals * sc
                py = by + sgn * ny * vals * sc
                ax.fill(np.concatenate([bx, px[::-1]]), np.concatenate([by, py[::-1]]),
                        color=col, alpha=0.25 if kind != "Menv" else 0.18, lw=0)
                ax.plot(px, py, color=col, lw=0.9)
        # labels: columns at their ends, beams at the column faces (+ max span moment, N once per span)
        colx = sorted({round(fr.nodes[n][0], 6) for n in fr.fix})
        lab = {}          # key -> (x, y, text)
        span_best = {}    # (y, span, k) -> (value, x, y)
        for ei_, e in enumerate(fr.elems):
            if not e.tag:
                continue
            L, c, s = fr.geom(e)
            x1, y1 = fr.nodes[e.n1]
            nx, ny = (s, -c) if sgn > 0 else (-s, c)
            xs = data[ei_][0]
            horiz = abs(c) > 0.5
            series = list(data[ei_][1:])
            if kind == "Menv" and not horiz:      # columns: the governing value only
                series = [np.where(np.abs(series[0]) >= np.abs(series[1]), series[0], series[1])]
            for kk, vals in enumerate(series):
                if horiz:
                    picks = [k for k in (0, len(vals) - 1) if round(x1 + c * xs[k], 6) in colx]
                    if kind == "Menv" and kk == 0:   # beams: max in the span, min at the supports
                        picks = []
                    xm = x1 + c * xs[len(xs) // 2]
                    sp = sum(1 for xc in colx if xc < xm)
                    if kind in ("M", "Menv"):
                        k = int(np.argmax(vals)) if kk == 0 else int(np.argmin(vals))
                        key = (round(y1, 2), sp, kk)
                        if kind == "M" or kk == 0:
                            if key not in span_best or vals[k] > span_best[key][0]:
                                span_best[key] = (vals[k], x1 + c * xs[k] + nx * vals[k] * sc,
                                                  y1 + s * xs[k] + ny * vals[k] * sc)
                    elif kind == "N":
                        key = (round(y1, 2), sp, 0)
                        span_best.setdefault(key, (vals[len(vals) // 2], xm, y1 + 0.25))
                        picks = []
                else:
                    picks = [0] if e.tag.endswith("|s") else ([len(vals) - 1] if e.tag.endswith("|e") else [])
                for k in picks:
                    v = vals[k]
                    if abs(v) < label_min or abs(v) < 0.03 * vmax:
                        continue
                    # column labels moved into the column, away from the joint
                    t_ = xs[k] + (0 if horiz else (0.35 if k == 0 else -0.35))
                    px, py = x1 + c * t_ + nx * v * sc, y1 + s * t_ + ny * v * sc
                    lab[(round(px, 1), round(py, 1), round(v, 0))] = (px, py, fmt(v), v)
        for v, px, py in span_best.values():
            if abs(v) >= 0.03 * vmax:
                lab[(round(px, 1), round(py, 1), round(v, 0))] = (px, py, fmt(v), v)
        kept = []
        for px, py, t, v in lab.values():
            if any(abs(v - w) < 0.05 and math.hypot(px - qx, py - qy) < 1.0 for qx, qy, w in kept):
                continue
            kept.append((px, py, v))
            ax.text(px, py, t, fontsize=fs, ha="center", va="center", color="k",
                    bbox=dict(fc="white", ec="none", alpha=0.7, pad=0.3))

    def _frame_loads(self, ax, levels, xs, point_loads, udls=(), fs=6.3, arrow=0.9):
        for (x, y, lab, col) in point_loads:
            ax.annotate("", xy=(x, y), xytext=(x, y + arrow),
                        arrowprops=dict(arrowstyle="->", color=col, lw=1.2))
            ax.text(x, y + arrow * 1.05, lab, ha="center", fontsize=fs, color=col, va="bottom",
                    bbox=dict(fc="white", ec="none", alpha=0.8, pad=0.2))
        for (x0, x1, y, lab, col) in udls:
            t = 0.25 * arrow
            ax.add_patch(Rectangle((x0, y + 0.05), x1 - x0, t, fc=col, ec=col, alpha=0.25, lw=0.6))
            ax.text(x0 + 0.3, y + 0.08 + t, lab, fontsize=fs, color=col, va="bottom")
        for y in levels[1:]:
            ax.text(xs[-1] + 0.4, y, f"+{y:.2f}", fontsize=fs + 0.7, va="center")
        ax.plot([xs[0]], [levels[-1] + 2.2 * arrow], alpha=0)

    def frame(self, fr, res_or_env, kind, title, name="frame", scale=None, unit="kNm",
              label_min=0.0, nodes_loads=None):
        """kind: 'M', 'V', 'N', 'Menv' ; res_or_env: Result object, or dict
        {elem: (xs, values)} ({elem: (xs, max, min)} for 'Menv')."""
        fig, ax = plt.subplots(figsize=(9, 8))
        self._frame_skeleton(ax, fr)
        self._frame_diagram(ax, fr, self._frame_data(fr, res_or_env, kind), kind, scale, label_min)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        return self._save(fig, name)

    def frame_loads(self, fr, levels, xs, point_loads, udl_label, title, name="frame_loads", udls=()):
        """sketch of the frame with point loads (list of (x, y, label, color)) and
        distributed loads (list of (x0, x1, y, label, color))."""
        fig, ax = plt.subplots(figsize=(9, 8))
        self._frame_skeleton(ax, fr)
        self._frame_loads(ax, levels, xs, point_loads, udls)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        return self._save(fig, name)

    def frame_case(self, fr, levels, xs, point_loads, udls, data, title, name="frame_case",
                   titles=("Loads [kN, kN/m]", "M [kNm]", "V [kN]", "N [kN]")):
        """one load case / combination on one figure: load scheme, M, V and N diagrams (2 x 2).
        data: {"M": {elem: (xs, vals)}, "V": ..., "N": ...}"""
        fig, axs = plt.subplots(2, 2, figsize=(11, 11))
        ax = axs[0][0]
        self._frame_skeleton(ax, fr)
        self._frame_loads(ax, levels, xs, point_loads, udls, fs=6.5, arrow=0.9)
        ax.set_title(titles[0], fontsize=10)
        for ax, kind, t in ((axs[0][1], "M", titles[1]), (axs[1][0], "V", titles[2]), (axs[1][1], "N", titles[3])):
            self._frame_skeleton(ax, fr)
            self._frame_diagram(ax, fr, data[kind], kind, fs=6.5)
            ax.set_title(t, fontsize=10)
        for ax in axs.flat:
            ax.set_aspect("equal")
            ax.axis("off")
        fig.suptitle(title, fontsize=11)
        fig.tight_layout()
        return self._save(fig, name)

    # --------------------------------------------------------- sketches
    def slab_plan(self, rects, title, name="plan", arrows=None, dims=None):
        """rects: list of (x, y, w, h, label, facecolor)"""
        fig, ax = plt.subplots(figsize=(9, 5))
        for (x, y, w, h, lab, fc) in rects:
            ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec="k", lw=1))
            ax.text(x + w / 2, y + h / 2, lab, ha="center", va="center", fontsize=9)
        for (x0, y0, x1, y1, lab) in (arrows or []):
            ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                        arrowprops=dict(arrowstyle="<->", color=RED, lw=1))
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, lab, color=RED, fontsize=8,
                    ha="center", va="bottom")
        ax.set_aspect("equal")
        ax.autoscale()
        ax.margins(0.08)
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        return self._save(fig, name)

    def section(self, b, h, bars_bot, bars_top=0, phi_b=12, phi_t=10, hf=None, beff=None,
                title="", name="section", stirrup=True, cover=25):
        """rectangular / T section sketch, dimensions in mm"""
        fig, ax = plt.subplots(figsize=(3.6, 3.6))
        if hf and beff and beff > b:
            pts = [(-beff / 2, h), (beff / 2, h), (beff / 2, h - hf), (b / 2, h - hf), (b / 2, 0),
                   (-b / 2, 0), (-b / 2, h - hf), (-beff / 2, h - hf)]
            ax.add_patch(Polygon(pts, closed=True, fc="#e8e8e8", ec="k"))
            W = beff
        else:
            ax.add_patch(Rectangle((-b / 2, 0), b, h, fc="#e8e8e8", ec="k"))
            W = b
        c = cover + 8
        if stirrup:
            ax.add_patch(Rectangle((-b / 2 + cover, cover), b - 2 * cover, h - 2 * cover,
                                   fc="none", ec=GREY, lw=1))
        for n, phi, y in ((bars_bot, phi_b, c + phi_b / 2), (bars_top, phi_t, h - c - phi_t / 2)):
            if n <= 0:
                continue
            xs = np.linspace(-b / 2 + c + phi / 2, b / 2 - c - phi / 2, n) if n > 1 else [0]
            for x in xs:
                ax.add_patch(Circle((x, y), phi / 2, fc="k"))
        ax.text(0, -h * 0.08, f"b = {fmt(b)} mm", ha="center", fontsize=8)
        ax.text(W / 2 + 15, h / 2, f"h = {fmt(h)} mm", rotation=90, va="center", fontsize=8)
        ax.set_xlim(-W / 2 - 60, W / 2 + 90)
        ax.set_ylim(-h * 0.15, h * 1.08)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=9)
        return self._save(fig, name)

    def column_section(self, b, h, n_bars, phi, title, name="col", layout=None):
        """layout=(n_long, n_mid): n_long bars along each horizontal side (corners included),
        n_mid extra bars on each vertical side, with cross ties (frame column)."""
        fig, ax = plt.subplots(figsize=(3.4, 3.8) if layout is None else (4.6, 3.2))
        ax.add_patch(Rectangle((-b / 2, -h / 2), b, h, fc="#e8e8e8", ec="k"))
        c = 45
        ax.add_patch(Rectangle((-b / 2 + 30, -h / 2 + 30), b - 60, h - 60, fc="none", ec=GREY))
        if layout is not None:
            nl, nm = layout
            xs = [-b / 2 + c + (b - 2 * c) * i / (nl - 1) for i in range(nl)]
            ys = [-h / 2 + c + (h - 2 * c) * i / (nm + 1) for i in range(1, nm + 1)]
            pts = [(x, y) for x in xs for y in (-h / 2 + c, h / 2 - c)] + \
                  [(x, y) for x in (-b / 2 + c, b / 2 - c) for y in ys]
            for x in xs[1:-1]:
                ax.plot([x, x], [-h / 2 + 30, h / 2 - 30], color=GREY, lw=0.8)
            for y in ys:
                ax.plot([-b / 2 + 30, b / 2 - 30], [y, y], color=GREY, lw=0.8)
            for (x, y) in pts:
                ax.add_patch(Circle((x, y), phi / 2, fc="k"))
            n_bars = 0
        # distribute bars around perimeter (corners first)
        pts = [(-b / 2 + c, -h / 2 + c), (b / 2 - c, -h / 2 + c), (b / 2 - c, h / 2 - c),
               (-b / 2 + c, h / 2 - c)] if n_bars else []
        rest = n_bars - 4
        side = []
        if rest > 0:
            k = rest // 2
            for i in range(1, k + 1):
                y = -h / 2 + c + (h - 2 * c) * i / (k + 1)
                side += [(-b / 2 + c, y), (b / 2 - c, y)]
        for (x, y) in pts + side[:max(rest, 0)]:
            ax.add_patch(Circle((x, y), phi / 2, fc="k"))
        ax.text(0, -h / 2 - 40, f"{fmt(b)} mm", ha="center", fontsize=8)
        ax.text(b / 2 + 25, 0, f"{fmt(h)} mm", rotation=90, va="center", fontsize=8)
        ax.set_xlim(-b / 2 - 40, b / 2 + 80)
        ax.set_ylim(-h / 2 - 80, h / 2 + 40)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=9)
        return self._save(fig, name)

    def stair(self, n_steps, tread, riser, l_land, title, name="stair"):
        fig, ax = plt.subplots(figsize=(9, 3.6))
        x, y = 0.0, 0.0
        pts = [(0, 0)]
        for i in range(n_steps):
            pts += [(x, y + riser), (x + tread, y + riser)]
            x += tread
            y += riser
        pts += [(x + l_land, y)]
        P = np.array(pts)
        ax.plot(P[:, 0], P[:, 1], color="k", lw=1.2)
        ax.plot([0, x], [-0.16, y - 0.16], color="k", lw=1.2)
        ax.plot([x, x + l_land], [y - 0.16, y - 0.16], color="k", lw=1.2)
        ax.annotate("", xy=(0, -0.5), xytext=(x, -0.5), arrowprops=dict(arrowstyle="<->"))
        ax.text(x / 2, -0.47, f"{fmt(x)} m (flight)", ha="center", fontsize=8)
        ax.annotate("", xy=(x, -0.5), xytext=(x + l_land, -0.5), arrowprops=dict(arrowstyle="<->"))
        ax.text(x + l_land / 2, -0.47, f"{fmt(l_land)} m (landing)", ha="center", fontsize=8)
        self._support(ax, 0, -0.16, "pin", 0.1)
        self._support(ax, x + l_land, y - 0.16, "roller", 0.1)
        ax.set_aspect("equal")
        ax.axis("off")
        ax.set_title(title, fontsize=10)
        return self._save(fig, name)

    def footing(self, Lf, Bf, hc, bc, Hf, title, name="footing"):
        fig, (a1, a2) = plt.subplots(1, 2, figsize=(9, 4))
        a1.add_patch(Rectangle((-Lf / 2, -Bf / 2), Lf, Bf, fc="#eee", ec="k"))
        a1.add_patch(Rectangle((-hc / 2, -bc / 2), hc, bc, fc="#999", ec="k"))
        a1.text(0, -Bf / 2 - 12, f"L = {fmt(Lf)} cm", ha="center", va="top", fontsize=8)
        a1.text(Lf / 2 + 8, 0, f"B = {fmt(Bf)} cm", rotation=90, va="center", fontsize=8)
        a1.set_xlim(-Lf / 2 - 30, Lf / 2 + 40)
        a1.set_ylim(-Bf / 2 - 40, Bf / 2 + 20)
        a1.set_aspect("equal")
        a1.axis("off")
        a1.set_title("Plan", fontsize=9)
        a2.add_patch(Rectangle((-Lf / 2, 0), Lf, Hf, fc="#eee", ec="k"))
        a2.add_patch(Rectangle((-hc / 2, Hf), hc, Hf * 1.2, fc="#999", ec="k"))
        a2.text(Lf / 2 + 8, Hf / 2, f"H = {fmt(Hf)} cm", rotation=90, va="center", fontsize=8)
        a2.set_xlim(-Lf / 2 - 30, Lf / 2 + 40)
        a2.set_ylim(-20, Hf * 2.4)
        a2.set_aspect("equal")
        a2.axis("off")
        a2.set_title("Section", fontsize=9)
        fig.suptitle(title, fontsize=10)
        return self._save(fig, name)
