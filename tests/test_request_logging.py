import re

import pytest


UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


class TestRequestId:
    def test_request_id_set_on_each_request(self, client):
        resp = client.get("/health/live")
        rid = resp.headers.get("X-Request-ID")
        assert rid is not None
        assert UUID_PATTERN.match(rid)

    def test_unique_request_id_per_request(self, client):
        resp1 = client.get("/health/live")
        resp2 = client.get("/health/live")
        rid1 = resp1.headers.get("X-Request-ID")
        rid2 = resp2.headers.get("X-Request-ID")
        assert rid1 != rid2

    def test_request_id_in_log_output(self, client, caplog):
        import logging
        caplog.set_level(logging.DEBUG)
        client.get("/health/live")
        found = False
        for record in caplog.records:
            rid = getattr(record, "request_id", None)
            if rid and UUID_PATTERN.match(str(rid)):
                found = True
                break
        assert found


class TestRequestDiagnosticHeaders:
    def test_response_has_timing_header(self, client):
        resp = client.get("/health/live")
        assert "X-Request-Duration-Ms" in resp.headers

    def test_timing_is_positive_float(self, client):
        resp = client.get("/health/live")
        duration = resp.headers.get("X-Request-Duration-Ms")
        assert float(duration) >= 0
