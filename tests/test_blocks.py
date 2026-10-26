from helpers import NAVY, hline, make_doc, span, vline

from sch_compare import blocks
from sch_compare.parts import Part


def test_clean_heading_drops_non_ascii():
    assert blocks.clean_heading("3DVR(Joystick) 霍爾搖桿") == "3DVR(Joystick)"
    assert blocks.clean_heading("板機/副板") == ""


def test_cell_of_uses_only_lines_that_span_the_point():
    hl = [hline(0, 400, 100)]
    vl = [vline(200, 0, 100)]
    assert blocks.cell_of(50, 50, hl, vl, (0, 0, 400, 300)) == (0, 0, 200, 100)
    assert blocks.cell_of(50, 200, hl, vl, (0, 0, 400, 300)) == (0, 100, 400, 300)


def test_dangling_frame_line_is_extended_to_the_border():
    doc = make_doc([], segs=[hline(4, 187, 176), vline(187, 359, 522), vline(187, 3, 360), hline(187, 799, 339)])
    hl, vl = blocks.frame_lines(doc.pages[0])
    v187 = [v for v in vl if abs(v.x0 - 187) < 0.5]
    assert len(v187) == 1 and v187[0].y0 == 0 and v187[0].y1 == 600


def _page_with(spans, segs):
    doc = make_doc(spans, segs)
    return doc, doc.pages[0]


def test_heading_is_top_left_title_not_a_note_lower_down():
    s = [span("ANT", 568, 8, size=5.1, color=0), span("RF need 50 ohm", 568, 27, size=4.6, color=0),
         span("LA1", 630, 47)]
    doc, page = _page_with(s, [hline(556, 782, 124), vline(556, 4, 404)])
    name, region, titled = blocks.locate(page, 632, 49, 3.5, NAVY, {})
    assert (name, titled) == ("ANT", True)


def test_label_far_below_the_top_is_not_a_heading():
    s = [span("Option A", 435, 66, size=5.1, color=0), span("RZA88", 440, 72)]
    doc, page = _page_with(s, [vline(346, 4, 303), vline(540, 4, 303), hline(4, 782, 303)])
    name, region, titled = blocks.locate(page, 442, 74, 3.5, NAVY, {})
    assert not titled


def test_same_size_title_at_left_edge_splits_a_frame():
    s = [span("Keys", 412, 12, size=5.8, color=0), span("Buttons", 405, 502, size=5.8, color=0),
         span("SW2", 450, 40), span("SW22", 450, 520)]
    doc, page = _page_with(s, [vline(401, 4, 587)])
    assert blocks.locate(page, 452, 42, 3.5, NAVY, {})[0] == "Keys"
    assert blocks.locate(page, 452, 522, 3.5, NAVY, {})[0] == "Buttons"


def test_build_names_untitled_block_after_main_part():
    s = [span("U18", 565, 360), span("RZA194", 600, 350)]
    doc, page = _page_with(s, [hline(187, 799, 339), vline(432, 339, 591)])
    ps = {"U18": Part("U18", 1, 565, 360), "RZA194": Part("RZA194", 1, 600, 350)}
    out = blocks.build(doc, ps, {1: 3.5}, NAVY, "after")
    names = {b.name for b in out.values()}
    assert "Untitled p1 (U18)" in names
