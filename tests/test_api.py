"""End-to-end tests for the FastAPI surface using TestClient."""


class TestHealth:
    def test_health_returns_ok(self, api_client):
        r = api_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestAirports:
    def test_list_all(self, api_client, seeded_data):
        r = api_client.get("/airports")
        assert r.status_code == 200
        body = r.json()
        assert body["total"] == 3
        codes = {a["iata_code"] for a in body["items"]}
        assert codes == {"LHR", "LGW", "CDG"}

    def test_filter_by_country(self, api_client, seeded_data):
        r = api_client.get("/airports", params={"country": "GB"})
        body = r.json()
        assert body["total"] == 2
        assert {a["iata_code"] for a in body["items"]} == {"LHR", "LGW"}

    def test_filter_by_tier(self, api_client, seeded_data):
        r = api_client.get("/airports", params={"tier": 1})
        body = r.json()
        assert {a["iata_code"] for a in body["items"]} == {"LHR", "CDG"}

    def test_filter_has_data_true(self, api_client, seeded_data):
        # LHR (2 records) and LGW (1 record); CDG has no records
        r = api_client.get("/airports", params={"has_data": True})
        body = r.json()
        assert {a["iata_code"] for a in body["items"]} == {"LHR", "LGW"}

    def test_filter_has_data_false(self, api_client, seeded_data):
        r = api_client.get("/airports", params={"has_data": False})
        body = r.json()
        assert {a["iata_code"] for a in body["items"]} == {"CDG"}

    def test_pagination(self, api_client, seeded_data):
        r = api_client.get("/airports", params={"limit": 2, "offset": 0})
        assert len(r.json()["items"]) == 2
        r = api_client.get("/airports", params={"limit": 2, "offset": 2})
        assert len(r.json()["items"]) == 1

    def test_detail_with_rollup(self, api_client, seeded_data):
        r = api_client.get("/airports/LHR")
        assert r.status_code == 200
        body = r.json()
        assert body["iata_code"] == "LHR"
        assert body["records_total"] == 2
        assert body["records_by_type"] == {"FINANCIAL": 1, "CLIMATE": 1}

    def test_detail_iata_is_case_insensitive(self, api_client, seeded_data):
        r = api_client.get("/airports/lhr")
        assert r.status_code == 200
        assert r.json()["iata_code"] == "LHR"

    def test_detail_unknown_iata_404(self, api_client, seeded_data):
        r = api_client.get("/airports/ZZZ")
        assert r.status_code == 404


class TestRecords:
    def test_list_all(self, api_client, seeded_data):
        r = api_client.get("/records")
        assert r.status_code == 200
        assert r.json()["total"] == 3

    def test_filter_by_iata(self, api_client, seeded_data):
        r = api_client.get("/records", params={"iata": "LHR"})
        assert r.json()["total"] == 2

    def test_filter_by_source_id(self, api_client, seeded_data):
        r = api_client.get("/records", params={"source_id": "esma_xbrl"})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["record_type"] == "FINANCIAL"

    def test_filter_by_record_type(self, api_client, seeded_data):
        r = api_client.get("/records", params={"record_type": "CLIMATE"})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["payload"]["concept"] == "scope_1_emissions_tco2e"

    def test_unknown_iata_returns_empty_not_404(self, api_client, seeded_data):
        # List endpoints are tolerant — filtering on a non-existent airport
        # is a legitimate query that should return zero rows.
        r = api_client.get("/records", params={"iata": "ZZZ"})
        assert r.status_code == 200
        assert r.json()["total"] == 0

    def test_get_record_by_id(self, api_client, seeded_data):
        rec_id = seeded_data["rec_lhr_climate"].id
        r = api_client.get(f"/records/{rec_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["record_type"] == "CLIMATE"
        assert body["payload"]["value"] == 26000.0

    def test_get_unknown_record_404(self, api_client, seeded_data):
        r = api_client.get("/records/not-a-real-id")
        assert r.status_code == 404


class TestIngestionRuns:
    def test_list_all(self, api_client, seeded_data):
        r = api_client.get("/ingestion-runs")
        body = r.json()
        assert body["total"] == 2

    def test_filter_by_status(self, api_client, seeded_data):
        r = api_client.get("/ingestion-runs", params={"status": "failed"})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["error_message"] == "auth failed"

    def test_filter_by_source_id(self, api_client, seeded_data):
        r = api_client.get("/ingestion-runs", params={"source_id": "esma_xbrl"})
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["status"] == "completed"


class TestReviewQueue:
    def test_list_pending(self, api_client, seeded_data):
        r = api_client.get("/llm-extractions", params={"status": "pending_review"})
        body = r.json()
        assert body["total"] == 1
        row = body["items"][0]
        assert row["confidence_score"] == 0.72
        assert row["data_record"]["payload"]["concept"] == "scope_1_emissions_tco2e"

    def test_approve(self, api_client, seeded_data):
        ext_id = str(seeded_data["pending_extraction"].id)
        r = api_client.post(
            f"/llm-extractions/{ext_id}/approve",
            json={"notes": "spot-checked against source"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["review_status"] == "approved"
        assert body["review_notes"] == "spot-checked against source"
        assert body["reviewed_at"] is not None

    def test_reject(self, api_client, seeded_data):
        ext_id = str(seeded_data["pending_extraction"].id)
        r = api_client.post(
            f"/llm-extractions/{ext_id}/reject",
            json={"notes": "wrong unit"},
        )
        assert r.status_code == 200
        assert r.json()["review_status"] == "rejected"

    def test_cannot_review_an_already_reviewed_record(self, api_client, seeded_data):
        ext_id = str(seeded_data["pending_extraction"].id)
        api_client.post(f"/llm-extractions/{ext_id}/approve", json={})
        r = api_client.post(f"/llm-extractions/{ext_id}/approve", json={})
        assert r.status_code == 409

    def test_unknown_extraction_404(self, api_client, seeded_data):
        bogus = "00000000-0000-0000-0000-000000000000"
        r = api_client.post(f"/llm-extractions/{bogus}/approve", json={})
        assert r.status_code == 404
