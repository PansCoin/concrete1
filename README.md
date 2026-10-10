# RC course project – explanatory note and drawings generator

Type in the **Input data** from the assignment sheet. The program does all the
calculations and writes the **explanatory note as a Word document (.docx)**
and the **drawings as DXF files** (formwork plan and reinforcement plans of the
slab, made with ezdxf from the results of the calculations). Every
formula is a real Word equation, shown three times: with symbols, with the numbers
substituted, and as the result. The note also contains the static schemes, the
M / V / N diagrams, tables and checks.

## Install (once)

    pip install python-docx matplotlib numpy ezdxf

## Run

    python make_note.py                  # asks for the values on the sheet
    python make_note.py my_input.json    # or reads them from a file
    python make_note.py --example        # writes input_example.json for you to edit
    python make_note.py my_input.json --png      # also PNG previews of the drawings
    python make_note.py my_input.json --no-dxf   # only the Word note

Output, in the current folder:

| File | Content |
|---|---|
| `Explanatory_note_<name>.docx` | the explanatory note (sections I–XI, summary, section XII with the bar schedule) |
| `Formwork_<name>.dxf` | formwork plan of the slab above the first floor, M 1:50 |
| `Slab_reinforcement_<name>.dxf` | bottom and top reinforcement plans of the slab with bar schedules, M 1:50 |

In Word, right-click the table of contents and choose "Update field".
Drawing unit in the DXF files = 1 cm.

## Drawings (DXF)

**Formwork plan** – `rc_note/dxf_formwork.py` (your `formwork_redraw.py`, built in).
The example formwork plan (`templates/formwork_template.dxf`, cut out of the example
drawing with `tools/extract_template.py`) is redrawn on the new grid: walls, columns,
section marks and dimensions move with their axes, only the slab fields are stretched.
The hall beams are re-spaced, meeting-room panels are added or removed (with
renumbering of the slabs and beams), the balconies get the depth d and the canopy
1.25·d. The slab thicknesses `h_f = .. cm` and a table of the element sizes
(slabs, beams, columns, footing) come from the calculations.

**Reinforcement plans** – `rc_note/rebar.py` (bar positions) and `rc_note/dxf_rebar.py`
(drawing). The formwork is the grey background; the bars are drawn the usual way: one
representative bar per group with its shape and lengths, the label
`N<pos> <mark> <n>Ø<d>x<L>/<s>` (as in the example: `BR 31Ø8x320/16.67`) and a range line
with arrows. Diameters and spacings are the ones adopted in the note:

| Slab | Bottom | Top |
|---|---|---|
| hall 1–6 (II) | BR per span, DR distribution | TR over every secondary beam (support moments), TR at axes A/E, constructive TR at axes 1, 2, 3 |
| meeting room (III) | BR end / interior spans, DR | TR over the beams (support B / interior), TR at 5' and 7, constructive at D/E |
| corridor (I) | BR, DR in 3 pieces with laps (> 12 m) | TR at B/D, constructive at 4/7 |
| offices 19–21 (IV) | BR x and y | TR over axes 5, 6, TR at the edges |
| balconies (IV), canopy 7 (VII) | – | TR cantilever bars + DR |
| slabs 10, 18 | as the offices | TR at the edges |

AR = assembly bars under the top bars (dots on the TR bars). Detailing rules (EC2 9.3):
bottom bars into the supports up to the far face minus the cover, top bars over supports
0.3·l (two-way 0.25·l) beyond the face, end supports A_s3 ≥ max(0.25·A_s; A_s,min; 5Φ8/m)
over 0.2·l, distribution ≥ 0.2·A_s and 3Φ8/m. Next to each plan: bar schedule and mass of
steel per diameter; the same schedule is in section XII of the note.

Limits of the template:
* the hall must have 3 panels between A and C (true when 2·(b + c/2)/a is between 2
  and 3); otherwise the note is written and the drawings are skipped with a message;
* the stairs, the section marks of the beams (beam depths) and the column outlines are
  those of the template – the real sizes are in the table on the formwork plan;
* the staircase, beams, columns, frame and footing detail drawings are not generated.

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
* `rc_note/runner.py` – calculations → drawings → Word note
* `rc_note/drawings.py` – writes the DXF files and section XII of the note
* `rc_note/dxf_formwork.py`, `rc_note/rebar.py`, `rc_note/dxf_rebar.py` – see "Drawings"
* `templates/formwork_template.dxf` – the example formwork plan (template)
* `tools/extract_template.py` – cuts the template out of the example drawing
* `rc_note/engine.py` – formulas → Word equations (symbols → numbers → result)
* `rc_note/statics.py` – frame / continuous-beam solver (direct stiffness), plate solver
* `rc_note/design.py` – EC2 design steps (bending, shear, deflection, columns)
* `rc_note/sec_slabs.py`, `sec_members.py`, `sec_frame.py` – sections I–XI
* `rc_note/plots.py` – schemes and diagrams
