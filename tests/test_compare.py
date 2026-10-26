from sch_compare import compare as cmp
from sch_compare.blocks import Block
from sch_compare.parts import Part


def part(ref, value, block, fp="", page=4):
    return Part(ref, page, 0, 0, value=value, fp=fp, block=block)


def blk(key, name, refs, page=4):
    return Block("x", page, key, name, name, (0, 0, 10, 10), refs=refs)


def test_kinds_and_mounting():
    pb = {"R1": part("R1", "2.2K", "b1"), "R2": part("R2", "NC", "b1"), "R3": part("R3", "0R", "b1"),
          "C1": part("C1", "10nF", "b1", "C0402"), "T5": part("T5", "", "b1"), "Q1": part("Q1", "AO3415", "b1")}
    pa = {"R1": part("R1", "4.7R", "a1"), "R2": part("R2", "0R", "a1"), "C1": part("C1", "10nF", "a1", "C0201"),
          "U4": part("U4", "ICM-42670-P", "a1"), "R9": part("R9", "NC", "a1"), "Q1": part("Q1", "AO3415", "a2", page=6)}
    bb = {"b1": blk("b1", "Motor", list(pb))}
    ba = {"a1": blk("a1", "Motor", ["R1", "R2", "C1", "U4", "R9"]), "a2": blk("a2", "TP_POWER", ["Q1"], 6)}
    pairs = cmp.pair_blocks(bb, ba, pb, pa)
    rows = {r.ref: r for r in cmp.compare(pb, pa, bb, ba, pairs)}
    assert rows["R1"].remark == "Changed: value change"
    assert rows["R2"].remark.startswith("Changed: NC to Mount") and rows["R2"].mount == "Mounted"
    assert rows["C1"].remark == "Changed: footprint C0402 to C0201"
    assert rows["R3"].kind == "Removed" and rows["R3"].mount == "Not Mounted"
    assert rows["U4"].kind == "Added" and rows["U4"].mount == "Mounted"
    assert rows["R9"].remark == "Added (footprint only, NC)"
    assert rows["Q1"].kind == "Moved" and "sheet 4 Motor" in rows["Q1"].remark
    assert "T5" not in rows


def test_few_shared_nc_caps_do_not_pair_a_big_block():
    pb = {f"CZA{i}": part(f"CZA{i}", "NC", "ant") for i in range(1, 5)}
    pb.update({f"LA{i}": part(f"LA{i}", "0R", "ant") for i in range(1, 7)})
    pa = {f"CZA{i}": part(f"CZA{i}", "NC", "mcu", page=7) for i in range(1, 5)}
    pa.update({f"RZA{i}": part(f"RZA{i}", "0R", "mcu", page=7) for i in range(100, 160)})
    bb = {"ant": blk("ant", "ANT", list(pb))}
    ba = {"mcu": blk("mcu", "I/O Ext MCU", list(pa), 7)}
    assert cmp.pair_blocks(bb, ba, pb, pa) == {}


def test_overlap_and_word_pairing():
    pb = {r: part(r, "X", "keys") for r in ("SW7", "SW8", "SW9", "SW10", "SW2", "SW3", "SW4", "SW5")}
    pb.update({"SW22": part("SW22", "Y", "act"), "SW23": part("SW23", "Y", "act"), "SW17": part("SW17", "Y", "act")})
    pa = {r: part(r, "X", "trig", page=6) for r in ("SW7", "SW8", "SW9", "SW10", "SW27")}
    pa.update({r: part(r, "Y", "back", page=6) for r in ("SW22", "SW23", "SW25", "SW26", "SW30", "SW31", "SW32", "SW33")})
    bb = {"keys": blk("keys", "Keys", [r for r in pb if pb[r].block == "keys"]), "act": blk("act", "Mappable Action Buttons", ["SW22", "SW23", "SW17"])}
    ba = {"trig": blk("trig", "Untitled p6 (SW7)", ["SW7", "SW8", "SW9", "SW10", "SW27"], 6),
          "back": blk("back", "Buttons", ["SW22", "SW23", "SW25", "SW26", "SW30", "SW31", "SW32", "SW33"], 6)}
    pairs = cmp.pair_blocks(bb, ba, pb, pa)
    assert pairs == {"trig": "keys", "back": "act"}
