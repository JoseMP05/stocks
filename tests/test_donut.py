"""Ring geometry tests, including the three ways it degenerates."""

from __future__ import annotations

import pytest

from app.analysis.donut import OTHER_LABEL, OTHER_TONE, TONES, build_donut


def test_shares_sum_to_one_and_sweeps_cover_the_circle():
    donut = build_donut([("a", 50.0), ("b", 30.0), ("c", 20.0)])

    assert donut is not None
    assert sum(s.share for s in donut.slices) == pytest.approx(1.0)
    assert donut.slices[-1].end_deg == pytest.approx(360.0, abs=1.0)


def test_slices_are_ranked_largest_first():
    donut = build_donut([("small", 1.0), ("big", 9.0)])

    assert [s.label for s in donut.slices] == ["big", "small"]
    assert donut.top_label == "big"
    assert donut.top_share == pytest.approx(0.9)


def test_tones_are_assigned_in_order_and_never_cycled():
    donut = build_donut([(f"s{i}", float(TONES - i)) for i in range(TONES)])

    assert [s.tone for s in donut.slices] == list(range(1, TONES + 1))


def test_single_holding_draws_a_ring_rather_than_nothing():
    """A 360-degree arc has coincident endpoints and paints nothing at all."""
    donut = build_donut([("only", 100.0)])

    assert donut.full_circle is True
    assert donut.slices[0].path  # a real path, not an empty string
    # Two subpaths cut with evenodd: outer circle, then inner.
    assert donut.slices[0].path.count("M ") == 2


def test_zero_total_has_nothing_to_draw():
    assert build_donut([]) is None
    assert build_donut([("a", 0.0)]) is None
    assert build_donut([("a", -5.0)]) is None


def test_overflow_folds_into_one_residual_wedge():
    items = [(f"s{i}", float(20 - i)) for i in range(12)]
    donut = build_donut(items, max_slices=4)

    assert len(donut.slices) == 4
    assert donut.slices[-1].label == OTHER_LABEL
    assert donut.slices[-1].tone == OTHER_TONE
    assert sum(s.value for s in donut.slices) == pytest.approx(sum(v for _, v in items))


def test_members_stay_attached_to_their_wedge():
    donut = build_donut(
        [("Tech", 60.0), ("Utilities", 40.0)],
        members={"Tech": ["CRWV", "MDB"], "Utilities": ["VST"]},
    )

    assert donut.slices[0].members == ("CRWV", "MDB")
    assert donut.slices[1].members == ("VST",)


def test_the_residual_wedge_inherits_what_it_swallowed():
    """Folding into 'Otros' must not lose track of what ended up there."""
    donut = build_donut(
        [("a", 10.0), ("b", 5.0), ("c", 3.0), ("d", 1.0)],
        max_slices=2,
        members={"b": ["B1"], "c": ["C1", "C2"]},
    )

    other = donut.slices[-1]
    assert other.label == OTHER_LABEL
    # 'd' had no members of its own, so it contributes its own label.
    assert other.members == ("B1", "C1", "C2", "d")


def test_a_single_wedge_keeps_its_members():
    donut = build_donut([("STOCK", 100.0)], members={"STOCK": ["AAA", "BBB"]})

    assert donut.full_circle is True
    assert donut.slices[0].members == ("AAA", "BBB")


def test_members_are_optional():
    donut = build_donut([("a", 1.0), ("b", 1.0)])

    assert all(s.members == () for s in donut.slices)


def test_a_sliver_thinner_than_the_gap_still_sweeps_forward():
    """Subtracting a fixed gap from a tiny wedge must not invert it."""
    donut = build_donut([("huge", 100000.0), ("sliver", 1.0)])

    sliver = donut.slices[-1]
    assert sliver.end_deg > sliver.start_deg
