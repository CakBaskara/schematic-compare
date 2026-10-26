import collections
import re


def net_color(doc):
    """Net aliases are usually red; take the commonest colour of text that looks like a net name."""
    c = collections.Counter()
    for p in doc.pages:
        for s in p.spans:
            if "_" in s.t and s.color != 0 and re.fullmatch(r"[A-Za-z0-9_+\-./\[\]]+", s.t):
                c[s.color] += 1
    return c.most_common(1)[0][0] if c else 0xFF0000


def find_body(page, ref_span):
    """Connector body: a vertical edge starting just under the ref text, closed by a parallel edge to the right."""
    vs = [s for s in page.segs if s.vertical and abs(s.y1 - s.y0) > 30]
    left = [s for s in vs if abs(s.x0 - ref_span.x0) <= 4 and ref_span.y1 - 1 <= min(s.y0, s.y1) <= ref_span.y1 + 6]
    if not left:
        return None
    lft = max(left, key=lambda s: abs(s.y1 - s.y0))
    top, bot = min(lft.y0, lft.y1), max(lft.y0, lft.y1)
    right = [s for s in vs if s.x0 > lft.x0 + 5 and abs(min(s.y0, s.y1) - top) < 1.5 and abs(max(s.y0, s.y1) - bot) < 1.5]
    if not right:
        return None
    return (lft.x0, top, min(right, key=lambda s: s.x0).x0, bot)


def _wire_end(page, y, x_edge, direction):
    """Follow the pin line and the wire joined to it; returns the far x, or None when no line leaves the body."""
    row = sorted((min(s.x0, s.x1), max(s.x0, s.x1)) for s in page.segs if s.horizontal and abs(s.y0 - y) <= 0.4)
    end, found = x_edge, False
    changed = True
    while changed:
        changed = False
        for a, b in row:
            if direction > 0 and a <= end + 1.5 and b > end + 0.01:
                end, found, changed = b, True, True
            elif direction < 0 and b >= end - 1.5 and a < end - 0.01:
                end, found, changed = a, True, True
    return end if found else None


def connector_nets(doc, ref, color=None):
    color = color if color is not None else net_color(doc)
    for page in doc.pages:
        for h in (s for s in page.spans if s.t == ref):
            body = find_body(page, h)
            if not body:
                continue
            bx0, by0, bx1, by1 = body
            nums = [s for s in page.spans if s.color == 0 and re.fullmatch(r"\d{1,3}", s.t) and by0 - 2 <= s.cy <= by1 + 2
                    and ((bx0 - 25 <= s.x0 and s.x1 <= bx0 + 1) or (bx1 - 1 <= s.x0 and s.x1 <= bx1 + 25))]
            nets = [s for s in page.spans if s.color == color]
            power = [s for s in page.spans if s.color == 0 and "Bold" in s.font and re.search(r"[A-Za-z]", s.t)]
            out = {}
            for n in nums:
                hgt = n.y1 - n.y0
                left_side = n.x1 <= bx0 + 1
                edge = bx0 if left_side else bx1
                lines = sorted({round(s.y0, 2) for s in page.segs if s.horizontal and n.cy - 0.3 * hgt <= s.y0 <= n.cy + 0.9 * hgt
                                and abs((max(s.x0, s.x1) if left_side else min(s.x0, s.x1)) - edge) < 1.5},
                               key=lambda y: abs(y - (n.cy + 0.3 * hgt)))
                name = ""
                if lines:
                    y = lines[0]
                    end = _wire_end(page, y, edge, -1 if left_side else 1)
                    if end is not None:
                        lo, hi = (end - 2, edge) if left_side else (edge, end + 2)
                        on_wire = [s for s in nets if lo <= s.cx <= hi and y - 1.4 * hgt <= s.cy <= y + 0.2 * hgt]
                        on_wire.sort(key=lambda s: abs(s.cx - edge))
                        if not on_wire:
                            on_wire = [s for s in power if abs((s.x1 if left_side else s.x0) - end) < 8 and abs(s.cy - y) < 2 * hgt]
                        for s in on_wire:
                            tok = [t for t in s.t.split() if not re.fullmatch(r"[\d,.\[\]]+", t)]
                            if tok:
                                name = tok[0]
                                break
                out[int(n.t)] = name
            if out:
                return dict(page=page.number, body=body, nets=out)
    return None


def pin_rows(before, after):
    rows = []
    for n in sorted(set(before["nets"]) | set(after["nets"])):
        o, w = before["nets"].get(n, ""), after["nets"].get(n, "")
        if o != w:
            rows.append((n, o or "(not connected)", w or "(not connected)"))
    return rows
