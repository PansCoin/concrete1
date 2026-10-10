#!/usr/bin/env python3
"""
extract_template.py - cut the formwork plan out of the example drawing
=====================================================================

The example drawing (formwork + reinforcement examples) holds several plans
in one model space. The formwork plan "Formwork at level +2.90" lies in the
box x = -300 ... 4500, y = -100 ... 3000 (drawing units = cm). This script
keeps only the entities inside that box, removes the block definitions that
are no longer used and writes templates/formwork_template.dxf, the template
that rc_note/dxf_formwork.py redraws for new input data.

    python tools/extract_template.py example.dxf templates/formwork_template.dxf
"""
import sys

import ezdxf
from ezdxf import bbox
from ezdxf.blkrefs import find_unreferenced_blocks

BOX = (-300.0, -100.0, 4500.0, 3000.0)


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
