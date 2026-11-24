#!/usr/bin/env python3
"""
extract_template.py - cut the formwork plan out of the example drawing
=====================================================================

The example drawing (formwork + reinforcement examples) holds several plans
in one model space. The formwork plan "Formwork at level +2.90" lies in the
box x = -300 ... 4500, y = -100 ... 3000 (drawing units = cm). This script
keeps only the entities inside that box, removes the block definitions that
are no longer used and writes templates/formwork_template.dxf, the template
that rc_note/dxf_formwork.py redraws for new input data. A few drafting slips of
the example are corrected on the way (DRAFTING_FIXES).

    python tools/extract_template.py example.dxf templates/formwork_template.dxf
"""
import sys

import ezdxf
from ezdxf import bbox
from ezdxf.blkrefs import find_unreferenced_blocks

BOX = (-300.0, -100.0, 4500.0, 3000.0)

# drafting slips of the example: entity handle -> [(axis 0 = x / 1 = y, old value, new value)]
FACE_B = 1190.63673439375        # face of SW4 towards the corridor (axis B + 12.5)
SW_END = 3542.91335962981        # free end of SW3 / SW4: 3867.9 - 325 (the labels say 325/25)
DRAFTING_FIXES = {
    # SW4: hatch and outline rose 8.5 cm towards axis 7 (a wedge); hatch ended 1 cm, outline
    # 4 cm off the labelled end; the hole of the hatch did not match the section drawn across
    "CDC5": [(1, 1199.1367, FACE_B), (0, 3543.9134, SW_END), (0, 3575.5016, 3570.501570555634),
             (0, 3654.9051, 3648.601570554534)],
    "CDC6": [(1, 1199.1367, FACE_B)],
    "CDCB": [(1, 1199.4680, FACE_B)],
    "CDC7": [(0, 3538.9134, SW_END)], "CDC8": [(0, 3538.9134, SW_END)], "CDC9": [(0, 3538.9134, SW_END)],
    "D257": [(0, 3538.9134, SW_END)], "D258": [(0, 3538.9134, SW_END)],     # beam faces up to SW4
    # hidden face line on axis 7 above SW4: down to the wall face, and clear of the section mark
    # of the corridor (touching it, the corner of SW4 moved with that mark)
    "CCD5": [(1, 1199.1316, FACE_B), (1, 1256.6455, 1235.0)],
    # SW3: outline 4.5 cm, hatch 0.5 cm off the labelled end; hole of the hatch vs. section
    "CD30": [(0, 3543.4150, SW_END), (0, 3621.5571, 3616.556971030941), (0, 3654.9051, 3694.656971029826)],
    "CDC0": [(0, 3538.4150, SW_END)], "CDC1": [(0, 3538.4150, SW_END)], "CDC2": [(0, 3538.4150, SW_END)],
    # SW2: hole of the hatch 5 cm off the section drawn across the wall
    "CD2C": [(0, 2106.2526, 2101.25255892825), (0, 2171.9051, 2167.678994993947)],
}


def _fix(v, fixes, tol=0.01):
    v = list(v)
    for ax, old, new in fixes:
        if abs(v[ax] - old) < tol:
            v[ax] = new
    return v


def fix_drafting(doc):
    """apply DRAFTING_FIXES (LINE ends, HATCH boundary vertices / line edges)"""
    n = 0
    for handle, fixes in DRAFTING_FIXES.items():
        e = doc.entitydb.get(handle)
        if e is None:
            print(f"drafting fix: {handle} not found")
            continue
        n += 1
        if e.dxftype() == "LINE":
            e.dxf.start = _fix(e.dxf.start, fixes)
            e.dxf.end = _fix(e.dxf.end, fixes)
        elif e.dxftype() == "HATCH":
            for p in e.paths:
                if hasattr(p, "vertices"):
                    p.vertices = [tuple(_fix(v[:2], fixes)) + tuple(v[2:]) for v in p.vertices]
                else:
                    for ed in p.edges:
                        if hasattr(ed, "start") and hasattr(ed, "end"):
                            ed.start = tuple(_fix(ed.start, fixes))
                            ed.end = tuple(_fix(ed.end, fixes))
    return n


def main(src, dst):
    doc = ezdxf.readfile(src)
    msp = doc.modelspace()
    cache = bbox.Cache()
    drop = []
    for e in msp:
        bb = bbox.extents([e], cache=cache)
        if not bb.has_data:
            drop.append(e)
            continue
        if not (BOX[0] <= bb.extmin.x and bb.extmax.x <= BOX[2] and
                BOX[1] <= bb.extmin.y and bb.extmax.y <= BOX[3]):
            drop.append(e)
    for e in drop:
        msp.delete_entity(e)
    fix_drafting(doc)
    for layout in doc.layouts:                      # paper space is not used
        if layout.name != "Model":
            for e in list(layout):
                if e.dxftype() != "VIEWPORT":
                    layout.delete_entity(e)
    while True:                                     # purge unused blocks
        names = [n for n in find_unreferenced_blocks(doc)
                 if not n.lower().startswith(("*model_space", "*paper_space"))
                 and n in doc.blocks]
        if not names:
            break
        for n in names:
            doc.blocks.delete_block(n, safe=False)
    doc.header["$EXTMIN"] = (BOX[0], BOX[1], 0)
    doc.header["$EXTMAX"] = (BOX[2], BOX[3], 0)
    doc.saveas(dst)
    print(f"kept {len(msp)} entities, {len(doc.blocks)} blocks -> {dst}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
