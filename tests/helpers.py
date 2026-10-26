from sch_compare.pdfdoc import Document, Page, Seg, Span

NAVY = 0x000080


def span(t, x0, y0, w=None, h=3.9, color=NAVY, size=3.5, font="Helvetica", page=1):
    w = w if w is not None else 1.9 * len(t)
    return Span(page, t, x0, y0, x0 + w, y0 + h, size, font, color)


def fillers(n, y=500):
    return [span(f"GND{i}", 5 + (i % 40) * 15, y + (i // 40) * 6, color=0) for i in range(n)]


def make_doc(spans, segs=(), size=(800, 600), number=1, sheet_title=""):
    # Short thin wires so that the 2.0 frame lines stand out as thick, as on a real sheet.
    wires = [Seg(1 + i, 595, 4 + i, 595, 0.36, False) for i in range(40)]
    page = Page(number=number, width=size[0], height=size[1], spans=list(spans), segs=list(segs) + wires, item_rects=[],
                border=(0, 0, size[0], size[1]), sheet_title=sheet_title)
    return Document(path="fake.pdf", name="fake.pdf", pages=[page])


def hline(x0, x1, y, width=2.0, dashed=False):
    return Seg(x0, y, x1, y, width, dashed)


def vline(x, y0, y1, width=2.0, dashed=False):
    return Seg(x, y0, x, y1, width, dashed)
