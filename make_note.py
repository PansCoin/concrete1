#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_note.py - RC course project: explanatory note generator
==============================================================

Enter the "Input data" of the assignment sheet and the program writes the
complete explanatory note (sections I - XI) as a Word document, with
every formula written as a Word equation (symbols -> numbers -> result),
the static schemes and the M / V / N diagrams.

Usage
-----
    python make_note.py                      # asks for the values
    python make_note.py my_input.json        # reads them from a file
    python make_note.py --example            # writes input_example.json to edit

Requirements:  pip install python-docx matplotlib numpy
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from rc_note.project import Inputs          # noqa: E402
from rc_note import runner                  # noqa: E402

SHEET = [
    ("student", "Student's name", str),
    ("faculty_no", "Faculty number", str),
    ("date", "Date", str),
    ("a", "a [cm]  (450-650)", float),
    ("b", "b [cm]  (450-650)", float),
    ("c", "c [cm]  (240-360)", float),
    ("d", "d [cm]  (130-180)", float),
    ("hs", "h_s [cm]  (300-380)", float),
    ("hb", "h_b [cm]  (260-300)", float),
    ("qk1", "q_k1 [kN/m2]  (3-7.5) exhibition hall", float),
    ("qk2", "q_k2 [kN/m2]  (3-7.5) meeting room", float),
    ("R0", "R_0 [kN/m2]  (180-250)", float),
]

ADVANCED = [
    ("q_office", "imposed load offices / corridor [kN/m2]", float),
    ("q_stair", "imposed load stairs [kN/m2]", float),
    ("s_k", "snow on the roof [kN/m2]", float),
    ("n_floors", "number of storeys of height h_s above the first storey", int),
    ("fck", "concrete f_ck [MPa]", float),
    ("C7_b", "column C7 b [cm]", float), ("C7_h", "column C7 h [cm]", float),
    ("C1_b", "columns C1/C12 b [cm]", float), ("C1_h", "columns C1/C12 h [cm]", float),
    ("C10_b", "column C10 b [cm]", float), ("C10_h", "column C10 h [cm]", float),
]


def ask(inp: Inputs):
    print("\nEnter the input data from the assignment sheet (Enter = keep the value in [ ]):\n")
    for key, label, typ in SHEET:
        cur = getattr(inp, key)
        s = input(f"  {label} [{cur}]: ").strip()
        if s:
            setattr(inp, key, typ(s.replace(",", ".")) if typ is not str else s)
    s = input("\nChange advanced options (loads not on the sheet, materials, columns)? [y/N]: ")
    if s.strip().lower().startswith("y"):
        for key, label, typ in ADVANCED:
            cur = getattr(inp, key)
            s = input(f"  {label} [{cur}]: ").strip()
            if s:
                setattr(inp, key, typ(s.replace(",", ".")))
    return inp


def main(argv):
    inp = Inputs()
    if "--example" in argv:
        with open("input_example.json", "w", encoding="utf-8") as f:
            json.dump(inp.to_dict(), f, indent=2, ensure_ascii=False)
        print("Written input_example.json - edit it and run:  python make_note.py input_example.json")
        return
    files = [a for a in argv if a.endswith(".json")]
    if files:
        with open(files[0], encoding="utf-8") as f:
            inp = Inputs.from_dict(json.load(f))
    else:
        inp = ask(inp)
    name = (inp.student or "student").replace(" ", "_")
    out = os.path.abspath(f"Explanatory_note_{name}.docx")
    print("\nCalculating ...")
    P = runner.build(inp, out)
    print("\nAutomatically chosen sizes:")
    for line in P.log:
        print("   ", line)
    print(f"\nDone:  {out}")
    print("Open it in Word and right-click the table of contents -> 'Update field'.")


if __name__ == "__main__":
    main(sys.argv[1:])
