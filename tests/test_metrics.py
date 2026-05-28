import pytest


class TestMetricsEndpoint:
    def test_metrics_endpoint_exists(self, client):
        resp = client.get("/metrics")
        assert resp.status_code == 200

    def test_metrics_format_prometheus(self, client):
        resp = client.get("/metrics")
        text = resp.data.decode()
        assert "# HELP" in text
        assert "# TYPE" in text

    def test_metrics_include_request_count(self, client):
        client.get("/health/live")
        client.get("/health/live")
        resp = client.get("/metrics")
        text = resp.data.decode()
        assert "flask_http_request_total" in text

    def test_metrics_include_request_duration(self, client):
        client.get("/health/ready")
        resp = client.get("/metrics")
        text = resp.data.decode()
        assert "flask_http_request_duration_seconds" in text

    def test_metrics_include_active_requests(self, client):
        resp = client.get("/metrics")
        text = resp.data.decode()
        assert "flask_http_request_duration_seconds" in text

    def test_metrics_include_info(self, client):
        resp = client.get("/metrics")
        text = resp.data.decode()
        assert "flask_exporter_info" in text or "python_info" in text
