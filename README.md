# RC course project – explanatory note generator

Type in the **Input data** from the assignment sheet. The program does all the
calculations and writes the **explanatory note as a Word document (.docx)**. Every
formula is a real Word equation, shown three times: with symbols, with the numbers
substituted, and as the result. The note also contains the static schemes, the
M / V / N diagrams, tables and checks.

## Install (once)

    pip install python-docx matplotlib numpy

## Run

    python make_note.py                  # asks for the values on the sheet
    python make_note.py my_input.json    # or reads them from a file
    python make_note.py --example        # writes input_example.json for you to edit

Output: `Explanatory_note_<name>.docx` in the current folder. In Word, right-click
the table of contents and choose "Update field".

## What is calculated (same order as the course)

| Section | Element | Method |
|---|---|---|
| I | Corridor slab (B–D, span c) | simply supported, one-way |
| II | Hall slabs 1–6 | continuous, **elastic**: stiffness method + pattern loading → exact envelopes, written as α-coefficients |
| III | Meeting-room slabs 11–16 | continuous, **plastic** (p·l²/11, p·l²/16), x_u/d ≤ 0.25 |
| IV | Office slabs (two-way) + balconies | plate theory (Lévy series, ν = 0) = basis of the Marcus/Czerny tables |
| V | Stairs | inclined simply supported slab, flight + landing |
| VI | Beam B21 | simply supported T-beam, triangular/trapezoidal slab load, links, flange shear, **deflection by curvatures** (EC2 7.4.3) |
| VII | Beam on axis E (3–4) | bending + torsion (EC2 6.3) |
| VIII | Beam B5–B9 | 2-span continuous T-beam, envelopes, hanger reinforcement |
| IX | Column C10 | normal forces floor by floor, α_n reduction, 2nd-order effects, N–M interaction |
| X | Frame on axis 2 | plane frame, 5 storeys, 3 load cases (all spans + two chequerboards), beam B15 + columns C7, C1 |
| XI | Pad footing under C7 | plan size from R0 (SLS), height from v_Rd,max, bending, punching |

* Geometry comes from the formwork plan (axes 1–7, 5', A–E): the number of one-way
  panels in the hall and in the meeting room is chosen so that l/l ≥ 2.
* Slab thicknesses, the stair thickness, the depths of beams B5 / B21 and the
  footing height are **increased automatically** until all checks pass
  (bending, shear, deflection, punching). To fix a size yourself, set it in the
  JSON file (`hf_hall`, `B21_h`, …; 0 = automatic).
* Codes: EN 1990, EN 1991-1-1, EN 1992-1-1 with the recommended values;
  C25/30, B500, γ_G = 1.35, γ_Q = 1.5.

## Extra input (not on the sheet, course values by default)

`q_office` 3.5, `q_stair` 3.0, `q_balcony` 3.0, `s_k` 1.0 kN/m², `n_floors` 4,
`fck` 25, column sizes C1/C12 40/60, C7 40/80, C10 25/60 cm, beam widths 25 / 30 cm.

## Files

* `make_note.py` – start here
* `rc_note/engine.py` – formulas → Word equations (symbols → numbers → result)
* `rc_note/statics.py` – frame / continuous-beam solver (direct stiffness), plate solver
* `rc_note/design.py` – EC2 design steps (bending, shear, deflection, columns)
* `rc_note/sec_slabs.py`, `sec_members.py`, `sec_frame.py` – sections I–XI
* `rc_note/plots.py` – schemes and diagrams
