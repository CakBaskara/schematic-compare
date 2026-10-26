import re
from dataclasses import dataclass

from .blocks import norm_name
from .parts import natkey, prefix


@dataclass
class Row:
    ref: str
    kind: str
    sheet: int
    circuit: str
    b_val: str
    b_fp: str
    a_val: str
    a_fp: str
    mount: str
    remark: str
    a_block: str = ""
    b_block: str = ""


def norm_value(v):
    return re.sub(r"\s+", " ", (v or "").strip()).upper()


def is_mounted(v):
    v = norm_value(v)
    return not (v == "NC" or v.startswith("NC/"))


STOP_WORDS = {"circuit", "circuits", "header", "power", "sensor", "block", "option", "untitled", "board", "connector"}


def pair_blocks(blocks_b, blocks_a, parts_b, parts_a, forced_pairs=(), exclude=("T", "TP")):
    """Map each after-block to a before-block: forced or equal names, then shared parts, then a shared word."""
    by_name_b = {}
    for k, b in blocks_b.items():
        by_name_b.setdefault(norm_name(b.name), []).append(k)
    forced = {norm_name(a): norm_name(b) for b, a in forced_pairs}
    pairs = {}
    for ka, a in blocks_a.items():
        n = forced.get(norm_name(a.name), norm_name(a.name))
        if n in by_name_b:
            pairs[ka] = min(by_name_b[n], key=lambda kb: abs(blocks_b[kb].page - a.page))
    for ka, a in blocks_a.items():
        refs = [r for r in a.refs if prefix(r) not in exclude]
        if ka in pairs or not refs:
            continue
        count = {}
        for r in refs:
            o = parts_b.get(r)
            if o and norm_value(o.value) == norm_value(parts_a[r].value):
                count[o.block] = count.get(o.block, 0) + 1
        if count:
            kb, same = max(count.items(), key=lambda kv: kv[1])
            # Score against the after-block size: a few shared NC caps must not pull a big new block onto an old one.
            if same >= 2 and same / len(refs) >= 0.4:
                pairs[ka] = kb
    used = set(pairs.values())
    for ka, a in blocks_a.items():
        if ka in pairs:
            continue
        words = {w for w in re.findall(r"[a-z]{4,}", a.name.lower()) if w not in STOP_WORDS}
        cand = [kb for kb, b in blocks_b.items() if kb not in used
                and words & {w for w in re.findall(r"[a-z]{4,}", b.name.lower()) if w not in STOP_WORDS}]
        if len(cand) == 1:
            pairs[ka] = cand[0]
            used.add(cand[0])
    return pairs


def compare(parts_b, parts_a, blocks_b, blocks_a, pairs, exclude=("T", "TP")):
    rows = []
    for ref in sorted(set(parts_b) | set(parts_a), key=natkey):
        if prefix(ref) in exclude:
            continue
        o, n = parts_b.get(ref), parts_a.get(ref)
        if o and n:
            val_eq = norm_value(o.value) == norm_value(n.value)
            fp_eq = not o.fp or not n.fp or o.fp == n.fp
            same_block = pairs.get(n.block) == o.block
            if val_eq and fp_eq and same_block:
                continue
            what = []
            if not val_eq:
                om, nm = is_mounted(o.value), is_mounted(n.value)
                what.append("value change" if om == nm else ("NC to Mount" if nm else "Mount to NC"))
            if not fp_eq:
                what.append(f"footprint {o.fp} to {n.fp}")
            src = f"sheet {o.page} {blocks_b[o.block].name}"
            if what:
                kind = "Changed"
                remark = "Changed: " + ", ".join(what) + ("" if same_block else f"; Moved from {src}")
            else:
                kind = "Moved"
                remark = f"Moved: from {src}"
            rows.append(Row(ref, kind, n.page, blocks_a[n.block].name, o.value or "-", o.fp or "-",
                            n.value or "-", n.fp or "-", "Mounted" if is_mounted(n.value) else "Not Mounted",
                            remark, n.block, o.block))
        elif n:
            m = is_mounted(n.value)
            rows.append(Row(ref, "Added", n.page, blocks_a[n.block].name, "-", "-", n.value or "-", n.fp or "-",
                            "Mounted" if m else "Not Mounted", "Added" if m else "Added (footprint only, NC)", n.block, ""))
        else:
            rows.append(Row(ref, "Removed", o.page, blocks_b[o.block].name, o.value or "-", o.fp or "-", "-", "-",
                            "Not Mounted", "Removed" if is_mounted(o.value) else "Removed (was NC)", "", o.block))
    return rows


def order_rows(rows, blocks_b, blocks_a):
    def pos(r):
        b = blocks_a.get(r.a_block) if r.a_block else blocks_b.get(r.b_block)
        return (b.page, round(b.region[1] / 20), b.region[0]) if b else (99, 0, 0)
    rows.sort(key=lambda r: (pos(r), r.circuit, r.mount != "Mounted", natkey(r.ref)))
    return rows


def block_rows(blocks_b, blocks_a, pairs, rows, page_pairs):
    """Rows for the circuit diagram sheet: paired blocks, new blocks and removed blocks in page order."""
    used_b = set(pairs.values()) | set(page_pairs.values())
    out = []
    for ka, a in blocks_a.items():
        kb = pairs.get(ka) or page_pairs.get(ka)
        out.append((blocks_b.get(kb) if kb else None, a))
    for kb, b in blocks_b.items():
        if kb not in used_b:
            out.append((b, None))

    def pos(pair):
        b, a = pair
        x = a or b
        return (x.page, a is None, round(x.region[1] / 10), x.region[0])
    out.sort(key=pos)
    return out


def pair_pages(pblocks_b, pblocks_a):
    by = {norm_name(b.name): k for k, b in pblocks_b.items()}
    return {ka: by[norm_name(a.name)] for ka, a in pblocks_a.items() if norm_name(a.name) in by}


def primary_pairs(pairs, blocks_b, blocks_a):
    """For a before-block shared by several after-blocks, the one that keeps its removed parts."""
    out = {}
    for ka, kb in pairs.items():
        if norm_name(blocks_a[ka].name) == norm_name(blocks_b[kb].name) or kb not in out:
            out[kb] = ka
    return out


def summarize(b, a, rows, with_removed=True, limit=8):
    """Auto remark for one circuit-diagram row, built from the part rows of that block pair."""
    ka = a.key if a else None
    kb = b.key if b else None
    mine = [r for r in rows if (ka and r.a_block == ka) or (with_removed and kb and not r.a_block and r.b_block == kb)]
    if not a:
        return f"Block removed ({len(mine)} parts)." if mine else "Block removed."
    if not b and not mine:
        return "New block (no parts)."
    groups = {"Added": [], "Removed": [], "Changed": [], "Moved": []}
    for r in mine:
        groups[r.kind].append(r)

    def fmt(r):
        if r.kind == "Added":
            return f"{r.ref} {r.a_val}"
        if r.kind == "Removed":
            return f"{r.ref} {r.b_val}"
        if r.kind == "Moved":
            return f"{r.ref} ({r.remark.split('from ', 1)[-1]})"
        return f"{r.ref} {r.b_val} to {r.a_val}" if r.b_val != r.a_val else f"{r.ref} {r.b_fp} to {r.a_fp}"
    lines = [] if b else ["New block."]
    for k in ("Added", "Removed", "Changed", "Moved"):
        g = groups[k]
        if g:
            items = ", ".join(fmt(r) for r in g[:limit]) + (", ..." if len(g) > limit else "")
            lines.append(f"{k} ({len(g)}): {items}")
    return "\n".join(lines) if lines else "No part change (check wiring in the pictures)."
