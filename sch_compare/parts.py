import collections
import math
import re
from dataclasses import dataclass, field, replace

REF_RE = re.compile(r"^[A-Z]{1,4}\d{1,3}[A-Z]?$")
FP_RE = re.compile(r"^(?:(?:R|C|L|LED)\d{4}|SOD-?\d+.*|SOT-?\d+.*|DFN.*|QFN.*|LQFP.*|SOP.*|TSSOP.*|MSOP.*|SC70.*)$", re.I)
VALUE_TAIL = re.compile(r"^(?:0R|[1-9]\d*(?:\.\d+)?[KMR]|NC)$")
COMMON_PREFIX = ("R", "C", "L", "U", "D", "Q", "J", "SW", "FB", "ESD", "LED", "Y")
BIG_BODY_PREFIX = ("U", "UA", "UH", "IC", "J", "JA", "JE", "JU", "JP", "CN", "SW", "VR", "H", "M", "YA", "Y", "LED", "Q")


@dataclass
class Part:
    ref: str
    page: int
    x: float
    y: float
    value: str = ""
    extra: list = field(default_factory=list)
    fp: str = ""
    how: str = "none"
    block: str = ""


def prefix(ref):
    m = re.match(r"[A-Z]+", ref)
    return m.group(0) if m else ref


def natkey(ref):
    m = re.match(r"([A-Z]+)(\d+)(.*)", ref)
    return (m.group(1), int(m.group(2)), m.group(3)) if m else (ref, 0, "")


def split_merged(t):
    """'RZA10310K' -> ('RZA103', '10K'): ref and value printed on top of each other in the PDF."""
    m = re.match(r"^([A-Z]{1,4})(\d+)(.*)$", t)
    if not m:
        return None
    letters, digits, rest = m.groups()
    for n in (3, 2, 1):
        if len(digits) > n:
            tail = digits[n:] + rest
            if VALUE_TAIL.match(tail):
                return letters + digits[:n], tail
    return None


def split_span(s):
    t = s.t
    toks = t.split()
    if len(toks) >= 2 and REF_RE.match(toks[0]) and not split_merged(toks[0]):
        cut = len(toks[0])
    else:
        m = split_merged(toks[0]) if toks else None
        if not m:
            return [s]
        cut = len(m[0])
    w = (s.x1 - s.x0) / max(len(t), 1)
    a = replace(s, t=t[:cut].strip(), x1=s.x0 + w * cut)
    b = replace(s, t=t[cut:].strip(), x0=s.x0 + w * (cut + 1))
    return [a, b]


def box_dist(a, b):
    dx = max(0.0, max(a.x0 - b.x1, b.x0 - a.x1))
    dy = max(0.0, max(a.y0 - b.y1, b.y0 - a.y1))
    return math.hypot(dx, dy)


def pair_cost(r, v):
    """Value text sits right of the ref on the same line, directly below it, or one line lower to the right."""
    rh = r.y1 - r.y0
    size = max(rh, 1.0)
    best = box_dist(r, v) * 3 + 6 * size
    if abs(r.cy - v.cy) <= 0.45 * rh and v.x0 >= r.x1 - 0.5:
        best = min(best, (v.x0 - r.x1) + 3 * abs(r.cy - v.cy))
    if v.y0 >= r.y0 + 0.5 * rh and abs(v.x0 - r.x0) <= 1.2 * size:
        best = min(best, max(0.0, v.y0 - r.y1) + abs(v.x0 - r.x0))
    if r.y0 + 0.5 * rh <= v.y0 <= r.y1 + 1.5 * rh and v.x0 >= r.x1 - 0.5:
        best = min(best, (v.x0 - r.x1) + 2 * max(0.0, v.y0 - r.y1) + 2)
    return best


def _greedy(refs, vals, r_val, v_used, thr, ok, directional):
    cost = pair_cost if directional else box_dist
    pairs = sorted((cost(r, v), i, j)
                   for i, r in enumerate(refs) if i not in r_val and ok(r.t)
                   for j, v in enumerate(vals) if j not in v_used and box_dist(r, v) <= thr)
    for _, i, j in pairs:
        if i in r_val or j in v_used:
            continue
        r_val[i] = j
        v_used.add(j)


def detect_part_color(doc):
    """OrCAD prints reference and value in one colour (navy by default); find it from the refs themselves."""
    c = collections.Counter()
    for p in doc.pages:
        for s in p.spans:
            if REF_RE.match(s.t) and s.t.startswith(COMMON_PREFIX) and s.color != 0:
                c[s.color] += 1
    return c.most_common(1)[0][0] if c else 0x000080


def _markup_colors(spans, part_color):
    """Rare colours are designer mark-up (for example a green 'NC' written over a part)."""
    c = collections.Counter(s.color for s in spans)
    n = max(len(spans), 1)
    return {col for col, k in c.items() if k / n < 0.02 and col not in (0, part_color)}


def extract(doc, part_color, no_value_prefix=("T", "TP", "NP", "AA")):
    parts, issues = {}, []
    sizes = {}
    for page in doc.pages:
        markup = _markup_colors(page.spans, part_color)
        cand = [s for s in page.spans if s.color == part_color or (s.t == "NC" and s.color in markup)]
        cand = [x for s in cand for x in split_span(s)]
        refs = [s for s in cand if REF_RE.match(s.t)]
        vals = [s for s in cand if not REF_RE.match(s.t)]
        fps = [s for s in page.spans if s.color == 0 and FP_RE.match(s.t)]
        if not refs:
            continue
        size = max(collections.Counter(s.size for s in cand).most_common(1)[0][0], 3.0)
        sizes[page.number] = size
        thr = 4.5 * size
        can_have = lambda t: prefix(t) not in no_value_prefix
        r_val, v_used, how = {}, set(), {}
        for stage, limit, ok, directional in (("near", 9 * size, can_have, True),
                                              ("mid", 14 * size, can_have, False),
                                              ("far", 40 * size, lambda t: prefix(t) in BIG_BODY_PREFIX, False)):
            before = set(r_val)
            _greedy(refs, vals, r_val, v_used, limit, ok, directional)
            for i in set(r_val) - before:
                how[i] = stage
        extra = collections.defaultdict(list)
        for j, v in enumerate(vals):
            if j in v_used:
                continue
            near = sorted((box_dist(r, v), i) for i, r in enumerate(refs) if can_have(r.t))
            if near and near[0][0] <= thr:
                extra[near[0][1]].append(v.t)
            else:
                issues.append(dict(page=page.number, kind="value text not linked to a part", text=v.t, x=round(v.x0), y=round(v.y0)))
        r_fp, f_used = {}, set()
        fpairs = []
        for k, f in enumerate(fps):
            for i, r in enumerate(refs):
                anchors = [r] + ([vals[r_val[i]]] if i in r_val else [])
                if min(box_dist(a, f) for a in anchors) > thr:
                    continue
                fpairs.append((min(pair_cost(a, f) for a in anchors), i, k))
        for _, i, k in sorted(fpairs):
            if i in r_fp or k in f_used:
                continue
            r_fp[i] = k
            f_used.add(k)
        for i, r in enumerate(refs):
            part = Part(ref=r.t, page=page.number, x=round(r.cx, 1), y=round(r.cy, 1),
                        value=vals[r_val[i]].t if i in r_val else "", extra=extra.get(i, []),
                        fp=fps[r_fp[i]].t if i in r_fp else "", how=how.get(i, "none"))
            if part.ref in parts:
                issues.append(dict(page=page.number, kind="duplicate ref (kept first)", text=part.ref,
                                   x=round(r.x0), y=round(r.y0)))
                continue
            parts[part.ref] = part
    for p in parts.values():
        if not p.value and prefix(p.ref) not in no_value_prefix:
            issues.append(dict(page=p.page, kind="part without value", text=p.ref, x=round(p.x), y=round(p.y)))
        elif p.how == "far":
            issues.append(dict(page=p.page, kind="value taken from far text, please check", text=f"{p.ref} = {p.value}",
                               x=round(p.x), y=round(p.y)))
    return parts, issues, sizes


def apply_overrides(parts, overrides):
    for ref, fix in (overrides or {}).items():
        if ref in parts:
            for k, v in fix.items():
                setattr(parts[ref], k, v)
            parts[ref].how = "override"
