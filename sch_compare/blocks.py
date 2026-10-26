import re
from dataclasses import dataclass, field

from .pdfdoc import Seg, median_width
from .parts import natkey, prefix


@dataclass
class Block:
    side: str
    page: int
    key: str
    name: str
    auto_name: str
    region: tuple
    crop: tuple = None
    refs: list = field(default_factory=list)
    titled: bool = True


def clean_heading(t):
    t = re.sub(r"[^\x20-\x7e]", " ", t)
    t = re.sub(r"\s+", " ", t).strip(" /-:")
    return t if len(re.findall(r"[A-Za-z]", t)) >= 2 else ""


def norm_name(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _merge_collinear(segs, horizontal):
    """Join pieces of one frame line drawn as several segments."""
    rows = {}
    for s in segs:
        k = round(s.y0 if horizontal else s.x0, 0)
        a, b = (min(s.x0, s.x1), max(s.x0, s.x1)) if horizontal else (min(s.y0, s.y1), max(s.y0, s.y1))
        rows.setdefault(k, []).append([a, b, s.width])
    out = []
    for k, items in rows.items():
        items.sort()
        cur = items[0]
        for a, b, w in items[1:]:
            if a <= cur[1] + 1.5:
                cur[1] = max(cur[1], b)
            else:
                out.append((k, cur[0], cur[1], cur[2]))
                cur = [a, b, w]
        out.append((k, cur[0], cur[1], cur[2]))
    if horizontal:
        return [Seg(a, k, b, k, w, False) for k, a, b, w in out]
    return [Seg(k, a, k, b, w, False) for k, a, b, w in out]


def _extend(hl, vl, border):
    """A frame line that stops in empty space is treated as running on to the next frame line or the border."""
    bx0, by0, bx1, by1 = border

    def touches_v(x, y):
        return abs(x - bx0) < 3 or abs(x - bx1) < 3 or any(abs(v.x0 - x) < 3 and v.y0 - 3 <= y <= v.y1 + 3 for v in vl)

    def touches_h(x, y):
        return abs(y - by0) < 3 or abs(y - by1) < 3 or any(abs(h.y0 - y) < 3 and h.x0 - 3 <= x <= h.x1 + 3 for h in hl)

    new_h = []
    for h in hl:
        x0, x1 = h.x0, h.x1
        if not touches_v(x0, h.y0):
            x0 = max([v.x0 for v in vl if v.x0 < x0 and v.y0 - 1 <= h.y0 <= v.y1 + 1] + [bx0])
        if not touches_v(x1, h.y0):
            x1 = min([v.x0 for v in vl if v.x0 > x1 and v.y0 - 1 <= h.y0 <= v.y1 + 1] + [bx1])
        new_h.append(Seg(x0, h.y0, x1, h.y0, h.width, False))
    new_v = []
    for v in vl:
        y0, y1 = v.y0, v.y1
        if not touches_h(v.x0, y0):
            y0 = max([h.y0 for h in new_h if h.y0 < y0 and h.x0 - 1 <= v.x0 <= h.x1 + 1] + [by0])
        if not touches_h(v.x0, y1):
            y1 = min([h.y0 for h in new_h if h.y0 > y1 and h.x0 - 1 <= v.x0 <= h.x1 + 1] + [by1])
        new_v.append(Seg(v.x0, y0, v.x0, y1, v.width, False))
    return new_h, new_v


def frame_lines(page):
    thick = max(1.5, 4 * median_width(page.segs))
    hl = _merge_collinear([s for s in page.segs if s.horizontal and s.width >= thick and s.length > 20], True)
    vl = _merge_collinear([s for s in page.segs if s.vertical and s.width >= thick and s.length > 20], False)
    return _extend(hl, vl, page.border)


def dashed_partitions(page, hl, vl):
    """Dashed lines that split a frame: big closed dashed boxes, or long dashed lines joined to a frame line."""
    dh = _merge_collinear([s for s in page.segs if s.horizontal and s.dashed and s.length >= 10], True)
    dv = _merge_collinear([s for s in page.segs if s.vertical and s.dashed and s.length >= 10], False)
    keep_h, keep_v = set(), set()
    for i, top in enumerate(dh):
        for j, bot in enumerate(dh):
            if bot.y0 <= top.y0 + 10 or abs(top.x0 - bot.x0) > 2 or abs(top.x1 - bot.x1) > 2:
                continue
            sides = [k for k, v in enumerate(dv) if (abs(v.x0 - top.x0) < 2 or abs(v.x0 - top.x1) < 2)
                     and v.y0 <= top.y0 + 2 and v.y1 >= bot.y0 - 2]
            if len({round(dv[k].x0) for k in sides}) < 2:
                continue
            cx, cy = (top.x0 + top.x1) / 2, (top.y0 + bot.y0) / 2
            f = cell_of(cx, cy, hl, vl, page.border)
            if (top.x1 - top.x0) * (bot.y0 - top.y0) >= 0.15 * (f[2] - f[0]) * (f[3] - f[1]):
                keep_h.update((i, j))
                keep_v.update(sides)
    anchors_h = list(hl) + [dh[i] for i in keep_h]
    anchors_v = list(vl) + [dv[k] for k in keep_v]
    bx0, by0, bx1, by1 = page.border
    changed = True
    while changed:
        changed = False
        for i, h in enumerate(dh):
            if i in keep_h or h.length < 60:
                continue
            ends = ((h.x0, h.y0), (h.x1, h.y0))
            if any(abs(x - bx0) < 3 or abs(x - bx1) < 3 or any(abs(v.x0 - x) < 3 and v.y0 - 3 <= y <= v.y1 + 3 for v in anchors_v)
                   for x, y in ends):
                keep_h.add(i)
                anchors_h.append(h)
                changed = True
        for k, v in enumerate(dv):
            if k in keep_v or v.length < 60:
                continue
            ends = ((v.x0, v.y0), (v.x0, v.y1))
            if any(abs(y - by0) < 3 or abs(y - by1) < 3 or any(abs(h.y0 - y) < 3 and h.x0 - 3 <= x <= h.x1 + 3 for h in anchors_h)
                   for x, y in ends):
                keep_v.add(k)
                anchors_v.append(v)
                changed = True
    return [dh[i] for i in keep_h], [dv[k] for k in keep_v]


def cell_of(x, y, hl, vl, box):
    """Rectangle around (x, y) bounded by the nearest line on each side that actually spans the point."""
    bx0, by0, bx1, by1 = box
    x0 = max([s.x0 for s in vl if s.x0 <= x and bx0 <= s.x0 <= bx1 and min(s.y0, s.y1) - 1 <= y <= max(s.y0, s.y1) + 1] + [bx0])
    x1 = min([s.x0 for s in vl if s.x0 > x and bx0 <= s.x0 <= bx1 and min(s.y0, s.y1) - 1 <= y <= max(s.y0, s.y1) + 1] + [bx1])
    y0 = max([s.y0 for s in hl if s.y0 <= y and by0 <= s.y0 <= by1 and min(s.x0, s.x1) - 1 <= x <= max(s.x0, s.x1) + 1] + [by0])
    y1 = min([s.y0 for s in hl if s.y0 > y and by0 <= s.y0 <= by1 and min(s.x0, s.x1) - 1 <= x <= max(s.x0, s.x1) + 1] + [by1])
    return (x0, y0, x1, y1)


def headings(page, part_size, part_color):
    """Block titles: text clearly larger than part text, merged with neighbours on the same line."""
    cands = [s for s in page.spans if s.size >= 1.18 * part_size and s.color != part_color
             and not page.in_title_block(s.cx, s.cy)]
    cands.sort(key=lambda s: (round(s.cy), s.x0))
    merged = []
    for s in cands:
        if merged:
            m = merged[-1]
            if abs(m["cy"] - s.cy) < 1.0 and 0 <= s.x0 - m["x1"] < 1.5 * s.size:
                m["raw"] += " " + s.t
                m["x1"] = s.x1
                m["size"] = max(m["size"], s.size)
                continue
        merged.append(dict(raw=s.t, x0=s.x0, y0=s.y0, x1=s.x1, y1=s.y1, cy=s.cy, size=s.size))
    for m in merged:
        m["t"] = clean_heading(m["raw"])
    return [m for m in merged if m["t"] or re.search(r"[^\x00-\x7f]", m["raw"])]


def _zones(cell, heads):
    """Top-left title of a cell, plus same-size titles stacked at its left edge that split it into zones."""
    x0, y0, x1, y1 = cell
    inside = [h for h in heads if x0 - 1 <= h["x0"] <= x1 and y0 - 1 <= h["y0"] <= y1]
    top = [h for h in inside if h["y0"] - y0 <= 20 and h["t"]]
    if not top:
        return []
    main = min(top, key=lambda h: (h["y0"] - y0) + 0.3 * (h["x0"] - x0))
    zones = [(y0, main)]
    for h in sorted(inside, key=lambda h: h["y0"]):
        if h is not main and h["x0"] - x0 <= 12 and h["y0"] > main["y0"] + 15 and h["size"] >= 0.95 * main["size"]:
            zones.append((h["y0"] - 2, h))
    return zones


def locate(page, x, y, part_size, part_color, cache):
    if "frames" not in cache:
        hl, vl = frame_lines(page)
        cache["frames"] = (hl, vl)
        cache["dashed"] = dashed_partitions(page, hl, vl)
        cache["heads"] = headings(page, part_size, part_color)
    hl, vl = cache["frames"]
    dh, dv = cache["dashed"]
    heads = cache["heads"]
    frame = cell_of(x, y, hl, vl, page.border)
    sub = cell_of(x, y, dh, dv, frame)
    for cell in (sub, frame):
        zones = _zones(cell, heads)
        hit = [(i, z) for i, z in enumerate(zones) if y >= z[0]]
        if hit:
            i, (start, h) = hit[-1]
            end = zones[i + 1][0] if i + 1 < len(zones) else cell[3]
            region = (cell[0], start, cell[2], end)
            return (h["t"] or None), region, bool(h["t"])
    b = page.border
    if (frame[2] - frame[0]) * (frame[3] - frame[1]) >= 0.8 * (b[2] - b[0]) * (b[3] - b[1]) and page.sheet_title:
        return sheet_name(page), frame, True
    return None, sub, False


def sheet_name(page):
    t = re.sub(r"^\d+\s*", "", page.sheet_title).strip()
    return re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", t))


def _main_ref(refs):
    def rank(r):
        p = prefix(r)
        return (0 if p in ("U", "UA", "UH", "IC") else 1 if p in ("J", "JA", "CN", "JP", "JE", "JU")
                else 2 if p in ("SW", "S", "M", "VR", "H") else 3 if p in ("D", "Q", "Y", "YA") else 4, natkey(r))
    return min(refs, key=rank) if refs else None


def build(doc, parts, sizes, part_color, side, renames=None, exclude=("T", "TP")):
    """Assign every part to a block and return the blocks of one document."""
    renames = renames or {}
    blocks = {}
    for page in doc.pages:
        size = sizes.get(page.number)
        on_page = [p for p in parts.values() if p.page == page.number]
        if size is None or not on_page:
            continue
        cache = {}
        for p in on_page:
            name, region, titled = locate(page, p.x, p.y, size, part_color, cache)
            key = f"{page.number}:{name}" if titled else f"{page.number}:@{tuple(round(v) for v in region)}"
            b = blocks.get(key)
            if b is None:
                b = blocks[key] = Block(side, page.number, key, name or "", name or "", region, titled=titled)
            else:
                b.region = _union(b.region, region)
            b.refs.append(p.ref)
            p.block = key
        for h in cache.get("heads", []):
            if not h["t"]:
                continue
            name, region, titled = locate(page, h["x0"] + 1, h["cy"], size, part_color, cache)
            if titled and name == h["t"]:
                key = f"{page.number}:{name}"
                if key not in blocks:
                    blocks[key] = Block(side, page.number, key, name, name, region)
    for b in blocks.values():
        if not b.titled:
            main = _main_ref([r for r in b.refs if prefix(r) not in exclude] or b.refs)
            b.name = b.auto_name = f"Untitled p{b.page} ({main})" if main else f"Untitled p{b.page}"
        new = renames.get(f"{b.page}:{b.auto_name}") or renames.get(b.auto_name)
        if new:
            b.name = new
        b.refs.sort(key=natkey)
        b.crop = content_box(doc.page(b.page), b.region)
    return blocks


def page_blocks(doc, side, with_parts):
    """One block per sheet that has no parts (history, block diagram, power tree ...)."""
    out = {}
    for page in doc.pages:
        if page.number in with_parts:
            continue
        name = sheet_name(page) or f"Sheet {page.number}"
        key = f"{page.number}:{name}"
        out[key] = Block(side, page.number, key, name, name, page.border, crop=content_box(page, page.border))
    return out


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def content_box(page, region, margin=4):
    x0, y0, x1, y1 = region
    xs, ys = [], []
    for s in page.spans:
        if x0 <= s.cx <= x1 and y0 <= s.cy <= y1 and not page.in_title_block(s.cx, s.cy):
            xs += [s.x0, s.x1]
            ys += [s.y0, s.y1]
    for r in page.item_rects:
        cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
        w, h = r[2] - r[0], r[3] - r[1]
        if x0 <= cx <= x1 and y0 <= cy <= y1 and w < 0.95 * (x1 - x0) and h < 0.95 * (y1 - y0) and not page.in_title_block(cx, cy):
            xs += [r[0], r[2]]
            ys += [r[1], r[3]]
    if not xs:
        return region
    return (max(x0, min(xs) - margin), max(y0, min(ys) - margin), min(x1, max(xs) + margin), min(y1, max(ys) + margin))
