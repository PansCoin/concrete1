# -*- coding: utf-8 -*-
"""
engine.py - symbolic/numeric expressions that are written into Word as real
equations (Office Math / OMML), first with symbols, then with the numbers
substituted, then the result:

        M_Ed = p·l²/8 = 12.4·2.87²/8 = 12.77 kNm/m

Usage
-----
    p = S("p", 12.4, "kN/m²")          # a symbol with a value
    l = S("l_eff", 2.87, "m")
    M = note.calc("M_Ed", p * l**2 / 8, "kNm/m", "Maximum bending moment")
    # M is again a symbol (M_Ed = 12.77) that can be used in later formulas
"""
from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape

M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

GREEK = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "Delta": "Δ",
    "epsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "lambda": "λ",
    "mu": "μ", "nu": "ν", "xi": "ξ", "rho": "ρ", "sigma": "σ", "Sigma": "Σ",
    "tau": "τ", "phi": "φ", "Phi": "Φ", "chi": "χ", "psi": "ψ", "omega": "ω",
    "pi": "π",
}


# --------------------------------------------------------------------------
# number formatting
# --------------------------------------------------------------------------
def fmt(v: float, digits: int | None = None) -> str:
    """Engineering formatting: about 4 significant digits, no exponent."""
    if v is None:
        return "-"
    if isinstance(v, bool):
        return str(v)
    if v == 0 or abs(v) < 1e-12:
        return "0"
    a = abs(v)
    if digits is not None:
        s = f"{v:.{digits}f}"
    elif a >= 1000:
        s = f"{v:.0f}"
    elif a >= 100:
        s = f"{v:.1f}"
    elif a >= 10:
        s = f"{v:.2f}"
    elif a >= 1:
        s = f"{v:.3f}"
    elif a >= 0.01:
        s = f"{v:.4f}"
    else:
        dec = max(3, -int(math.floor(math.log10(a))) + 2)
        s = f"{v:.{dec}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s in ("-0", ""):
        s = "0"
    return s


# --------------------------------------------------------------------------
# OMML building blocks
# --------------------------------------------------------------------------
def _r(text: str, upright: bool = False, bold: bool = False) -> str:
    rpr = ""
    if upright or bold:
        sty = "b" if bold and not upright else ("bi" if bold else "p")
        rpr = f'<m:rPr><m:sty m:val="{sty}"/></m:rPr>'
    return (f'<m:r>{rpr}<w:rPr><w:rFonts w:ascii="Cambria Math" '
            f'w:hAnsi="Cambria Math"/></w:rPr><m:t xml:space="preserve">'
            f'{escape(text)}</m:t></m:r>')


def _frac(num: str, den: str) -> str:
    return f"<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>"


def _sub(base: str, sub: str) -> str:
    return f"<m:sSub><m:e>{base}</m:e><m:sub>{sub}</m:sub></m:sSub>"


def _sup(base: str, sup: str) -> str:
    return f"<m:sSup><m:e>{base}</m:e><m:sup>{sup}</m:sup></m:sSup>"


def _subsup(base: str, sub: str, sup: str) -> str:
    return (f"<m:sSubSup><m:e>{base}</m:e><m:sub>{sub}</m:sub>"
            f"<m:sup>{sup}</m:sup></m:sSubSup>")


def _rad(inner: str, deg: str | None = None) -> str:
    if deg is None:
        return (f'<m:rad><m:radPr><m:degHide m:val="1"/></m:radPr><m:deg/>'
                f"<m:e>{inner}</m:e></m:rad>")
    return f"<m:rad><m:deg>{deg}</m:deg><m:e>{inner}</m:e></m:rad>"


def _paren(inner: str, beg="(", end=")", sep=None, items=None) -> str:
    pr = f'<m:begChr m:val="{escape(beg)}"/><m:endChr m:val="{escape(end)}"/>'
    if sep is not None:
        pr += f'<m:sepChr m:val="{escape(sep)}"/>'
    if items is not None:
        es = "".join(f"<m:e>{i}</m:e>" for i in items)
    else:
        es = f"<m:e>{inner}</m:e>"
    return f"<m:d><m:dPr>{pr}</m:dPr>{es}</m:d>"


def _greekify(s: str) -> str:
    for k in sorted(GREEK, key=len, reverse=True):
        s = re.sub(rf"(?<![A-Za-z]){k}(?![A-Za-z])", GREEK[k], s)
    return s


def name_omml(name: str) -> str:
    """'M_Ed' -> M with subscript Ed ;  'A_s,req' ; 'l_eff,1' ;
    'gamma_c' -> γ_c ; "x'" ; 'A_s^2' (superscript) ."""
    name = _greekify(name)
    sup = None
    if "^" in name:
        name, sup = name.split("^", 1)
    if "_" in name:
        base, sub = name.split("_", 1)
        # one-letter base italic, subscripts upright (engineering style)
        b = _r(base, upright=len(base) > 1)
        # a zero-width space keeps LibreOffice from reading these as operators
        sub = re.sub(r"(?<![A-Za-z])(lim|sup|inf|min|max)(?![A-Za-z])",
                     lambda m: m.group(1)[0] + "\u200b" + m.group(1)[1:], sub)
        sb = _r(sub, upright=True)
        if sup:
            return _subsup(b, sb, _r(sup, upright=True))
        return _sub(b, sb)
    b = _r(name, upright=len(name) > 1 and not name.isalpha() or len(name) > 2)
    if sup:
        return _sup(b, _r(sup, upright=True))
    return b


# --------------------------------------------------------------------------
# Expression tree
# --------------------------------------------------------------------------
class Ex:
    prec = 100

    # arithmetic -----------------------------------------------------------
    def __add__(self, o):
        return Add(self, wrap(o))

    def __radd__(self, o):
        return Add(wrap(o), self)

    def __sub__(self, o):
        return Sub(self, wrap(o))

    def __rsub__(self, o):
        return Sub(wrap(o), self)

    def __mul__(self, o):
        return Mul(self, wrap(o))

    def __rmul__(self, o):
        return Mul(wrap(o), self)

    def __truediv__(self, o):
        return Div(self, wrap(o))

    def __rtruediv__(self, o):
        return Div(wrap(o), self)

    def __pow__(self, o):
        return Pow(self, wrap(o))

    def __neg__(self):
        return Neg(self)

    # value ----------------------------------------------------------------
    @property
    def v(self) -> float:
        return self.value()

    def __float__(self):
        return float(self.value())

    def value(self) -> float:
        raise NotImplementedError

    def om(self, num: bool) -> str:
        raise NotImplementedError

    def is_atom(self) -> bool:
        return False

    def __repr__(self):
        return f"{type(self).__name__}({self.value():.4g})"


def wrap(x) -> Ex:
    if isinstance(x, Ex):
        return x
    return Num(float(x))


def par(e: Ex, num: bool, need: bool) -> str:
    s = e.om(num)
    return _paren(s) if need else s


class Num(Ex):
    prec = 100

    def __init__(self, v: float, text: str | None = None):
        self._v = float(v)
        self.text = text

    def value(self):
        return self._v

    def om(self, num):
        t = self.text if self.text is not None else fmt(self._v)
        return _r(t, upright=True)

    def is_atom(self):
        return True

    @property
    def negative(self):
        return self._v < 0


class S(Ex):
    """Named quantity with a value (and unit for the report)."""
    prec = 100

    def __init__(self, name: str, value: float, unit: str = "", digits=None):
        self.name = name
        self._v = float(value)
        self.unit = unit
        self.digits = digits

    def value(self):
        return self._v

    def om(self, num):
        if num:
            return _r(fmt(self._v, self.digits), upright=True)
        return name_omml(self.name)

    def is_atom(self):
        return True

    @property
    def negative(self):
        return self._v < 0

    def __format__(self, spec):
        return format(self._v, spec)


def _needs_neg_paren(e: Ex, num: bool) -> bool:
    return num and isinstance(e, (Num, S)) and e.value() < 0


class Add(Ex):
    prec = 1

    def __init__(self, a, b):
        self.a, self.b = a, b

    def value(self):
        return self.a.value() + self.b.value()

    def om(self, num):
        b = self.b
        if num and isinstance(b, (Num, S)) and b.value() < 0:
            # a + (-3)  ->  a - 3
            return (self.a.om(num) + _r("−", True) +
                    _r(fmt(-b.value(), getattr(b, "digits", None)), True))
        return self.a.om(num) + _r("+", True) + par(b, num, _needs_neg_paren(b, num))


class Sub(Ex):
    prec = 1

    def __init__(self, a, b):
        self.a, self.b = a, b

    def value(self):
        return self.a.value() - self.b.value()

    def om(self, num):
        need = self.b.prec <= 1 or _needs_neg_paren(self.b, num)
        return self.a.om(num) + _r("−", True) + par(self.b, num, need)


class Neg(Ex):
    prec = 1.5

    def __init__(self, a):
        self.a = a

    def value(self):
        return -self.a.value()

    def om(self, num):
        return _r("−", True) + par(self.a, num, self.a.prec < 2 or _needs_neg_paren(self.a, num))


class Mul(Ex):
    prec = 2

    def __init__(self, a, b):
        self.a, self.b = a, b

    def value(self):
        return self.a.value() * self.b.value()

    def om(self, num):
        la = par(self.a, num, self.a.prec < 2 or (num and _needs_neg_paren(self.a, num) and False))
        rb = par(self.b, num, self.b.prec < 2 or _needs_neg_paren(self.b, num))
        return la + _r("·", True) + rb


class Div(Ex):
    prec = 3

    def __init__(self, a, b):
        self.a, self.b = a, b

    def value(self):
        d = self.b.value()
        return self.a.value() / d if d != 0 else float("inf")

    def om(self, num):
        return _frac(self.a.om(num), self.b.om(num))


class Pow(Ex):
    prec = 4

    def __init__(self, a, b):
        self.a, self.b = a, b

    def value(self):
        return self.a.value() ** self.b.value()

    def om(self, num):
        base = par(self.a, num, (not self.a.is_atom()) or _needs_neg_paren(self.a, num)
                   or (num and isinstance(self.a, S) and False))
        # an exponent like 0.5 or 1/3 is written as a number / fraction
        if isinstance(self.b, Num):
            v = self.b.value()
            frac = {1 / 3: ("1", "3"), 2 / 3: ("2", "3"), 1.5: ("3", "2"), 0.5: ("1", "2")}
            for k, (n, d) in frac.items():
                if abs(v - k) < 1e-12:
                    return _sup(base, _frac(_r(n, True), _r(d, True)))
            return _sup(base, _r(fmt(v), True))
        return _sup(base, self.b.om(num))


class Fn(Ex):
    prec = 100

    def __init__(self, name, *args):
        self.name = name
        self.args = [wrap(a) for a in args]

    def value(self):
        vs = [a.value() for a in self.args]
        n = self.name
        if n == "sqrt":
            return math.sqrt(vs[0])
        if n == "cbrt":
            return vs[0] ** (1 / 3)
        if n == "min":
            return min(vs)
        if n == "max":
            return max(vs)
        if n == "abs":
            return abs(vs[0])
        if n == "sin":
            return math.sin(math.radians(vs[0]))
        if n == "cos":
            return math.cos(math.radians(vs[0]))
        if n == "tan":
            return math.tan(math.radians(vs[0]))
        if n == "cot":
            return 1 / math.tan(math.radians(vs[0]))
        if n == "atan":
            return math.degrees(math.atan(vs[0]))
        if n == "ln":
            return math.log(vs[0])
        raise ValueError(n)

    def is_atom(self):
        return True

    def om(self, num):
        n = self.name
        if n == "sqrt":
            return _rad(self.args[0].om(num))
        if n == "cbrt":
            return _rad(self.args[0].om(num), _r("3", True))
        if n == "abs":
            return _paren(self.args[0].om(num), "|", "|")
        items = [a.om(num) for a in self.args]
        nm = {"atan": "arctan"}.get(n, n)
        return _r(nm, True) + _paren("", "(", ")", sep=";", items=items)


def sqrt(x):
    return Fn("sqrt", x)


def cbrt(x):
    return Fn("cbrt", x)


def emin(*a):
    return Fn("min", *a)


def emax(*a):
    return Fn("max", *a)


def eabs(x):
    return Fn("abs", x)


def esin(x):
    return Fn("sin", x)


def ecos(x):
    return Fn("cos", x)


def etan(x):
    return Fn("tan", x)


def ecot(x):
    return Fn("cot", x)


def eatan(x):
    return Fn("atan", x)


class P(Ex):
    """Explicit parentheses."""
    prec = 100

    def __init__(self, a):
        self.a = wrap(a)

    def value(self):
        return self.a.value()

    def is_atom(self):
        return True

    def om(self, num):
        return _paren(self.a.om(num))


def N(v, text=None):
    """Plain number in a formula (e.g. 0.5, 1.35, 25)."""
    return Num(v, text)


def _contains_symbol(e: Ex) -> bool:
    if isinstance(e, S):
        return True
    if isinstance(e, Num):
        return False
    for k in ("a", "b"):
        if hasattr(e, k) and _contains_symbol(getattr(e, k)):
            return True
    if isinstance(e, Fn):
        return any(_contains_symbol(a) for a in e.args)
    return False


def equation_xml(lhs_name: str | None, expr: Ex | None, result: float | None,
                 unit: str = "", extra: str = "", show_sym: bool = True,
                 show_num: bool = True, digits=None) -> str:
    """'name = symbolic = substituted = result unit'"""
    parts = []
    if lhs_name:
        parts.append(name_omml(lhs_name))
    eq = _r("=", True)
    if expr is not None:
        is_simple = isinstance(expr, (Num, S))
        if show_sym and not isinstance(expr, Num):
            parts.append(eq + expr.om(False))
        if show_num and not is_simple and _contains_symbol(expr):
            parts.append(eq + expr.om(True))
        elif show_num and not is_simple and not show_sym:
            parts.append(eq + expr.om(True))
        elif not show_sym and not is_simple:
            parts.append(eq + expr.om(True))
    if result is not None:
        u = (_r(" " + unit, True) if unit else "")
        parts.append(eq + _r(fmt(result, digits), True) + u)
    parts.append(extra)
    return "".join(parts)


def math_paragraph_xml(inner: str, align: str = "left") -> str:
    return (f'<m:oMathPara xmlns:m="{M_NS}" xmlns:w="{W_NS}">'
            f'<m:oMathParaPr><m:jc m:val="{align}"/></m:oMathParaPr>'
            f"<m:oMath>{inner}</m:oMath></m:oMathPara>")


def inline_math_xml(inner: str) -> str:
    return f'<m:oMath xmlns:m="{M_NS}" xmlns:w="{W_NS}">{inner}</m:oMath>'


# public helpers for free-form math
def om_text(t, upright=True):
    return _r(t, upright)


def om_name(n):
    return name_omml(n)


def om_rel(op):
    return _r(f" {op} ", True)
