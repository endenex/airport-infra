"""Unit tests for CAA UK parsing helpers."""

from datetime import datetime, timezone

from ingestion.sources.caa_uk import (
    CAA_NAME_TO_IATA,
    CaaUkIngestor,
    _parse_float,
    _parse_int,
)


class TestParseInt:
    def test_plain_number(self):
        assert _parse_int("12345") == 12345

    def test_with_commas(self):
        assert _parse_int("12,345,678") == 12345678

    def test_with_whitespace(self):
        assert _parse_int("  42  ") == 42

    def test_float_string(self):
        # CAA sometimes uses scientific or decimal forms; we truncate.
        assert _parse_int("12345.7") == 12345

    def test_empty_returns_none(self):
        assert _parse_int("") is None

    def test_sentinel_returns_none(self):
        for v in ("..", "-", "n/a", "N/A"):
            assert _parse_int(v) is None

    def test_garbage_returns_none(self):
        assert _parse_int("not a number") is None


class TestParseFloat:
    def test_plain_float(self):
        assert _parse_float("1234.567") == 1234.567

    def test_with_commas(self):
        assert _parse_float("1,234.567") == 1234.567

    def test_empty_returns_none(self):
        assert _parse_float("") is None

    def test_garbage_returns_none(self):
        assert _parse_float("not a number") is None


class TestIataMapping:
    def test_well_known_uk_airports(self):
        assert CAA_NAME_TO_IATA["HEATHROW"] == "LHR"
        assert CAA_NAME_TO_IATA["GATWICK"] == "LGW"
        assert CAA_NAME_TO_IATA["MANCHESTER"] == "MAN"
        assert CAA_NAME_TO_IATA["BIRMINGHAM"] == "BHX"

    def test_teesside_aliases_to_same_iata(self):
        """CAA renamed Durham Tees Valley → Teesside; both map to MME."""
        assert (
            CAA_NAME_TO_IATA["DURHAM TEES VALLEY"]
            == CAA_NAME_TO_IATA["TEESSIDE INTERNATIONAL AIRPORT"]
            == "MME"
        )


class TestParseTable01:
    def test_yields_one_record_per_airport_with_pax(self):
        csv_text = (
            "rundate,report_period,airport_name,this_year_pax,this_year_total_pax,"
            "Five_years_prev_pax,Five_years_prev_pax_total\n"
            "14/03/2025 10:59,2024,HEATHROW,83857297,292488416,80886589,296839124\n"
            "14/03/2025 10:59,2024,GATWICK,43242155,292488416,46574786,296839124\n"
        )
        ingestor = CaaUkIngestor(year=2024)
        records = ingestor._parse_table_01(csv_text, datetime.now(timezone.utc))
        assert len(records) == 2
        lhr = next(r for r in records if r.payload["caa_airport_name"] == "HEATHROW")
        assert lhr.payload["concept"] == "passengers_total"
        assert lhr.payload["value"] == 83857297.0
        assert lhr.payload["unit"] == "passengers"
        assert lhr.period_end == "2024-12-31"
        assert lhr.period_start == "2024-01-01"
        # entity_key must NOT contain iata — that's a metadata lookup, not identity
        assert "HEATHROW" in lhr.entity_key
        # payload must NOT contain iata — preserves idempotency when CAA_NAME_TO_IATA evolves
        assert "iata" not in lhr.payload

    def test_skips_zero_or_missing_pax(self):
        csv_text = (
            "rundate,report_period,airport_name,this_year_pax\n"
            "x,2024,GHOST_AIRPORT,0\n"
            "x,2024,EMPTY_AIRPORT,\n"
        )
        records = CaaUkIngestor(year=2024)._parse_table_01(csv_text, datetime.now(timezone.utc))
        assert records == []


class TestParseTable05:
    def test_sums_eu_non_eu_and_domestic_atms(self):
        csv_text = (
            "rundate,report_period,Reporting_Airport_Group_Name,rpt_apt_name,"
            "Total_EU_ATM,Scheduled_All_EU_International_ATM,scheduled_passenger_EU_international_atm,"
            "charter_all_EU_international_atm,charter_EU_international_passenger_atm,"
            "total_non_EU_international_atm,scheduled_all_non_EU_international_atm,"
            "scheduled_passenger_non_EU_international_atm,charter_all_non_EU_international_atm,"
            "charter_passenger_non_EU_international_atm,total_domestic_atm,"
            "scheduled_all_domestic_atm,scheduled_passenger_domestic_atm,"
            "charter_all_domestic_atm,charter_passenger_domestic_atm\n"
            "x,2024,London,HEATHROW,210468,209514,208783,954,100,229595,229504,228504,91,40,42080,42077,42077,3,2\n"
        )
        records = CaaUkIngestor(year=2024)._parse_table_05(csv_text, datetime.now(timezone.utc))
        assert len(records) == 1
        r = records[0]
        assert r.payload["concept"] == "air_transport_movements"
        # 210468 + 229595 + 42080 = 482143
        assert r.payload["value"] == 482143.0
        assert r.payload["breakdown"] == {
            "eu_international": 210468,
            "non_eu_international": 229595,
            "domestic": 42080,
        }
        assert r.payload["unit"] == "movements"

    def test_skips_airport_with_zero_atm(self):
        csv_text = (
            "rundate,report_period,Reporting_Airport_Group_Name,rpt_apt_name,"
            "Total_EU_ATM,Scheduled_All_EU_International_ATM,scheduled_passenger_EU_international_atm,"
            "charter_all_EU_international_atm,charter_EU_international_passenger_atm,"
            "total_non_EU_international_atm,scheduled_all_non_EU_international_atm,"
            "scheduled_passenger_non_EU_international_atm,charter_all_non_EU_international_atm,"
            "charter_passenger_non_EU_international_atm,total_domestic_atm,"
            "scheduled_all_domestic_atm,scheduled_passenger_domestic_atm,"
            "charter_all_domestic_atm,charter_passenger_domestic_atm\n"
            "x,2024,Other,DEAD,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0\n"
        )
        records = CaaUkIngestor(year=2024)._parse_table_05(csv_text, datetime.now(timezone.utc))
        assert records == []


class TestParseTable13:
    def test_expands_11_year_time_series(self):
        csv_text = (
            "rundate,span,rpt_apt_grp_name,rpt_apt_name,"
            "yr01,yr02,yr03,yr04,yr05,yr06,yr07,yr08,yr09,yr10,yr11,pc_change\n"
            "x,2014 - 2024,London,HEATHROW,"
            "1498905.757,1496537.361,1541028.712,1698460.908,1699663.498,"
            "1587486.409,1146309.870,1402890.886,1350895.297,1387045.188,"
            "1532299.079,11.0\n"
        )
        records = CaaUkIngestor(year=2024)._parse_table_13(csv_text, datetime.now(timezone.utc))
        # 11 years, all non-zero
        assert len(records) == 11
        # First record is yr01 = 2014
        first = next(r for r in records if r.period_end == "2014-12-31")
        assert first.payload["value"] == 1498905.757
        assert first.payload["concept"] == "cargo_tonnes"
        assert first.payload["unit"] == "tonnes"
        # Last record is yr11 = 2024
        last = next(r for r in records if r.period_end == "2024-12-31")
        assert last.payload["value"] == 1532299.079

    def test_skips_zero_freight_years(self):
        csv_text = (
            "rundate,span,rpt_apt_grp_name,rpt_apt_name,"
            "yr01,yr02,yr03,yr04,yr05,yr06,yr07,yr08,yr09,yr10,yr11,pc_change\n"
            "x,2014 - 2024,London,LONDON CITY,"
            "27.768,23.945,68.973,0,6.707,0,0,0.362,0,0,0.513,0\n"
        )
        records = CaaUkIngestor(year=2024)._parse_table_13(csv_text, datetime.now(timezone.utc))
        # Only non-zero years should be emitted
        years = sorted(int(r.period_end[:4]) for r in records)
        assert years == [2014, 2015, 2016, 2018, 2021, 2024]
