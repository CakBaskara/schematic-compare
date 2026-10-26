import os
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime

import fitz


@dataclass
class Span:
    page: int
    t: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    font: str
    color: int

    @property
    def cx(self):
        return (self.x0 + self.x1) / 2

    @property
    def cy(self):
        return (self.y0 + self.y1) / 2


@dataclass
class Seg:
    x0: float
    y0: float
    x1: float
    y1: float
    width: float
    dashed: bool

    @property
    def horizontal(self):
        return abs(self.y0 - self.y1) < 0.5

    @property
    def vertical(self):
        return abs(self.x0 - self.x1) < 0.5

    @property
    def length(self):
        return max(abs(self.x1 - self.x0), abs(self.y1 - self.y0))


@dataclass
class Page:
    number: int
    width: float
    height: float
    spans: list
    segs: list
    item_rects: list
    border: tuple
    title_block: tuple = None
    sheet_title: str = ""
    date: str = ""
    rev: str = ""
    title: str = ""
    has_images: bool = False

    def in_title_block(self, x, y):
        tb = self.title_block
        return bool(tb) and tb[0] <= x <= tb[2] and tb[1] <= y <= tb[3]


@dataclass
class Document:
    path: str
    name: str
    pages: list
    meta: dict = field(default_factory=dict)

    @property
    def stem(self):
        return os.path.splitext(self.name)[0]

    def page(self, number):
        return self.pages[number - 1]

    def date(self):
        """Best guess of the schematic date: title-block date, then PDF creation date, then file time."""
        for p in self.pages:
            d = parse_date(p.date)
            if d:
                return d
        m = re.match(r"D:(\d{4})(\d{2})(\d{2})", self.meta.get("creationDate") or "")
        if m:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return datetime.fromtimestamp(os.path.getmtime(self.path))


def parse_date(text):
    text = re.sub(r"^\w+day,\s*", "", (text or "").strip())
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%Y/%m/%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def load(path):
    doc = fitz.open(path)
    pages = []
    for i, p in enumerate(doc):
        spans = _spans(p, i + 1)
        segs, rects = _drawings(p)
        page = Page(number=i + 1, width=p.rect.width, height=p.rect.height, spans=spans, segs=segs,
                    item_rects=rects, border=_inner_border(segs, p.rect.width, p.rect.height),
                    has_images=bool(p.get_images()))
        _title_block(page)
        pages.append(page)
    return Document(path=path, name=os.path.basename(path), pages=pages, meta=dict(doc.metadata or {}))


def _spans(page, number):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for line in b.get("lines", []):
            for s in line["spans"]:
                t = s["text"].strip()
                if not t:
                    continue
                x0, y0, x1, y1 = s["bbox"]
                out.append(Span(number, t, x0, y0, x1, y1, round(s["size"], 2), s["font"], s["color"]))
    return out


def _is_dashed(dashes):
    return bool(dashes) and re.sub(r"\s", "", dashes) not in ("[]0", "")


def _drawings(page):
    segs, rects = [], []
    for path in page.get_drawings():
        width = path.get("width") or 0.0
        dashed = _is_dashed(path.get("dashes"))
        rects.append(tuple(path["rect"]))
        for it in path["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                segs.append(Seg(a.x, a.y, b.x, b.y, width, dashed))
            elif it[0] == "re":
                r = it[1]
                for (ax, ay, bx, by) in ((r.x0, r.y0, r.x1, r.y0), (r.x1, r.y0, r.x1, r.y1),
                                         (r.x0, r.y1, r.x1, r.y1), (r.x0, r.y0, r.x0, r.y1)):
                    segs.append(Seg(ax, ay, bx, by, width, dashed))
            elif it[0] == "qu":
                q = it[1]
                pts = [q.ul, q.ur, q.lr, q.ll, q.ul]
                for a, b in zip(pts, pts[1:]):
                    segs.append(Seg(a.x, a.y, b.x, b.y, width, dashed))
    return segs, rects


def _inner_border(segs, W, H):
    """Schematic sheets draw two nested border frames; the inner one bounds the drawing area."""
    hs = [s for s in segs if s.horizontal and abs(s.x1 - s.x0) > 0.7 * W]
    vs = [s for s in segs if s.vertical and abs(s.y1 - s.y0) > 0.7 * H]

    def pick(values, edge):
        values = sorted(set(round(v, 1) for v in values), key=lambda v: abs(v - edge))
        if not values:
            return edge
        if len(values) >= 2 and abs(values[1] - values[0]) < 15:
            return values[1]
        return values[0]

    x0 = pick([s.x0 for s in vs if s.x0 < W / 2], 0.0)
    x1 = pick([s.x0 for s in vs if s.x0 >= W / 2], W) if any(s.x0 >= W / 2 for s in vs) else W
    y0 = pick([s.y0 for s in hs if s.y0 < H / 2], 0.0)
    y1 = pick([s.y0 for s in hs if s.y0 >= H / 2], H) if any(s.y0 >= H / 2 for s in hs) else H
    return (x0, y0, x1, y1)


def _title_block(page):
    sp = page.spans
    docnum = next((s for s in sp if s.t.lower() == "document number"), None)
    if not docnum:
        return
    title = min((s for s in sp if s.t == "Title" and s.y0 < docnum.y0 and s.x0 < docnum.x0 + 5),
                key=lambda s: docnum.y0 - s.y0, default=None)
    rev = next((s for s in sp if s.t == "Rev" and abs(s.cy - docnum.cy) < 3), None)
    date_lbl = next((s for s in sp if s.t.rstrip(":").lower() == "date" and s.y0 > docnum.y0), None)
    left = min(docnum.x0, title.x0 if title else docnum.x0)
    top = (title.y0 if title else docnum.y0) - 14
    inside = [s for s in sp if s.x0 >= left - 2 and s.y0 >= top]
    page.title_block = (left - 3, top, max(s.x1 for s in inside) + 3, max(s.y1 for s in inside) + 3)

    def below(label):
        # Field values may overlap their label vertically, so compare centres, not edges.
        h = label.y1 - label.y0
        return [s for s in sp if s is not label and s.cy > label.cy + 0.4 * h and s.y0 < label.y1 + 3 * h]

    x_limit = rev.x0 - 2 if rev else page.width
    cand = [s for s in below(docnum) if docnum.x0 - 2 <= s.x0 < x_limit]
    if cand:
        page.sheet_title = max(cand, key=lambda s: (s.size, -s.y0)).t
    if rev:
        rv = [s for s in below(rev) if abs(s.cx - rev.cx) < 12]
        if rv:
            page.rev = min(rv, key=lambda s: s.y0).t
    if date_lbl:
        dv = sorted((s for s in sp if abs(s.cy - date_lbl.cy) < 2 and s.x0 > date_lbl.x1), key=lambda s: s.x0)
        if dv:
            page.date = dv[0].t
    if title:
        tv = [s for s in below(title) if title.x0 - 2 <= s.x0 < x_limit and s is not docnum and s.cy < docnum.cy]
        if tv:
            page.title = max(tv, key=lambda s: s.size).t


def median_width(segs):
    ws = [s.width for s in segs if s.width > 0]
    return statistics.median(ws) if ws else 0.0
