"""Unit tests for ESMA XBRL period and value parsing."""

from ingestion.sources.esma_xbrl import _coerce_numeric, _parse_period


class TestParsePeriod:
    def test_duration_decrements_end_at_midnight(self):
        """
        XBRL duration end is exclusive — encoded as start-of-next-day midnight.
        FY2022 reported as 2022-01-01/2023-01-01 should yield 2022-12-31 end.
        """
        start, end = _parse_period("2022-01-01T00:00:00/2023-01-01T00:00:00")
        assert start == "2022-01-01"
        assert end == "2022-12-31"

    def test_instant_at_midnight_decrements(self):
        """Balance-sheet instants at midnight = as-of close of previous day."""
        _, end = _parse_period("2023-01-01T00:00:00")
        assert end == "2022-12-31"

    def test_non_midnight_instant_keeps_date(self):
        _, end = _parse_period("2023-06-30T12:34:56")
        assert end == "2023-06-30"

    def test_empty_string_returns_none(self):
        assert _parse_period("") == (None, None)

    def test_fiscal_year_ending_jun(self):
        """Fiscal year ending June 30, 2024 → duration 2023-07-01/2024-07-01."""
        start, end = _parse_period("2023-07-01T00:00:00/2024-07-01T00:00:00")
        assert start == "2023-07-01"
        assert end == "2024-06-30"


class TestCoerceNumeric:
    def test_int_string(self):
        assert _coerce_numeric("12096201000") == 12096201000.0

    def test_float_string(self):
        assert _coerce_numeric("1573523000.0") == 1573523000.0

    def test_already_float(self):
        assert _coerce_numeric(42.5) == 42.5

    def test_int_passthrough(self):
        assert _coerce_numeric(100) == 100.0

    def test_none_returns_none(self):
        assert _coerce_numeric(None) is None

    def test_empty_string_returns_none(self):
        assert _coerce_numeric("") is None

    def test_nil_string_returns_none(self):
        assert _coerce_numeric("nil") is None
        assert _coerce_numeric("N/A") is None

    def test_garbage_string_returns_none(self):
        assert _coerce_numeric("not a number") is None
