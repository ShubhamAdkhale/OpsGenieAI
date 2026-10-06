"""Indian-numbering rupee formatting.

Worth testing because the frontend formats with `en-IN` independently; if these
two ever disagree, the same figure renders two ways on one screen.
"""

from __future__ import annotations

import pytest

from app.services.formatting import indian_group, inr


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "0"),
        (7, "7"),
        (999, "999"),
        (1_000, "1,000"),
        (18_000, "18,000"),
        (99_999, "99,999"),
        (1_00_000, "1,00,000"),
        (4_10_000, "4,10,000"),
        (5_00_000, "5,00,000"),
        (30_50_00, "3,05,000"),
        (1_23_45_678, "1,23,45,678"),
    ],
)
def test_indian_grouping(amount, expected):
    assert indian_group(amount) == expected


def test_rounds_to_whole_rupees():
    assert indian_group(409_895.4) == "4,09,895"


def test_negative_amounts():
    assert indian_group(-4_10_000) == "-4,10,000"


def test_inr_prefix():
    assert inr(3_05_000) == "₹3,05,000"


def test_demo_headline_figures_render_as_expected():
    """The three numbers quoted in the demo script."""
    assert inr(410_000) == "₹4,10,000"
    assert inr(105_000) == "₹1,05,000"
    assert inr(305_000) == "₹3,05,000"
