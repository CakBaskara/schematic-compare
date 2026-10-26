from helpers import NAVY, fillers, make_doc, span

from sch_compare import parts


def test_split_merged_overlapping_ref_and_value():
    assert parts.split_merged("RZA790R") == ("RZA79", "0R")
    assert parts.split_merged("RZA10310K") == ("RZA103", "10K")
    assert parts.split_merged("R10") is None
    assert parts.split_merged("ATS3031") is None


def test_split_span_ref_and_value_in_one_text():
    a, b = parts.split_span(span("RZA6 5.1K 5%", 100, 100))
    assert (a.t, b.t) == ("RZA6", "5.1K 5%")
    assert a.x1 <= b.x0


def test_value_below_beats_value_on_same_line_of_other_part():
    # Real geometry from a schematic: the cap value sits under the cap ref and right of the resistor ref.
    s = [span("RZA27", 435.3, 217.8, w=10.9), span("0R", 447.1, 221.6, w=4.5),
         span("CZA8", 458.7, 213.9, w=9.0), span("1UF 6.3V X5R", 454.8, 217.8, w=22.3)]
    found, issues, _ = parts.extract(make_doc(s + fillers(40)), NAVY)
    assert found["RZA27"].value == "0R"
    assert found["CZA8"].value == "1UF 6.3V X5R"


def test_horizontal_part_value_right_vertical_part_value_below():
    s = [span("RZA48", 80, 100), span("0R", 102, 100), span("CZA27", 113, 100), span("10UF 16V X5R", 128, 100),
         span("RZA58", 106, 140), span("0R", 106, 144)]
    found, _, _ = parts.extract(make_doc(s + fillers(40)), NAVY)
    assert found["RZA48"].value == "0R"
    assert found["CZA27"].value == "10UF 16V X5R"
    assert found["RZA58"].value == "0R"


def test_rare_coloured_nc_markup_is_a_value_but_test_points_get_none():
    s = [span("RZA113", 100, 100), span("NC", 102, 105, color=0x00FF00),
         span("T5", 300, 100), span("10K", 312, 100)]
    found, issues, _ = parts.extract(make_doc(s + fillers(80)), NAVY)
    assert found["RZA113"].value == "NC"
    assert found["T5"].value == ""


def test_footprint_goes_to_the_part_it_is_aligned_with():
    s = [span("R43", 640, 214), span("274K", 640, 218), span("R0402", 640, 222, color=0),
         span("CZA8", 662, 222), span("10UF 16V X5R", 648, 230)]
    found, _, _ = parts.extract(make_doc(s + fillers(40)), NAVY)
    assert found["R43"].fp == "R0402"
    assert found["CZA8"].fp == ""


def test_detect_part_color_from_refs():
    s = [span(f"R{i}", 10 * i, 10) for i in range(1, 20)] + [span("U1", 5, 50, color=0xFF0000)]
    assert parts.detect_part_color(make_doc(s)) == NAVY
