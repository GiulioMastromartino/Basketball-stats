import json
import logging
import sys

import pytest

from core.logger import JSONFormatter, RequestIdFilter, get_logger


class TestJSONFormatter:
    def make_record(self, msg="hello world", level=logging.INFO,
                    exc_info=None, extra_fields=None):
        logger = logging.getLogger("test")
        logger.setLevel(logging.DEBUG)
        record = logger.makeRecord(
            "test", level, "test_logging.py", 42,
            msg, (), exc_info=exc_info,
        )
        if extra_fields:
            record.extra_fields = extra_fields
        return record

    def test_basic_fields(self):
        record = self.make_record()
        formatter = JSONFormatter()
        raw = formatter.format(record)
        data = json.loads(raw)
        assert data["level"] == "INFO"
        assert data["message"] == "hello world"
        assert data["logger"] == "test"
        assert data["module"] == "test_logging"
        assert "timestamp" in data

    def test_respects_log_level_debug(self):
        record = self.make_record(msg="debug msg", level=logging.DEBUG)
        formatter = JSONFormatter()
        data = json.loads(formatter.format(record))
        assert data["level"] == "DEBUG"
        assert data["message"] == "debug msg"

    def test_respects_log_level_error(self):
        record = self.make_record(msg="error msg", level=logging.ERROR)
        formatter = JSONFormatter()
        data = json.loads(formatter.format(record))
        assert data["level"] == "ERROR"

    def test_includes_exception(self):
        try:
            raise ValueError("bad value")
        except ValueError:
            exc_info = sys.exc_info()
            record = self.make_record(msg="something broke",
                                      level=logging.ERROR,
                                      exc_info=exc_info)
            formatter = JSONFormatter()
            raw = formatter.format(record)
            data = json.loads(raw)

        assert "exception" in data
        assert data["exception"]["type"] == "ValueError"
        assert data["exception"]["message"] == "bad value"

    def test_extra_fields(self):
        record = self.make_record(msg="with extra",
                                  extra_fields={"custom_key": "custom_val"})
        formatter = JSONFormatter()
        data = json.loads(formatter.format(record))
        assert data["custom_key"] == "custom_val"

    def test_output_is_valid_json(self):
        record = self.make_record(msg="valid json check")
        formatter = JSONFormatter()
        data = json.loads(formatter.format(record))
        assert isinstance(data, dict)

    def test_exc_info_true_does_not_crash(self):
        record = self.make_record(msg="no crash", exc_info=True)
        formatter = JSONFormatter()
        data = json.loads(formatter.format(record))
        assert data["message"] == "no crash"
        assert "exception" not in data


class TestRequestIdFilter:
    def test_no_request_context(self):
        logger = logging.getLogger("test_no_ctx")
        filter_ = RequestIdFilter()
        record = logger.makeRecord(
            "test_no_ctx", logging.INFO, "test_logging.py", 100,
            "no request", (), exc_info=None,
        )
        assert filter_.filter(record) is True
        assert record.request_id is None

    def test_get_logger_cached(self):
        logger_a = get_logger("cache_test")
        logger_b = get_logger("cache_test")
        assert logger_a is logger_b

    def test_get_logger_has_filter(self):
        logger = get_logger("filter_test")
        has_filter = any(isinstance(f, RequestIdFilter) for f in logger.filters)
        assert has_filter
