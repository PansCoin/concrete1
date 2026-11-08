# -*- coding: utf-8 -*-
"""
printout.py - the whole project in one PDF, ready to print
==========================================================

  Project_<name>.pdf      explanatory note (A4) + every drawing sheet at true
                          scale on its ISO paper (formwork and slab plans 1:50,
                          elements 1:25, stairs 1:10)
  Project_<name>_A3.pdf   the same, every drawing reduced to A3 (for a normal
                          office printer; the scale written in the title block
                          is then not valid)

The note is converted with LibreOffice (the table of contents is updated first).
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

A3 = (420.0, 297.0)
MISSING = []

UNO_SCRIPT = r'''
import sys, time, uno
from com.sun.star.beans import PropertyValue

def pv(n, v):
    p = PropertyValue(); p.Name = n; p.Value = v; return p

port, src, dst = int(sys.argv[1]), sys.argv[2], sys.argv[3]
local = uno.getComponentContext()
resolver = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local)
ctx = None
for _ in range(120):
    try:
        ctx = resolver.resolve(f"uno:socket,host=127.0.0.1,port={port};urp;StarOffice.ComponentContext")
        break
    except Exception:
        time.sleep(0.5)
desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(src), "_blank", 0, (pv("Hidden", True),))
for _ in range(2):
    idx = doc.getDocumentIndexes()
    for i in range(idx.getCount()):
        idx.getByIndex(i).update()
    try:
        doc.getTextFields().refresh()
    except Exception:
        pass
doc.storeToURL(uno.systemPathToFileUrl(dst), (pv("FilterName", "writer_pdf_Export"),))
doc.close(True)
try:
    desktop.terminate()
except Exception:
    pass
'''


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def note_to_pdf(docx_path, pdf_path, timeout=300):
    """Explanatory note -> PDF with LibreOffice (table of contents updated).
    Returns the PDF path or None if LibreOffice is not available."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    prog = os.path.dirname(os.path.realpath(soffice))
    if not any(os.path.exists(os.path.join(d, n)) for d in (prog, "/usr/lib/libreoffice/program")
               for n in ("libsmlo.so", "smath", "smath.exe", "libsmlo.dylib")):
        MISSING.append("LibreOffice Math is not installed - the equations of the note would be empty "
                       "(install it, e.g. 'apt install libreoffice-math')")
        return None
    work = tempfile.mkdtemp(prefix="rcnote_pdf_")
    profile = "file://" + os.path.join(work, "profile")
    port = _free_port()
    script = os.path.join(work, "export.py")
    with open(script, "w") as f:
        f.write(UNO_SCRIPT)
    proc = subprocess.Popen([soffice, "--headless", "--invisible", "--nologo", "--norestore",
                             f"-env:UserInstallation={profile}",
                             f"--accept=socket,host=127.0.0.1,port={port};urp;"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    ok = False
    try:
        py = "/usr/bin/python3" if os.path.exists("/usr/bin/python3") else sys.executable
        r = subprocess.run([py, script, str(port), os.path.abspath(docx_path), os.path.abspath(pdf_path)],
                           timeout=timeout, capture_output=True, text=True)
        ok = r.returncode == 0 and os.path.exists(pdf_path)
    except Exception:
        ok = False
    finally:
        try:
            proc.wait(timeout=20)
        except Exception:
            proc.kill()
    if not ok:                                   # plain conversion (table of contents not updated)
        subprocess.run([soffice, "--headless", f"-env:UserInstallation={profile}", "--convert-to", "pdf",
                        "--outdir", work, os.path.abspath(docx_path)], timeout=timeout, capture_output=True)
        cand = os.path.join(work, os.path.splitext(os.path.basename(docx_path))[0] + ".pdf")
        if os.path.exists(cand):
            shutil.move(cand, pdf_path)
            ok = True
    shutil.rmtree(work, ignore_errors=True)
    return pdf_path if ok else None


def drawings_pdf(printout, pdf_path, fit=None):
    """All sheets [(doc, [Sheet])] into one PDF; fit=(W, H) mm reduces bigger sheets to that paper."""
    import matplotlib
    matplotlib.use("Agg")
    from matplotlib.backends.backend_pdf import PdfPages
    from .sheets import sheet_pdf_pages, Sheet
    with PdfPages(pdf_path) as pdf:
        for doc, sheets in printout:
            if fit:
                out = []
                for s in sheets:
                    W, H = (fit if s.W >= s.H else (fit[1], fit[0]))
                    if s.W <= W + 0.5 and s.H <= H + 0.5:
                        out.append(s)
                    else:
                        out.append(Sheet(s.paper, W, H, s.scale, s.rect, s.title, s.content))
                sheets = out
            sheet_pdf_pages(doc, sheets, pdf)
    return pdf_path


def merge(parts, out_path):
    from pypdf import PdfWriter
    w = PdfWriter()
    for p in parts:
        if p and os.path.exists(p):
            w.append(p)
    with open(out_path, "wb") as f:
        w.write(f)
    return out_path


def make(P, note_docx, out_dir, name):
    """Project_<name>.pdf (true scale) and Project_<name>_A3.pdf. Returns the list of files."""
    if not getattr(P, "drawings", None) or not P.drawings.get("sheets"):
        return []
    work = tempfile.mkdtemp(prefix="rcnote_print_")
    MISSING.clear()
    note_pdf = note_to_pdf(note_docx, os.path.join(work, "note.pdf"))
    if note_pdf is None:
        P.warn.append("PDF: " + (MISSING[0] if MISSING else "LibreOffice not found") +
                      " - the PDF contains only the drawings")
    files = []
    for suffix, fit in (("", None), ("_A3", A3)):
        dpdf = drawings_pdf(P.drawings["sheets"], os.path.join(work, f"drawings{suffix}.pdf"), fit=fit)
        out = os.path.join(out_dir, f"Project_{name}{suffix}.pdf")
        merge([note_pdf, dpdf], out)
        files.append(out)
    shutil.rmtree(work, ignore_errors=True)
    return files
