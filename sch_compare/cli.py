import argparse
import dataclasses
import json
import os
import sys

from . import blocks as blk
from . import compare as cmp
from . import config as cfgmod
from . import excel, parts as prt, pdfdoc, pins as pinmod


def analyse(path, side, cfg):
    doc = pdfdoc.load(path)
    color = prt.detect_part_color(doc)
    parts, issues, sizes = prt.extract(doc, color, tuple(cfg["no_value_prefixes"]))
    prt.apply_overrides(parts, cfg["value_overrides"].get(side))
    blocks = blk.build(doc, parts, sizes, color, side, cfg["block_names"].get(side), tuple(cfg["exclude_prefixes"]))
    pages = blk.page_blocks(doc, side, {p.page for p in parts.values()})
    return dict(doc=doc, parts=parts, issues=issues, blocks=blocks, pages=pages)


def default_output(b, a):
    base = os.path.join(os.path.dirname(os.path.abspath(a.path)), f"CHANGE.POINT.LIST_{b.stem}_vs_{a.stem}")
    out, i = base + ".xlsx", 1
    while os.path.exists(out):
        out = f"{base}_{i}.xlsx"
        i += 1
    return out


def run(before, after, output=None, config=None, before_name=None, after_name=None, pins=None,
        auto_order=False, dump=None, log=print):
    cfg = cfgmod.load(config)
    B = analyse(before, "before", cfg)
    A = analyse(after, "after", cfg)
    if auto_order and B["doc"].date() > A["doc"].date():
        B, A = analyse(after, "before", cfg), analyse(before, "after", cfg)
    doc_b, doc_a = B["doc"], A["doc"]
    name_b = before_name or cfg["before_name"] or doc_b.stem
    name_a = after_name or cfg["after_name"] or doc_a.stem
    log(f"Before: {doc_b.name} ({doc_b.date():%Y-%m-%d}, {len(doc_b.pages)} sheets, {len(B['parts'])} parts)")
    log(f"After : {doc_a.name} ({doc_a.date():%Y-%m-%d}, {len(doc_a.pages)} sheets, {len(A['parts'])} parts)")

    pairs = cmp.pair_blocks(B["blocks"], A["blocks"], B["parts"], A["parts"], cfg["block_pairs"],
                            tuple(cfg["exclude_prefixes"]))
    rows = cmp.compare(B["parts"], A["parts"], B["blocks"], A["blocks"], pairs, tuple(cfg["exclude_prefixes"]))
    cmp.order_rows(rows, B["blocks"], A["blocks"])

    page_pairs = cmp.pair_pages(B["pages"], A["pages"])
    all_b = {**B["pages"], **B["blocks"]}
    all_a = {**A["pages"], **A["blocks"]}
    primary = cmp.primary_pairs(pairs, B["blocks"], A["blocks"])
    cdc = []
    remarks = cfg["block_remarks"]
    for b, a in cmp.block_rows(all_b, all_a, pairs, rows, page_pairs):
        with_removed = not (b and a) or primary.get(b.key) == a.key
        text = remarks.get(a.name if a else "") or remarks.get(b.name if b else "")
        sheet_only = (b and b.key in B["pages"]) or (a and a.key in A["pages"])
        auto = "" if sheet_only or not cfg["auto_remarks"] else cmp.summarize(b, a, rows, with_removed)
        cdc.append((b, a, "\n".join(t for t in (text, auto) if t)))

    pin_tables = []
    for ref in (pins if pins is not None else cfg["pins"]):
        nb, na = pinmod.connector_nets(doc_b, ref), pinmod.connector_nets(doc_a, ref)
        if not nb or not na:
            log(f"Pins  : {ref} not found in {'before' if not nb else 'after'} PDF, skipped")
            continue
        pin_tables.append(dict(ref=ref, page_b=nb["page"], page_a=na["page"], rows=pinmod.pin_rows(nb, na)))
        log(f"Pins  : {ref} {len(pin_tables[-1]['rows'])} pins changed")

    out = output or default_output(doc_b, doc_a)
    excel.write(out, dict(docs=(doc_b, doc_a), names=(name_b, name_a), rows=rows, cdc=cdc, pins=pin_tables,
                          issues=(B["issues"], A["issues"]), blocks=(B["blocks"], A["blocks"]),
                          checks=cfg["check_items"], exclude=cfg["exclude_prefixes"]))
    kinds = {k: sum(1 for r in rows if r.kind == k) for k in ("Added", "Removed", "Changed", "Moved")}
    log(f"Parts : {len(rows)} listed  " + "  ".join(f"{k} {v}" for k, v in kinds.items()))
    log(f"Review: {len(B['issues']) + len(A['issues'])} items in sheet 'Extraction Review'")
    log(f"Output: {out}")

    if dump:
        os.makedirs(dump, exist_ok=True)
        for tag, X in (("before", B), ("after", A)):
            with open(os.path.join(dump, f"{tag}_parts.json"), "w", encoding="utf-8") as f:
                json.dump({k: dataclasses.asdict(v) for k, v in X["parts"].items()}, f, ensure_ascii=False, indent=1)
            with open(os.path.join(dump, f"{tag}_blocks.json"), "w", encoding="utf-8") as f:
                json.dump({k: dataclasses.asdict(v) for k, v in X["blocks"].items()}, f, ensure_ascii=False, indent=1)
        with open(os.path.join(dump, "rows.json"), "w", encoding="utf-8") as f:
            json.dump([dataclasses.asdict(r) for r in rows], f, ensure_ascii=False, indent=1)
    return dict(output=out, rows=rows, before=B, after=A, pairs=pairs, pins=pin_tables)


def dropped(files):
    """Drag and drop: two PDFs in any order plus an optional .json config."""
    pdfs = [f for f in files if f.lower().endswith(".pdf")]
    cfgs = [f for f in files if f.lower().endswith(".json")]
    if len(pdfs) != 2 or len(cfgs) > 1 or len(pdfs) + len(cfgs) != len(files):
        print("Drop exactly two schematic PDFs (and optionally one .json config).", file=sys.stderr)
        return 1
    try:
        run(pdfs[0], pdfs[1], config=cfgs[0] if cfgs else None, auto_order=True)
    except PermissionError as e:
        print(f"Cannot write the output (is it open in Excel?): {e}", file=sys.stderr)
        return 2
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--drop"]:
        return dropped(argv[1:])
    ap = argparse.ArgumentParser(prog="sch_compare",
                                 description="Compare two schematic PDFs and write a change point list (.xlsx).")
    ap.add_argument("before", help="older schematic PDF")
    ap.add_argument("after", help="newer schematic PDF")
    ap.add_argument("-o", "--output", help="output .xlsx (default: next to the AFTER pdf, never overwritten)")
    ap.add_argument("-c", "--config", help="JSON config with names, value fixes, block renames, remarks")
    ap.add_argument("--before-name", help="label for the older schematic, e.g. Joystick")
    ap.add_argument("--after-name", help="label for the newer schematic, e.g. Joystick2")
    ap.add_argument("--pins", nargs="*", help="connector refs to compare pin by pin, e.g. --pins J1")
    ap.add_argument("--auto-order", action="store_true", help="swap the inputs if BEFORE is newer (for drag and drop)")
    ap.add_argument("--dump", help="also write the extracted parts, blocks and rows as JSON into this folder")
    args = ap.parse_args(argv)
    for p in (args.before, args.after):
        if not os.path.isfile(p):
            ap.error(f"file not found: {p}")
    try:
        run(args.before, args.after, args.output, args.config, args.before_name, args.after_name, args.pins,
            args.auto_order, args.dump)
    except PermissionError as e:
        print(f"Cannot write the output (is it open in Excel?): {e}", file=sys.stderr)
        return 2
    return 0
