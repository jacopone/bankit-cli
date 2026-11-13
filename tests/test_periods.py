from datetime import date

import pytest

from bankit.periods import end_date_of_period, frequency_of_period, normalise_frequency, period_from_date


@pytest.mark.parametrize(
    ("freq", "expected"),
    [("D", "2026-08-31"), ("M", "2026-08"), ("Q", "2026-Q3"), ("S", "2026-S2"), ("A", "2026"), (None, None)],
)
def test_period_from_date(freq, expected):
    assert period_from_date(date(2026, 8, 31), freq) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [("2026-02", date(2026, 2, 28)), ("2024-02", date(2024, 2, 29)), ("2026-Q2", date(2026, 6, 30)),
     ("2026-S1", date(2026, 6, 30)), ("2025", date(2025, 12, 31)), ("2026-09-30", date(2026, 9, 30))],
)
def test_end_date_of_period(label, expected):
    assert end_date_of_period(label) == expected


def test_frequency_helpers():
    assert normalise_frequency("m") == "M"
    assert normalise_frequency("H") == "S"
    assert normalise_frequency("24") is None
    assert frequency_of_period("2026-Q2") == "Q"
    assert frequency_of_period("2026") == "A"
