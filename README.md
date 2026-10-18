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
| `Slab_reinforcement_<name>.dxf` | bottom and top reinforcement plans of the slab (M 1:50) and, under them, the reinforcement drawings of all elements – with bar schedules |
| `Reinforcement_<element>_<name>.dxf` | one file per element, with border and title block: `Beam_B21`, `Beam_axis_E_torsion`, `Beam_B5`, `Frame_axis_2`, `Column_C7`, `Column_C10`, `Footing_C7` (M 1:25), `Stairs` (M 1:10) |

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

**Reinforcement plans** – `rc_note/rebar.py` (bar and mesh positions) and `rc_note/dxf_rebar.py`
(drawing). The background is only the outline of the structure (beams, walls, columns, axes,
names and slab numbers – no section marks, dimensions, levels or stairs), in grey.

* Hall slabs 1–6: **welded wire meshes** R131 / R188 / R221 / R257 / R335 / R424 / R524
  (R-type, main bars along the span, sheet 5.00 × 2.15 m). The mesh of every section is chosen in
  section II, part 8 of the note (A_s ≥ A_s,req, deflection checked with the area of the mesh).
  Bottom meshes per panel, top strips over the secondary beams (0.3·l), at the edges A/E and along
  axes 1, 2, 3. Every mesh piece is drawn as a rectangle with a diagonal and the label
  `M<pos> R188 - 2.72/2.11 m` (length along the main bars / width).
* Other slabs: bars – one representative bar per group with its shape and lengths and the label
  `N<pos> <mark> <n>Ø<d>x<L>/<s>` (as in the example: `BR 31Ø8x320/16.67`):

| Slab | Bottom | Top |
|---|---|---|
| meeting room (III) | BR end / interior spans, DR | TR over the beams (support B / interior), TR at 5' and 7, constructive at D/E |
| corridor (I) | BR, DR in 3 pieces with laps (> 12 m) | TR at B/D, constructive at 4/7 |
| offices 19–21 (IV) | BR x and y | TR over axes 5, 6, TR at the edges |
| balconies (IV), canopy 7 (VII) | – | TR cantilever bars + DR |
| slabs 10, 18 | as the offices | TR at the edges |

AR = assembly bars under the top bars (dots on the TR bars). Detailing rules (EC2 9.3):
bottom bars into the supports up to the far face minus the cover, top bars over supports
0.3·l (two-way 0.25·l) beyond the face, end supports A_s3 ≥ max(0.25·A_s; A_s,min; 5Φ8/m)
over 0.2·l, distribution ≥ 0.2·A_s and 3Φ8/m.

The width over which each group of bars or zone of meshes is placed is given with real
**dimension lines** (DIMENSION entities, style `RC_DIM`). Collinear dimensions are chained, so
they touch each other (the width of a beam between two zones is dimensioned too).
Next to each plan: bar schedule, mesh schedule and mass of steel; the same schedules are in
section XII of the note.

**Element details** – `rc_note/details.py`, drawn under the slab plans in the same file and written
again one element per file (`Reinforcement_<element>_<name>.dxf`, border + title block), from the
results of sections V–XI: beam B21 (VI), beam on axis E with torsion (VII), continuous beam B5 (VIII),
column C10 over two storeys (IX), frame on axis 2 with B15 and C7 (C1, C12 as outline) (X), column C7 over
two storeys with its sections (X), pad footing under C7 (XI) and the stairs (V). The drawings of the
elements are also inserted as figures in section XII of the note. Each drawing has the elevation (plan) with bars, links and link zones, dimension
lines, cross-sections, the bars drawn separately with the lengths of their parts, position numbers in
circles and a bar schedule with the mass. Detailing: cover 25 mm (50 mm in the footing), anchorage legs
12Ø, top bars over supports 0.3·l, links 0.6·s in the critical zones of the columns, laps 50Ø.

Also in the element drawings: every bar is drawn separately, the mirrored ones too (each with its
own label); all overlaps of bars (laps over the supports, assembly bars lapped with the support bars,
laps of the column bars above the slabs) are dimensioned; the frame on axis 2 shows the vertical bars of
the columns separately with the lengths of their parts (in the footing, in the storey, in the beam, lap);
beams B21, B5 and the frame beam B15 have the diagram of the tensile force M_Ed/z shifted by a_l = 0.45·d·cotθ, compared
with the force the bars can take (A_s·f_yd per bar), with ΔF_td = 0.5·V_Ed·cotθ.
In the slab plans every overlap is dimensioned too: side laps of the meshes, meshes and bottom bars
overlapping in the beams, laps of the distribution bars.

**Minimum slab thickness 12 cm** – the automatic search of every slab starts at 12 cm, smaller values
given in the input file are raised to 12 cm (with a message); the balconies are 12 cm at the free edge.

Limits of the template:
* the hall must have 3 panels between A and C (true when 2·(b + c/2)/a is between 2
  and 3); otherwise the note is written and the drawings are skipped with a message;
* the stairs, the section marks of the beams (beam depths) and the column outlines are
  those of the template – the real sizes are in the table on the formwork plan;
* the formwork of the stairs is the one of the template (the stair drawing shows the designed flight).

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
| X | Frame on axis 2 | plane frame, 5 storeys; basic load cases G, Q1 (span A-C), Q2 (span C-E), Q3 (chequerwise) with loads and M/V/N diagrams; design combinations as in the manual (12.3): LC1 = 1.35G + 1.5(Q1+Q2) full load, LC2 = 1.35G + 1.5Q1 variable only in the first span, LC3 = 1.35G + 1.5Q3 chequerwise; moment envelope; beam B15; column C7 as in the manual (12.6-12.7): sections 4-4 / 5-5 (first storey) and 6-6 / 7-7 (second storey), effective lengths from the beam/column stiffness, preliminary design for N, slenderness in and out of the plane, A_s^a / A_s^b (in the plane, short sides) / A_s^c (out of the plane, long sides), final bar arrangement, shear and links |
| XI | Pad footing under C7 | plan size from R0 (SLS), height from v_Rd,max, bending, punching |

* Geometry comes from the formwork plan (axes 1–7, 5', A–E): the number of one-way
  panels in the hall and in the meeting room is chosen so that l/l ≥ 2.
* Slab thicknesses, the stair thickness, the depths of beams B5 / B21 / B15 (B15 not
  shallower than B5) and the footing height are **increased automatically** until all checks pass
  (bending, shear, deflection, punching). To fix a size yourself, set it in the
  JSON file (`hf_hall`, `B21_h`, `B15_h`, …; 0 = automatic).
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
