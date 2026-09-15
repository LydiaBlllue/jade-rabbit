"""pdfgen.py — the smallest PDF writer the standard library allows: pages of text lines.

Enough to make a statement that pypdf reads back line for line, which is all a parser fixture
has to be. One font (Helvetica), one size, one column; a line longer than the page just runs
off the edge and still comes back whole from the text layer, so nothing here measures text.

    from pdfgen import write_pdf
    write_pdf(path, [["line 1 of page 1", "line 2"], ["page 2"]])
"""


def _esc(s):
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_pdf(path, pages, size=9, leading=11, top=770, left=50):
    objs = []

    def add(o):
        objs.append(o)
        return len(objs)

    font = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    contents = []
    for lines in pages:
        ops = ["BT", f"/F1 {size} Tf", f"{left} {top} Td", f"{leading} TL"]
        for l in lines:
            ops.append(f"({_esc(l)}) Tj T*")
        ops.append("ET")
        stream = "\n".join(ops).encode("latin-1", "replace")
        contents.append(add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream"))
    pages_id = len(objs) + len(pages) + 1
    page_ids = [add(f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font} 0 R >> >> /Contents {c} 0 R >>")
                for c in contents]
    pid = add(f"<< /Type /Pages /Kids [{' '.join(f'{p} 0 R' for p in page_ids)}] /Count {len(page_ids)} >>")
    assert pid == pages_id
    cat = add(f"<< /Type /Catalog /Pages {pid} 0 R >>")

    out = bytearray(b"%PDF-1.4\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += f"{i} 0 obj\n".encode()
        out += o if isinstance(o, bytes) else o.encode("latin-1")
        out += b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for o in offs:
        out += f"{o:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root {cat} 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode()
    with open(path, "wb") as fh:
        fh.write(bytes(out))
    return path
