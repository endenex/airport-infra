"""Unit tests for Eurostat aviation parser."""


from ingestion.sources.eurostat_aviation import (
    EurostatAviationIngestor,
    _split_eurostat_airport_code,
)


class TestSplitCode:
    def test_normal_code(self):
        assert _split_eurostat_airport_code("FR_LFPG") == ("FR", "LFPG")

    def test_uk_prefix(self):
        assert _split_eurostat_airport_code("UK_EGLL") == ("UK", "EGLL")

    def test_empty_returns_none(self):
        assert _split_eurostat_airport_code("") == (None, None)

    def test_malformed_returns_none(self):
        assert _split_eurostat_airport_code("LFPG") == (None, None)


def _stub_jsonstat(airport_values: dict[str, int | None]) -> dict:
    """Minimal JSON-stat 2.0 payload mimicking the avia_paoa response."""
    indices = {code: i for i, code in enumerate(airport_values.keys())}
    return {
        "dimension": {
            "freq": {"category": {"label": {"A": "Annual"}}},
            "rep_airp": {
                "category": {
                    "index": indices,
                    "label": {code: f"{code} airport" for code in airport_values},
                }
            },
        },
        "value": {
            str(idx): val
            for code, idx in indices.items()
            for val in [airport_values[code]]
            if val is not None
        },
    }


class TestParse:
    def test_emits_one_record_per_non_null_value(self):
        ingestor = EurostatAviationIngestor(year=2024)
        raw = _stub_jsonstat({
            "FR_LFPG": 70257116,
            "ES_LEMD": 66095218,
            "UK_EGLL": None,  # post-Brexit null — should be skipped
        })
        records = ingestor.parse(raw)
        assert len(records) == 2
        codes = {r.payload["eurostat_code"] for r in records}
        assert codes == {"FR_LFPG", "ES_LEMD"}

    def test_payload_carries_icao_country_and_value(self):
        ingestor = EurostatAviationIngestor(year=2024)
        raw = _stub_jsonstat({"FR_LFPG": 70257116})
        r = ingestor.parse(raw)[0]
        assert r.payload["icao"] == "LFPG"
        assert r.payload["country"] == "FR"
        assert r.payload["value"] == 70257116.0
        assert r.payload["concept"] == "passengers_total"
        assert r.payload["unit"] == "passengers"

    def test_skips_non_positive_values(self):
        ingestor = EurostatAviationIngestor(year=2024)
        raw = _stub_jsonstat({"FR_LFPG": 0, "ES_LEMD": -5})
        assert ingestor.parse(raw) == []

    def test_period_end_is_year_end(self):
        ingestor = EurostatAviationIngestor(year=2023)
        raw = _stub_jsonstat({"FR_LFPG": 1})
        r = ingestor.parse(raw)[0]
        assert r.period_start == "2023-01-01"
        assert r.period_end == "2023-12-31"

    def test_entity_key_includes_eurostat_code_and_period(self):
        ingestor = EurostatAviationIngestor(year=2024)
        raw = _stub_jsonstat({"FR_LFPG": 1})
        r = ingestor.parse(raw)[0]
        assert "FR_LFPG" in r.entity_key
        assert "2024-12-31" in r.entity_key
